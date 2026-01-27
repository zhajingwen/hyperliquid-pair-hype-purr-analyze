# 功能：分析山寨币与BTC/USDC的皮尔逊相关系数，识别存在时间差套利空间的异常币种
# 原理：通过计算不同时间周期和延迟下的相关系数，找出短期低相关但长期高相关的币种
# 基准币种：BTC/USDC:USDC，作为参考基准，用于计算相关系数、Beta系数和Z-score
# 目标币种：Hyperliquid 全量 USDC 本位永续合约

import ccxt
import time
import numpy as np
import pandas as pd
from enum import Enum
from retry import retry
from statsmodels.tsa.stattools import adfuller
import statsmodels.api as sm
from sklearn.linear_model import LinearRegression
from typing import Union, Tuple, Optional

from utils.lark_bot import sender
from utils.config import lark_bot_id
from utils.coingetation_more_check import CointegrationHealthMonitor
from utils.logging_config import logger


# ========== 新增：平稳性等级枚举类 ==========
class StationarityLevel(Enum):
    """价差序列平稳性等级"""
    STRONG = "strong"        # 强平稳: p < 0.05
    WEAK = "weak"            # 弱平稳: 0.05 <= p < 0.10
    NON_STATIONARY = "non"   # 非平稳: p >= 0.10

    @property
    def chinese_name(self) -> str:
        """中文名称"""
        return {
            StationarityLevel.STRONG: "强平稳",
            StationarityLevel.WEAK: "弱平稳",
            StationarityLevel.NON_STATIONARY: "非平稳"
        }[self]


class DelayCorrelationAnalyzer:
    """
    山寨币与基准币种相关系数分析器

    通过分析山寨币与BTC/USDC:USDC的相关系数，
    识别短期低相关但长期高相关的异常币种，这类币种存在时间差套利机会。

    核心功能：
    - 计算不同时间周期和延迟下的相关系数
    - 计算Beta系数衡量波动幅度关系
    - 使用OLS回归（Engle-Granger两步法）进行协整检验和平稳性验证
    - 计算Z-score识别价差偏离（基于OLS回归构建的价差序列）
    """
    # 相关系数计算所需的最小数据点数
    MIN_POINTS_FOR_CORR_CALC = 10
    # 数据分析所需的最小数据点数
    MIN_DATA_POINTS_FOR_ANALYSIS = 50

    # ========== 相关系数过滤配置 ==========
    # ('4h', '60d') 组合的相关系数阈值：大于此值保留，小于等于此值剔除
    TARGET_CORR_THRESHOLD = 0.6
    # 目标时间周期和数据周期配置
    TARGET_TIMEFRAME = '4h'  # K线时间周期
    TARGET_PERIOD = '60d'    # 数据周期

    # ========== 新增：异常值处理配置 ==========
    # Winsorization 分位数配置
    WINSORIZE_LOWER_PERCENTILE = 0.1   # 下分位数（0.1%）
    WINSORIZE_UPPER_PERCENTILE = 99.9  # 上分位数（99.9%）
    # 是否启用异常值处理（可配置开关）
    ENABLE_OUTLIER_TREATMENT = True

    # ========== 新增：Z-score 配置 ==========
    # 是否启用 Z-score 检查（默认启用）
    ENABLE_ZSCORE_CHECK = True
    # 长周期（4H）的Z-score阈值
    ZSCORE_THRESHOLD_LONG = 0.2  # 测试值
    # 中间周期（1H）的Z-score阈值
    ZSCORE_THRESHOLD_MIDDLE = 1.5  # 测试值
    # 短周期（5M）的Z-score阈值
    ZSCORE_THRESHOLD_SHORT = 1.8  # 测试值
    # ========== 双窗口策略配置 ==========
    # OLS回归窗口（长期关系窗口，用于 Z-score 价差构建）
    BETA_WINDOW = 100  # 建议值：80-120，平衡稳定性与响应性（OLS回归窗口）

    # Z-score 统计量计算窗口（短期偏离窗口）
    ZSCORE_WINDOW = 30  # 建议值：20-30，保持短期均值回归敏感度

    # ========== 新增：分级平稳性检验配置 ==========
    # 是否启用平稳性检验（默认启用）
    ENABLE_STATIONARITY_CHECK = True
    # 强平稳阈值（统计学上显著平稳）
    STATIONARITY_STRONG_THRESHOLD = 0.05  # p-value < 0.05
    # 弱平稳阈值（探索性分析可接受）
    STATIONARITY_WEAK_THRESHOLD = 0.10   # 0.05 <= p-value < 0.10
    # 弱信号是否发送飞书告警（默认关闭，避免告警过载）
    ENABLE_WEAK_SIGNAL_FEISHU = True
    # 向后兼容：保留原变量名
    STATIONARITY_SIGNIFICANCE_LEVEL = STATIONARITY_STRONG_THRESHOLD
    # 老协整检验方案
    STATS_PERIOD = ('4h', '60d')
    # 协整检验结果通过的周期数阈值
    COINTEGRATION_RESULT_APPROVED_THRESHOLD_NUMBER = 2  # 至少需要2个周期通过协整检验

    def __init__(self, exchange_name="hyperliquid", timeout=30000, default_combinations=None):
        """
        初始化分析器

        Args:
            exchange_name: 交易所名称，支持ccxt库支持的所有交易所
            timeout: 请求超时时间（毫秒）
            default_combinations: K线组合列表，如 [("5m", "7d"), ("1h", "30d")] (从短周期到长周期的顺序)
        """
        self.exchange_name = exchange_name
        self.exchange = getattr(ccxt, exchange_name)({
            "timeout": timeout,
            "enableRateLimit": True,
            "rateLimit": 1500
        })
        # 保留双周期组合用于相关性对比：5分钟K线7天，1小时K线30天
        # Beta/协整/ADF检验将使用配置周期(STATS_PERIOD)数据计算
        self.combinations = default_combinations or [("5m", "7d"), ("1h", "30d")]
        # 基准币种交易对：作为参考基准，用于计算与其他山寨币的相关系数和Beta系数
        self.base_symbol = "BTC/USDC:USDC"  # 修改为BTC/USDC:USDC
        # 基准币种数据缓存：缓存不同时间周期和周期的基准币种K线数据
        self.base_df_cache = {}
        # 山寨币数据缓存：缓存不同山寨币的K线数据
        self.alt_df_cache = {}

        # ========== 新增：平稳性统计变量 ==========
        self.strong_signal_count = 0  # 强平稳信号数量
        self.weak_signal_count = 0    # 弱平稳信号数量
        self.non_stationary_count = 0 # 非平稳信号数量

        # 检查 lark_bot_id 是否有效
        if not lark_bot_id:
            logger.warning("环境变量 LARKBOT_ID 未设置，飞书通知功能将不可用")
            self.lark_hook = None
        else:
            self.lark_hook = f'https://open.feishu.cn/open-apis/bot/v2/hook/{lark_bot_id}'

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        """
        将 timeframe 字符串转换为分钟数

        支持的格式：
        - 分钟：1m, 5m, 15m, 30m
        - 小时：1h, 4h, 12h
        - 天：1d, 3d
        - 周：1w

        Args:
            timeframe: K线时间周期字符串

        Returns:
            对应的分钟数

        Raises:
            ValueError: 不支持的 timeframe 格式
        """
        unit_multipliers = {
            'm': 1,
            'h': 60,
            'd': 24 * 60,
            'w': 7 * 24 * 60,
        }

        unit = timeframe[-1].lower()
        if unit not in unit_multipliers:
            raise ValueError(f"不支持的 timeframe 格式: {timeframe}，支持的单位: m, h, d, w")

        try:
            value = int(timeframe[:-1])
        except ValueError:
            raise ValueError(f"无效的 timeframe 格式: {timeframe}，数值部分必须是整数")

        return value * unit_multipliers[unit]

    @staticmethod
    def _period_to_bars(period: str, timeframe: str) -> int:
        """将时间周期转换为K线总条数"""
        days = int(period.rstrip('d'))
        timeframe_minutes = DelayCorrelationAnalyzer._timeframe_to_minutes(timeframe)
        bars_per_day = int(24 * 60 / timeframe_minutes)
        return days * bars_per_day

    def _safe_download(self, symbol: str, period: str, timeframe: str, coin: str = None) -> Optional[pd.DataFrame]:
        """
        安全下载数据，失败时返回None并记录日志

        Args:
            symbol: 交易对名称
            period: 数据周期
            timeframe: K线时间周期
            coin: 用于日志的币种名称（可选）

        Returns:
            成功返回DataFrame，失败返回None
        """
        display_name = coin or symbol
        return self._safe_execute(
            self.download_ccxt_data,
            symbol, period=period, timeframe=timeframe,
            error_msg=f"下载 {display_name} 的 {timeframe}/{period} 数据失败"
        )

    @retry(tries=10, delay=5, backoff=2, logger=logger)
    def download_ccxt_data(self, symbol: str, period: str, timeframe: str) -> pd.DataFrame:
        """
        从交易所下载OHLCV历史数据

        Args:
            symbol: 交易对名称，如 "BTC/USDC:USDC"
            period: 数据周期，如 "30d"
            timeframe: K线时间周期，如 "5m"

        Returns:
            包含 Open/High/Low/Close/Volume/return/volume_usd 列的DataFrame
        """
        target_bars = self._period_to_bars(period, timeframe)
        ms_per_bar = self._timeframe_to_minutes(timeframe) * 60 * 1000
        now_ms = self.exchange.milliseconds()
        since = now_ms - target_bars * ms_per_bar

        all_rows = []
        fetched = 0

        while True:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1500)
            if not ohlcv:
                break

            all_rows.extend(ohlcv)
            fetched += len(ohlcv)
            since = ohlcv[-1][0] + 1

            if len(ohlcv) < 1500 or fetched >= target_bars:
                break

            # 请求间隔：添加 1.5 秒延迟，确保即使 ccxt 内部发起多次请求也有足够间隔
            # 对 Hyperliquid 来说，1.5 秒是安全的间隔
            time.sleep(1.5)

        if not all_rows:
            logger.debug(f"交易对无历史数据（API返回空列表）| 币种: {symbol} | {timeframe}/{period}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "return", "volume_usd"])

        df = pd.DataFrame(all_rows, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="ms", utc=True).dt.tz_convert(None)
        df = df.set_index("Timestamp").sort_index()
        df['return'] = df['Close'].pct_change().fillna(0)
        df['volume_usd'] = df['Volume'] * df['Close']

        return df

    @staticmethod
    def _winsorize_returns(returns, lower_p=None, upper_p=None, log_stats=True, coin: str = None):
        """
        Winsorization 异常值处理

        将收益率数组中的极端值限制在指定分位数范围内，提高统计分析的稳健性。

        Args:
            returns: 收益率数组（numpy array）
            lower_p: 下分位数（默认使用类常量 WINSORIZE_LOWER_PERCENTILE）
            upper_p: 上分位数（默认使用类常量 WINSORIZE_UPPER_PERCENTILE）
            log_stats: 是否记录统计信息到日志（默认 False）
            coin: 币种名称（可选，用于日志）

        Returns:
            处理后的收益率数组（numpy array）

        Note:
            - 如果数据点少于 20 个，不进行异常值处理（返回原数组）
            - 使用 np.clip 进行快速处理
            - 异常值会被限制在分位数边界内，而不是删除
        """
        # 1. 参数默认值处理
        if lower_p is None:
            lower_p = DelayCorrelationAnalyzer.WINSORIZE_LOWER_PERCENTILE
        if upper_p is None:
            upper_p = DelayCorrelationAnalyzer.WINSORIZE_UPPER_PERCENTILE

        # 2. 数据量检查：如果数据点太少，不进行异常值处理
        if len(returns) < 20:
            return returns

        # 3. 计算分位数边界
        lower_bound = np.percentile(returns, lower_p)
        upper_bound = np.percentile(returns, upper_p)

        # 4. 统计异常值数量（用于日志和调试）
        n_lower_outliers = np.sum(returns < lower_bound)
        n_upper_outliers = np.sum(returns > upper_bound)
        total_outliers = n_lower_outliers + n_upper_outliers

        # 6. Winsorization：将极端值限制在分位数范围内
        winsorized = np.clip(returns, lower_bound, upper_bound)

        # 6. 记录统计信息（如果启用）
        if log_stats and total_outliers > 0:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.info(
                f"异常值处理统计 | "
                f"下侧异常值数量: {n_lower_outliers} | "
                f"上侧异常值数量: {n_upper_outliers} | "
                f"分位数范围: [{lower_bound:.6f}, {upper_bound:.6f}] | "
                f"原始数据范围: [{np.min(returns):.6f}, {np.max(returns):.6f}] | "
                f"处理后数据范围: [{np.min(winsorized):.6f}, {np.max(winsorized):.6f}]"
                f"{coin_info}"
            )

        return winsorized

    @staticmethod
    def _calculate_cointegration_params(base_prices: pd.Series, alt_prices: pd.Series,
                                        coin: str = None, base_symbol: str = None) -> Optional[dict]:
        """
        使用OLS回归计算协整参数（验证性函数）

        通过OLS回归计算截距项α和斜率β，并进行ADF检验验证价差平稳性。
        这是协整检验的标准方法（Engle-Granger两步法）。

        Args:
            base_prices: 基准币种价格序列（pandas Series）
            alt_prices: 山寨币价格序列（pandas Series）
            coin: 币种名称（可选，用于日志）

        Returns:
            dict: {
                'alpha': 截距项（价格溢价/折价）,
                'beta': OLS回归系数（对冲比例）,
                'spread': OLS价差序列（残差，保留原始索引）,
                'adf_pvalue': ADF检验p值（平稳性）
            }
            None: 如果计算失败

        Note:
            - α显著非0表示存在固定溢价/折价
            - β是最优对冲比例
            - ADF p-value < 0.05 表示价差平稳，适合配对交易
            - 此函数用于验证性分析，使用全样本数据是标准做法（Engle-Granger两步法）
            - 返回的价差序列保留原始时间索引，便于后续分析
            - 注意：此函数存在 look-ahead bias（使用全样本），仅用于事后验证，不适用于实时交易
              实时交易应使用 price_diff_spread_ols_window 方法
        """
        try:
            # 1. 数据验证
            if len(base_prices) != len(alt_prices):
                coin_info = f" | 币种: {coin}" if coin else ""
                base_symbol_info = f" | 基准币种: {base_symbol}" if base_symbol else ""
                logger.warning(f"协整参数计算失败：基准币种和ALT数据长度不一致 | "
                              f"基准币种: {len(base_prices)}, ALT: {len(alt_prices)}"
                              f"{coin_info}{base_symbol_info}")
                return None

            if len(base_prices) < 10:  # 最小数据点要求
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"协整参数计算失败：数据点不足（需要至少10个点，实际{len(base_prices)}个）{coin_info}")
                return None

            # 2. 计算对数价格（保留索引信息）
            log_base_series = np.log(base_prices)
            log_alt_series = np.log(alt_prices)

            # 3. statsmodels OLS回归（带常数项）：log_alt = α + β * log_base + ε
            # 注意：此函数用于验证性分析，使用全样本是标准做法（Engle-Granger两步法）
            # 虽然存在 look-ahead bias，但这是协整检验的标准方法
            X = sm.add_constant(log_base_series)
            model = sm.OLS(log_alt_series, X).fit()

            alpha = model.params.iloc[0]      # 常数项
            beta = model.params.iloc[1]       # 斜率
            alpha_pvalue = model.pvalues.iloc[0]  # α的p值
            beta_pvalue = model.pvalues.iloc[1]   # β的p值
            rsquared = model.rsquared    # 拟合优度

            # 4. 根据α显著性和绝对值大小选择价差计算方法（智能模型选择）
            if alpha_pvalue < 0.05 and abs(alpha) > 5:
                # α显著且绝对值很大 → 跨资产类配对（如NEAR/BTC）
                # 使用无α模型更稳健（避免α时变性问题）
                spread_ols = log_alt_series - beta * log_base_series
                model_type = "no_intercept_forced"
                use_alpha = False
                model_reason = f"|α|={abs(alpha):.1f}>5, 跨资产类配对"
                
            elif alpha_pvalue < 0.05 and abs(alpha) < 2:
                # α显著且绝对值较小 → 同类资产配对（如UNI/SUSHI）
                # α代表真实的溢价关系，应当包含
                spread_ols = log_alt_series - (alpha + beta * log_base_series)
                model_type = "standard_EG"  # 标准Engle-Granger
                use_alpha = True
                model_reason = f"|α|={abs(alpha):.1f}<2, 同类资产配对"
                
            else:
                # α不显著或中等范围（2<=|α|<=5）→ 使用无α模型
                spread_ols = log_alt_series - beta * log_base_series
                model_type = "no_intercept"
                use_alpha = False
                if alpha_pvalue >= 0.05:
                    model_reason = "α不显著"
                else:
                    model_reason = f"|α|={abs(alpha):.1f}∈[2,5], 中等范围"

            # 5. ADF检验价差平稳性（使用数值数组）
            adf_result = adfuller(spread_ols.values, autolag='AIC')
            adf_pvalue = adf_result[1]

            # 6. 日志输出（便于调试）
            if coin:
                logger.debug(
                    f"协整参数 | 币种: {coin} | α={alpha:.4f} (p={alpha_pvalue:.4f}) | "
                    f"β={beta:.4f} (p={beta_pvalue:.4f}) | R²={rsquared:.4f} | "
                    f"模型: {model_type} | 原因: {model_reason} | ADF p={adf_pvalue:.4f}"
                )

            return {
                'alpha': alpha,
                'beta': beta,
                'spread': spread_ols,  # 保留原始索引的 pandas Series
                'adf_pvalue': adf_pvalue,
                # 新增统计信息
                'alpha_pvalue': alpha_pvalue,
                'beta_pvalue': beta_pvalue,
                'rsquared': rsquared,
                'model_type': model_type,
                'use_alpha': use_alpha,  # 标记是否使用了α
                'model_reason': model_reason  # 模型选择原因
            }
        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.debug(f"OLS协整参数计算失败：{type(e).__name__}: {str(e)}{coin_info}", exc_info=True)
            return None

    @staticmethod
    def price_diff_spread_ols_window(base_prices: pd.Series, alt_prices: pd.Series, beta_window: int = 100, zscore_window: int = 30) -> pd.Series:
        """
        计算价格差价（双窗口策略：OLS回归使用长窗口（稳定），统计量使用短窗口（敏感）。）
        """
        # 4. 数据切片：取足够计算OLS回归和统计量的数据
        data_window = max(beta_window, zscore_window)
        recent_base_full = base_prices.iloc[-data_window:]
        recent_alt_full = alt_prices.iloc[-data_window:]

        # 5. OLS回归计算协整参数
        # 使用前 beta_window-1 个点计算OLS参数（避免 look-ahead bias）
        # 公式：log_alt = α + β × log_base + ε
        # 用途：构建价差序列 spread = log(ALT) - (α + β × log(BASE))
        ols_base = recent_base_full.iloc[:-1]
        ols_alt = recent_alt_full.iloc[:-1]

        # 计算对数价格
        log_base_ols = np.log(ols_base)
        log_alt_ols = np.log(ols_alt)

        # statsmodels OLS回归
        X = sm.add_constant(log_base_ols)
        model = sm.OLS(log_alt_ols, X).fit()

        alpha = model.params.iloc[0]          # 常数项
        beta_ols = model.params.iloc[1]       # 斜率
        alpha_pvalue = model.pvalues.iloc[0]  # α的p值
        beta_pvalue = model.pvalues.iloc[1]   # β的p值
        rsquared = model.rsquared         # 拟合优度

        # 根据α显著性和绝对值大小选择价差计算方法（智能模型选择）
        log_base_full = np.log(recent_base_full)  # 全部100期
        log_alt_full = np.log(recent_alt_full)

        if alpha_pvalue < 0.05 and abs(alpha) > 5:
            # α显著且绝对值很大 → 跨资产类配对（如NEAR/BTC）
            # 使用无α模型更稳健（避免α时变性问题）
            spread_full = log_alt_full - beta_ols * log_base_full
            model_type = "no_intercept_forced"
            use_alpha = False
            model_reason = f"|α|={abs(alpha):.1f}>5, 跨资产类配对"
            
        elif alpha_pvalue < 0.05 and abs(alpha) < 2:
            # α显著且绝对值较小 → 同类资产配对（如UNI/SUSHI）
            # α代表真实的溢价关系，应当包含
            spread_full = log_alt_full - (alpha + beta_ols * log_base_full)
            model_type = "standard_EG"
            use_alpha = True
            model_reason = f"|α|={abs(alpha):.1f}<2, 同类资产配对"
            
        else:
            # α不显著或中等范围（2<=|α|<=5）→ 使用无α模型
            spread_full = log_alt_full - beta_ols * log_base_full
            model_type = "no_intercept"
            use_alpha = False
            if alpha_pvalue >= 0.05:
                model_reason = "α不显著"
            else:
                model_reason = f"|α|={abs(alpha):.1f}∈[2,5], 中等范围"

        # ADF检验价差平稳性
        adf_result = adfuller(spread_full.values, autolag='AIC')
        adf_pvalue = adf_result[1]

        # 6. 价差构建（用于Z-score计算：使用短窗口保持敏感度）
        # 取最近 zscore_window 期数据，使用长窗口计算的OLS参数构建对数价差
        recent_base = recent_base_full.iloc[-zscore_window:]
        recent_alt = recent_alt_full.iloc[-zscore_window:]
        log_base = np.log(recent_base)
        log_alt = np.log(recent_alt)

        # 使用相同的模型选择
        if use_alpha:
            spread = log_alt - (alpha + beta_ols * log_base)
        else:
            spread = log_alt - beta_ols * log_base

        return {
            'alpha': alpha,           # 截距项（价格溢价/折价）
            'beta': beta_ols,         # OLS回归系数
            'spread': spread,         # 用于Z-score计算的价差序列
            'adf_pvalue': adf_pvalue, # ADF检验价差平稳性
            # 新增统计信息
            'alpha_pvalue': alpha_pvalue,
            'beta_pvalue': beta_pvalue,
            'rsquared': rsquared,
            'model_type': model_type,
            'use_alpha': use_alpha,
            'model_reason': model_reason  # 模型选择原因
        }

    def cointegration_analysis(
        self, cointegration_result: dict, 
        method_type: str, 
        coin: str = None, 
        stats_period_key: tuple = None
        ) -> bool:
        """
        协整分析
        """
        # 协整检验状态
        cointegration_status = False
        # 币种信息
        coin_info = f" | 币种: {coin} | 方法: {method_type}" if coin else ""
        # check_result = ''
        if cointegration_result is None or cointegration_result['adf_pvalue'] >= 0.05:
            if cointegration_result:
                adf_pvalue_str = f"{cointegration_result['adf_pvalue']:.4f}"
                alpha_str = f"{cointegration_result['alpha']:.4f}"
                beta_str = f"{cointegration_result['beta']:.4f}"
                check_result = (f"❌ 协整检验未通过（基于{stats_period_key}周期数据） | "
                                f"α={alpha_str}, β={beta_str} | "
                                f"ADF p-value: {adf_pvalue_str} >= 0.05 | "
                                f"原因: 价差非平稳，不适合配对交易"
                                f"{coin_info}")
            else:
                check_result = (
                    f"❌ 协整检验未通过（基于{stats_period_key}周期数据） | "
                    f"ADF p-value: N/A | "
                    f"原因: OLS参数计算失败"
                    f"{coin_info}"
                )
            # is_anomaly = False  # ⚠️ 协整失败，拒绝信号
        else:
            # 协整检验通过，输出详细信息
            check_result = (f"✅ 协整检验通过（基于{stats_period_key}周期数据） | "
                            f"α={cointegration_result['alpha']:.4f}, β={cointegration_result['beta']:.4f} | "
                            f"ADF p-value={cointegration_result['adf_pvalue']:.4f} < 0.05"
                            f"{coin_info}")
            cointegration_status = True
        self.alert_content += f"\n{check_result}\n"
        logger.info(check_result)

        return cointegration_status

    def multiple_cointegration_analysis(self, 
        base_prices: pd.Series, 
        alt_prices: pd.Series, 
        coin: str = None, 
        stats_period_key: tuple = None,
        beta_window: int = None,
        zscore_window: int = None,
    ) -> tuple[bool, bool, dict]:
        """
        多周期协整检验
        """
        if stats_period_key == ('4h', '60d'):
            # === 协整健康监控（优化版）- 双窗口对比分析 ===
            # 计算对数价格（保留索引信息）
            log_base_series = np.log(base_prices)
            log_alt_series = np.log(alt_prices)

            # 长期监控（200期 = 33天）- 评估长期结构稳定性
            monitor_long = CointegrationHealthMonitor(
                window=200,
                enable_diagnostics=True,
                state_thresholds=(18, 14, 10)  # 调整为合理阈值
            )
            result_long = monitor_long.update(log_base_series, log_alt_series)

            # 短期监控（100期 = 16.7天）- 与交易信号窗口对齐
            monitor_short = CointegrationHealthMonitor(
                window=100,
                enable_diagnostics=True,
                state_thresholds=(18, 14, 10)  # 调整为合理阈值
            )
            result_short = monitor_short.update(log_base_series, log_alt_series)

            # 计算窗口差异
            score_diff = abs(result_long['health_score'] - result_short['health_score'])

            # health_result_content_str = f"健康得分: {health_result['health_score']} | 状态: {health_result['state']} | ADF得分: {health_result['scores']['adf']} | 半衰期得分: {health_result['scores']['halflife']} | 稳定性得分: {health_result['scores']['stability']} | ADF p-value: {health_result['adf_pvalue']:.4f} | 半衰期: {health_result['halflife']}"
            # logger.info(f"协整健康监控结果 | 币种: {coin} | 健康结果: {health_result_content_str}")

            # === 增强日志输出 ===
            cointegration_health_result = f"""
            ╔════════════════════════════════════════════════════════════════
            ║ 协整健康监控 | 币种: {coin}
            ╠════════════════════════════════════════════════════════════════
            ║ 【长期窗口 200期】
            ║   综合得分: {result_long['health_score']} | 状态: {result_long['state']}
            ║   ADF: p={result_long['adf_pvalue']:.4f} (得分:{result_long['scores']['adf']})
            ║   半衰期: {result_long['halflife']} 期 (得分:{result_long['scores']['halflife']}) | 原因:{result_long['halflife_reason']}
            ║   phi: {result_long.get('phi', 'N/A')} | Hurst: {result_long.get('hurst', 'N/A')}
            ║   稳定性: {result_long['scores']['stability']} (β变异:{result_long['stability_details'].get('beta_cv', 'N/A')}, 均值漂移:{result_long['stability_details'].get('mean_shift_ratio', 'N/A'):.3f}, ADF持续:{result_long['stability_details'].get('adf_pass_rate', 'N/A'):.1%})
            ║
            ║ 【短期窗口 100期】
            ║   综合得分: {result_short['health_score']} | 状态: {result_short['state']}
            ║   ADF: p={result_short['adf_pvalue']:.4f} (得分:{result_short['scores']['adf']})
            ║   半衰期: {result_short['halflife']} 期 (得分:{result_short['scores']['halflife']}) | 原因:{result_short['halflife_reason']}
            ║   phi: {result_short.get('phi', 'N/A')} | Hurst: {result_short.get('hurst', 'N/A')}
            ║   稳定性: {result_short['scores']['stability']} (β变异:{result_short['stability_details'].get('beta_cv', 'N/A')}, 均值漂移:{result_short['stability_details'].get('mean_shift_ratio', 'N/A'):.3f}, ADF持续:{result_short['stability_details'].get('adf_pass_rate', 'N/A'):.1%})
            ║
            ║ 【窗口对比】
            ║   得分差异: {score_diff:.2f} {'⚠️ 显著差异' if score_diff > 10 else '✓ 差异正常'}
            ║   趋势判断: {'📈 短期改善' if result_short['health_score'] > result_long['health_score'] else '📉 短期恶化' if result_short['health_score'] < result_long['health_score'] else '➡️ 稳定'}
            ║
            ║ 【诊断信息 - 长期】
            ║   模型质量: Beta R²={result_long['diagnostics']['model_quality'].get('beta_rsquared', 'N/A')}, AR1 R²={result_long['diagnostics']['model_quality'].get('ar1_rsquared', 'N/A')}, phi={result_long.get('phi', 'N/A')}
            ║   数据质量: Spread σ={result_long['diagnostics']['data_quality']['spread_std']:.4f}, 偏度={result_long['diagnostics']['data_quality']['spread_skewness']:.2f}, 峰度={result_long['diagnostics']['data_quality']['spread_kurtosis']:.2f}
            ║   异常警告: {', '.join(result_long['diagnostics']['warnings']) if result_long['diagnostics']['warnings'] else '无异常'}
            ╚════════════════════════════════════════════════════════════════
                        """.strip()
            logger.info(cointegration_health_result)
            self.alert_content += f"\n{cointegration_health_result}\n"

            # 如果有严重问题，额外输出警告
            if result_long['diagnostics']['warnings']:
                warning_details = []
                for warning in result_long['diagnostics']['warnings']:
                    if warning == 'AR1_LOW_FIT':
                        warning_details.append(f"AR(1)模型拟合优度低(R²={result_long['diagnostics']['model_quality'].get('ar1_rsquared', 'N/A')}), 半衰期可能不可靠")
                    elif warning == 'BETA_UNSTABLE':
                        warning_details.append(f"β系数不稳定(变异系数={result_long['stability_details'].get('beta_cv', 'N/A')}), 协整关系可能恶化")
                    elif warning == 'MEAN_SHIFT_LARGE':
                        warning_details.append(f"均值显著漂移(漂移比={result_long['stability_details'].get('mean_shift_ratio', 'N/A'):.2f}), 价差中枢改变")
                    elif warning == 'ADF_INCONSISTENT':
                        warning_details.append(f"ADF检验不一致(通过率={result_long['stability_details'].get('adf_pass_rate', 'N/A'):.1%}), 平稳性存疑")
                    elif warning == 'VOLATILITY_REGIME_CHANGE':
                        warning_details.append("波动率状态突变, 可能发生结构性变化")
                    else:
                        warning_details.append(warning)

                logger.warning(f"⚠️ 币种 {coin} 健康监控异常 | 问题: {' | '.join(warning_details)}")

        # 协整检验（基于配置周期数据）(老方案)，全量数据
        ols_params = DelayCorrelationAnalyzer._calculate_cointegration_params(
            base_prices, alt_prices, coin=coin, base_symbol=self.base_symbol
        )
        cointegration_status_total_period = self.cointegration_analysis(ols_params, 'old', coin, stats_period_key)
        # 输出Old方法的模型选择信息
        if ols_params:
            logger.info(
                f"Old方法 | 币种: {coin} | 模型类型: {ols_params.get('model_type')} | "
                f"α显著性: p={ols_params.get('alpha_pvalue', 'N/A'):.4f} | "
                f"β显著性: p={ols_params.get('beta_pvalue', 'N/A'):.4f} | "
                f"R²={ols_params.get('rsquared', 'N/A'):.4f}"
            )
        
        # 双窗口策略：OLS回归使用长窗口（稳定），统计量使用短窗口（敏感）。
        cointegration_result = DelayCorrelationAnalyzer.price_diff_spread_ols_window(base_prices, alt_prices, beta_window, zscore_window)
        cointegration_status_short_period = self.cointegration_analysis(cointegration_result, 'new', coin, stats_period_key)
        # 输出New方法的模型选择信息
        if cointegration_result:
            logger.info(
                f"New方法 | 币种: {coin} | 模型类型: {cointegration_result.get('model_type')} | "
                f"α显著性: p={cointegration_result.get('alpha_pvalue', 'N/A'):.4f} | "
                f"β显著性: p={cointegration_result.get('beta_pvalue', 'N/A'):.4f} | "
                f"R²={cointegration_result.get('rsquared', 'N/A'):.4f}"
            )
        
        # 返回协整检验状态，短周期协整检验状态，协整检验结果
        return cointegration_status_total_period, cointegration_status_short_period, cointegration_result

    def _calculate_zscore(
        self,
        base_prices: pd.Series,
        alt_prices: pd.Series,
        window: int = 20,
        beta_window: int = None,
        coin: str = None,
        cointegration_result: dict = None
    ) -> Optional[float]:
        """
        计算 Z-score（基于OLS回归方法）

        使用OLS回归计算协整参数，构建价差序列并计算Z-score。

        双窗口策略：OLS回归使用长窗口（稳定），统计量使用短窗口（敏感）。

        Args:
            base_prices: 基准币种价格序列
            alt_prices: 山寨币价格序列
            window: 统计量窗口大小（默认 20），实际使用 ZSCORE_WINDOW
            beta_window: OLS回归窗口大小（可选，默认 None 使用 BETA_WINDOW 类属性）
            coin: 币种名称（用于日志）
            stats_period_key: 统计周期 ('5m', '7d') 或 ('1h', '30d') 或 ('4h', '60d')
            cointegration_result: 协整检验结果
        Returns:
            tuple: (zscore, stationarity_level, p_value)
                - zscore: Z-score 值（如果计算失败则为 None）
                - stationarity_level: 始终返回 None（已移除协整检验）
                - p_value: 始终返回 None（已移除协整检验）

        Note:
            - 使用OLS回归：log_alt = α + β × log_base + ε
            - 价差公式：spread = log(ALT) - (α + β × log(BASE))
            - 双窗口设计：beta_window 用于OLS回归，window 用于计算统计量
            - OLS回归使用前 beta_window-1 个点（避免 look-ahead bias）
            - 均值和标准差基于前 window-1 期价差，避免样本偏差
            - 降级策略：数据不足时自动降级为单窗口模式
        """
        # ========== 双窗口策略实现（基于OLS回归）==========
        # 1. 参数处理：beta_window 默认使用类属性 BETA_WINDOW
        if beta_window is None:
            beta_window = getattr(DelayCorrelationAnalyzer, 'BETA_WINDOW', window * 3)
        zscore_window = window

        # 2. 数据验证
        if len(base_prices) != len(alt_prices):
            return None

        # 3. 数据验证与降级策略
        required_points = max(beta_window, zscore_window)
        if len(base_prices) < required_points:
            # 降级策略：数据足够 zscore 但不足 beta → 使用 zscore 窗口
            if len(base_prices) >= zscore_window:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.warning(
                    f"Z-score 降级为单窗口模式 | 数据不足 beta_window | "
                    f"需要: {required_points}, 实际: {len(base_prices)} | "
                    f"使用 zscore_window={zscore_window} 替代{coin_info}"
                )
                beta_window = zscore_window
            else:
                return None

        try:
            spread = cointegration_result['spread']
            # 调试信息：记录价差序列的长度和统计量
            # spread_len = len(spread)
            spread_mean = spread.iloc[:-1].mean()
            spread_std = spread.iloc[:-1].std()
            current_spread = spread.iloc[-1]

            # 8. 检查统计量有效性
            if pd.isna(spread_mean) or pd.isna(spread_std):
                return None

            if spread_std == 0 or np.isnan(spread_std):
                return None

            # 9. 计算当前 Z-score（修复：使用当前窗口的最后一个价差值）
            zscore = (current_spread - spread_mean) / spread_std

            # logger.info(f"Z-score: 双窗口策略：OLS回归使用长窗口（稳定），统计量使用短窗口（敏感）。: {zscore}")

            if np.isnan(zscore) or np.isinf(zscore):
                return None

            return float(zscore)

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Z-score 计算异常：{type(e).__name__}: {str(e)}{coin_info}", exc_info=True)
            return None

    def _get_trading_direction(self, zscore: float, coin: str) -> tuple[str, str]:
        """
        根据 Z-score 获取交易方向

        基于价差的Z-score值判断交易方向：
        - Z-score > 0: 价差偏高，预期回归 → 做空山寨币/做多基准币种
        - Z-score < 0: 价差偏低，预期回归 → 做多山寨币/做空基准币种

        Args:
            zscore: Z-score 值（可正可负），表示当前价差相对于历史均值的偏离程度
            coin: 币种名称（如 "AR/USDC:USDC"）

        Returns:
            tuple: (方向描述, 方向代码)
                - 方向描述: "做空{coin}/做多{基准币种}" 或 "做多{coin}/做空{基准币种}"（coin保留完整值）
                - 方向代码: "short_alt_long_base" 或 "long_alt_short_base"

        Note:
            基准币种由 self.base_symbol 指定
        """
        if zscore > 0:
            # 价差偏高，预期回归 → 做空山寨币，做多基准币种
            return f"做空{coin}/做多{self.base_symbol}", "short_alt_long_base"
        elif zscore < 0:
            # 价差偏低，预期回归 → 做多山寨币，做空基准币种
            return f"做多{coin}/做空{self.base_symbol}", "long_alt_short_base"
        else:
            return "无方向（Z-score=0）", "neutral"

    def find_optimal_delay(self, base_ret, alt_ret, max_lag=3,
                           enable_outlier_treatment=None, coin: str = None):
        """
        寻找最优延迟 τ*（增强版：支持异常值处理）

        通过计算不同延迟下基准币种和山寨币收益率的相关系数，找出使相关系数最大的延迟值。
        tau_star > 0 表示山寨币滞后于基准币种，存在时间差套利机会。

        Args:
            base_ret: 基准币种收益率数组
            alt_ret: 山寨币收益率数组
            max_lag: 最大延迟值（默认 3）
            enable_outlier_treatment: 是否启用异常值处理（None 时使用类常量）
            coin: 币种名称（可选，用于日志）

        Returns:
            tuple: (tau_star, corrs, max_related_matrix)
                - tau_star: 最优延迟值
                - corrs: 所有延迟值对应的相关系数列表
                - max_related_matrix: 最大相关系数
        """
        # ========== 1. 参数默认值处理 ==========
        if enable_outlier_treatment is None:
            enable_outlier_treatment = DelayCorrelationAnalyzer.ENABLE_OUTLIER_TREATMENT

        # ========== 2. 异常值处理（如果启用）==========
        if enable_outlier_treatment:
            base_symbol_name = self.base_symbol.split('/')[0]
            base_ret_processed = DelayCorrelationAnalyzer._winsorize_returns(
                base_ret, coin=f"{base_symbol_name} (参考币种)"
            )
            alt_ret_processed = DelayCorrelationAnalyzer._winsorize_returns(
                alt_ret, coin=f"{coin} (目标币种)"
            )
        else:
            base_ret_processed = base_ret
            alt_ret_processed = alt_ret

        # ========== 3. 原有逻辑：计算相关系数和最优延迟 ==========
        corrs = []
        lags = list(range(0, max_lag + 1))
        arr_len = len(base_ret_processed)

        for lag in lags:
            # 检查 lag 是否超过数组长度，避免空数组切片
            if lag > 0 and lag >= arr_len:
                corrs.append(np.nan)
                continue

            if lag > 0:
                # ALT滞后基准币种: 比较 BASE[t] 与 ALT[t+lag]
                x = base_ret_processed[:-lag]
                y = alt_ret_processed[lag:]
            else:
                x = base_ret_processed
                y = alt_ret_processed

            m = min(len(x), len(y))

            if m < DelayCorrelationAnalyzer.MIN_POINTS_FOR_CORR_CALC:
                corrs.append(np.nan)
                continue

            related_matrix = np.corrcoef(x[:m], y[:m])[0, 1]
            corrs.append(np.nan if np.isnan(related_matrix) else related_matrix)

        # 找出最大相关系数对应的延迟值（匹配性最好的延迟窗口长度）
        valid_corrs = np.array(corrs)
        valid_mask = ~np.isnan(valid_corrs)
        if valid_mask.any():
            valid_indices = np.where(valid_mask)[0]
            best_idx = valid_indices[np.argmax(valid_corrs[valid_mask])]
            tau_star = lags[best_idx]
            max_related_matrix = valid_corrs[best_idx]
        else:
            tau_star = 0
            max_related_matrix = np.nan

        return tau_star, corrs, max_related_matrix

    def _get_base_data(self, timeframe: str, period: str) -> Optional[pd.DataFrame]:
        """
        获取基准币种数据（带缓存）

        从交易所下载基准币种（base_symbol）的K线数据，并缓存结果以提高性能。
        基准币种数据用于与所有山寨币进行相关性分析和Beta系数计算。

        Args:
            timeframe: K线时间周期（如 "5m", "1h"）
            period: 数据周期（如 "7d", "30d"）

        Returns:
            包含OHLCV数据的DataFrame，失败返回None
        """
        cache_key = (timeframe, period)
        if cache_key in self.base_df_cache:
            logger.debug(f"基准币种数据缓存命中 | 基准币种: {self.base_symbol} | {timeframe}/{period}")
            return self.base_df_cache[cache_key].copy()

        logger.debug(f"基准币种数据缓存未命中，开始下载 | 基准币种: {self.base_symbol} | {timeframe}/{period}")
        base_df = self._safe_download(self.base_symbol, period, timeframe)
        if base_df is None:
            return None
        self.base_df_cache[cache_key] = base_df
        return base_df.copy()

    def _get_alt_data(self, symbol: str, period: str, timeframe: str, coin: str = None) -> Optional[pd.DataFrame]:
        """
        获取山寨币数据（带缓存）

        Args:
            symbol: 交易对名称
            period: 数据周期
            timeframe: K线时间周期
            coin: 用于日志的币种名称（可选）

        Returns:
            成功返回DataFrame，失败返回None
        """
        display_name = coin or symbol
        cache_key = (symbol, timeframe, period)

        # 检查缓存
        if cache_key in self.alt_df_cache:
            cached_df = self.alt_df_cache[cache_key]
            # 验证缓存的数据是否为空
            if cached_df.empty or len(cached_df) == 0:
                logger.warning(f"山寨币数据缓存命中但数据为空，跳过 | 币种: {display_name} | {timeframe}/{period}")
                return None
            logger.debug(f"山寨币数据缓存命中 | 币种: {display_name} | {timeframe}/{period}")
            return cached_df.copy()

        # 直接下载并缓存
        logger.debug(f"山寨币数据缓存未命中，开始下载 | 币种: {display_name} | {timeframe}/{period}")
        alt_df = self._safe_download(symbol, period, timeframe, coin)
        if alt_df is None:
            return None
        # 验证下载的数据是否为空
        if alt_df.empty or len(alt_df) == 0:
            logger.warning(f"山寨币数据不存在（空数据），不缓存 | 币种: {display_name} | {timeframe}/{period}")
            return None
        # 验证数据量是否足够
        if len(alt_df) < self.MIN_DATA_POINTS_FOR_ANALYSIS:
            logger.warning(f"山寨币数据量不足，不缓存 | 币种: {display_name} | {timeframe}/{period} | 数据量: {len(alt_df)}")
            return None
        self.alt_df_cache[cache_key] = alt_df
        return alt_df.copy()

    @staticmethod
    def _safe_execute(func, *args, error_msg: str = None, log_error: bool = True, **kwargs):
        """
        安全执行函数，统一错误处理

        Args:
            func: 要执行的函数
            *args: 函数的位置参数
            error_msg: 自定义错误消息（可选）
            log_error: 是否记录错误日志（默认True）
            **kwargs: 函数的关键字参数

        Returns:
            函数返回值，如果发生异常返回 None
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if log_error and error_msg:
                # 使用 exc_info=True 记录完整的异常堆栈跟踪
                logger.warning(f"{error_msg} | {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    def _align_and_validate_data(self, base_df: pd.DataFrame, alt_df: pd.DataFrame,
                                  coin: str, timeframe: str, period: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        对齐和验证基准币种与山寨币数据

        Args:
            base_df: 基准币种数据DataFrame
            alt_df: 山寨币数据DataFrame
            coin: 币种名称（用于日志）
            timeframe: 时间周期
            period: 数据周期

        Returns:
            成功返回对齐后的 (base_df, alt_df)，失败返回 None
        """
        # 检查数据是否存在（区分"数据不存在"和"数据量不足"）
        if alt_df.empty or len(alt_df) == 0:
            logger.warning(f"数据不存在（空数据），跳过 | 币种: {coin} | {timeframe}/{period}")
            return None

        # 对齐时间索引
        common_idx = base_df.index.intersection(alt_df.index)
        base_df_aligned = base_df.loc[common_idx]
        alt_df_aligned = alt_df.loc[common_idx]

        # 数据验证：检查数据量（数据存在但不足）
        if len(base_df_aligned) < self.MIN_DATA_POINTS_FOR_ANALYSIS or len(alt_df_aligned) < self.MIN_DATA_POINTS_FOR_ANALYSIS:
            logger.warning(f"数据量不足，跳过 | 币种: {coin} | {timeframe}/{period} | 基准币种({self.base_symbol})数据量: {len(base_df_aligned)} | 山寨币数据量: {len(alt_df_aligned)}")
            logger.debug(f"币种: {coin} | {timeframe}/{period} 数据详情 | 基准币种({self.base_symbol}): {base_df.head()}, length: {len(base_df)} | 山寨币: {alt_df.head()}, length: {len(alt_df)}")
            return None

        return base_df_aligned, alt_df_aligned

    def _analyze_single_combination(self, coin: str, timeframe: str, period: str, alt_df: Optional[pd.DataFrame] = None,
                                     base_df_aligned: Optional[pd.DataFrame] = None, alt_df_aligned: Optional[pd.DataFrame] = None) -> Optional[tuple]:
        """
        分析单个 timeframe/period 组合下，基准币种与目标山寨币之间的相关性和最优时间延迟关系
        
        该方法是配对交易策略的核心分析单元，用于计算在特定时间周期和数据周期组合下，
        两个币种价格变动的相关性以及最优的交易时滞（lag）关系。
        
        核心功能流程：
        1. 数据准备：获取或使用预提供的基准币和山寨币历史数据
        2. 数据对齐：确保两个币种的时间序列在时间维度上一致
        3. 相关性分析：计算收益率序列的相关系数和最优时间延迟
        
        应用场景：
        - 配对交易（Pairs Trading）策略中寻找高度相关的交易对
        - 套利策略中识别存在领先-滞后关系的币种对
        - 风险对冲策略中评估资产间的协同性

        Args:
            coin (str): 
                目标山寨币的交易对名称，例如 "ETH-USDT", "BNB-USDT"
                
            timeframe (str): 
                K线时间周期，决定了数据的时间粒度
                常见值：'1m', '5m', '15m', '1h', '4h', '1d'
                例如：'4h' 表示使用4小时K线数据
                
            period (str): 
                历史数据的时间跨度，决定了回溯的历史长度
                常见值：'7d', '30d', '60d', '90d'
                例如：'60d' 表示使用最近60天的历史数据
                
            alt_df (Optional[pd.DataFrame], optional): 
                可选的预获取的山寨币历史数据DataFrame
                用途：性能优化，避免重复API调用
                - 如果提供：直接使用该数据，跳过 _get_alt_data() 调用
                - 如果不提供（None）：自动调用 _get_alt_data() 获取数据
                数据格式要求：包含 'close'、'time' 等价格和时间字段
                默认值：None
                
            base_df_aligned (Optional[pd.DataFrame], optional): 
                可选的已经对齐后的基准币种数据（如BTC数据）
                用途：高性能场景下，跳过数据获取和对齐步骤
                - 如果与 alt_df_aligned 同时提供：直接使用，跳过所有数据准备步骤
                - 如果不提供：自动获取并对齐数据
                数据格式要求：必须包含 'return' 字段（收益率），且与 alt_df_aligned 时间对齐
                默认值：None
                
            alt_df_aligned (Optional[pd.DataFrame], optional): 
                可选的已经对齐后的山寨币数据
                用途：高性能场景下，跳过数据获取和对齐步骤
                - 如果与 base_df_aligned 同时提供：直接使用，跳过所有数据准备步骤
                - 如果不提供：自动获取并对齐数据
                数据格式要求：必须包含 'return' 字段（收益率），且与 base_df_aligned 时间对齐
                默认值：None

        Returns:
            Optional[tuple]: 
                成功时返回包含4个元素的元组：
                    (related_matrix, timeframe, period, tau_star)
                    - related_matrix (float): 相关系数，范围 [-1, 1]
                        > 0.6: 强正相关，适合做多山寨币/做空基准币
                        > 0: 正相关，价格同向变动
                        < 0: 负相关，价格反向变动
                    - timeframe (str): 传入的时间周期参数（原样返回）
                    - period (str): 传入的数据周期参数（原样返回）
                    - tau_star (int): 最优时间延迟（单位：K线周期数）
                        > 0: 基准币领先山寨币 tau_star 个周期
                        = 0: 同步变动，无明显领先滞后关系
                        < 0: 山寨币领先基准币（较少见）
                        
                失败时返回 None，失败原因包括：
                    - 基准币数据获取失败
                    - 山寨币数据获取失败
                    - 数据对齐失败（例如时间范围不重叠）
                    - 数据验证失败（例如数据量不足）
                    
        数据流示例：
            场景1 - 完全自动模式（无预获取数据）：
                result = _analyze_single_combination("ETH-USDT", "4h", "60d")
                → 自动获取BTC和ETH的数据 → 自动对齐 → 计算相关性
                
            场景2 - 部分优化模式（预获取山寨币数据）：
                eth_data = _get_alt_data("ETH-USDT", "60d", "4h", "ETH-USDT")
                result = _analyze_single_combination("ETH-USDT", "4h", "60d", alt_df=eth_data)
                → 使用预获取的ETH数据 → 只获取BTC数据 → 对齐 → 计算相关性
                
            场景3 - 高性能模式（数据已对齐）：
                base_aligned, eth_aligned = _align_and_validate_data(btc_data, eth_data, ...)
                result = _analyze_single_combination("ETH-USDT", "4h", "60d", 
                                                    base_df_aligned=base_aligned,
                                                    alt_df_aligned=eth_aligned)
                → 直接使用对齐数据 → 计算相关性（最快）
                
        性能考虑：
            - 场景1：适用于单次分析，代码简洁
            - 场景2：适用于批量分析多个timeframe/period组合（同一币种）
            - 场景3：适用于多线程并行分析，最大化性能
            
        注意事项：
            1. base_df_aligned 和 alt_df_aligned 必须同时提供或同时为None
            2. 如果提供已对齐数据，必须确保数据质量（包含'return'字段且时间已对齐）
            3. 该方法不抛出异常，所有错误通过返回None处理
            4. 调用方需要检查返回值是否为None，并妥善处理失败情况
        """
        # ========== 步骤1: 数据准备与对齐 ==========
        # 灵活模式设计：支持三种数据输入方式，平衡性能和易用性
        
        # 检查是否提供了已对齐的数据（高性能模式）
        if base_df_aligned is None or alt_df_aligned is None:
            # 未提供已对齐数据，进入标准数据获取流程（向后兼容原有逻辑）
            
            # 1.1 获取基准币种数据（例如BTC-USDT）
            # 基准币通常选择市值最大、流动性最好的主流币种
            base_df = self._get_base_data(timeframe, period)
            if base_df is None:
                # 基准币数据获取失败，无法继续分析
                # 可能原因：API异常、网络错误、时间范围超出数据可用范围
                return None

            # 1.2 获取目标山寨币数据
            # 性能优化：如果调用方已预获取数据（alt_df参数），则直接使用，避免重复API调用
            if alt_df is None:
                # 未提供预获取数据，需要实时获取
                alt_df = self._get_alt_data(coin, period, timeframe, coin)
            if alt_df is None:
                # 山寨币数据获取失败，无法继续分析
                # 可能原因：币种不存在、交易对已下架、API限流
                return None

            # 1.3 数据对齐与验证
            # 目的：确保两个币种的K线数据在时间维度上严格对齐
            # 对齐内容：
            #   - 时间戳匹配：保留时间完全一致的K线
            #   - 数据长度一致：确保两个序列长度相同
            #   - 数据质量验证：检查缺失值、异常值等
            aligned_data = self._align_and_validate_data(base_df, alt_df, coin, timeframe, period)
            if aligned_data is None:
                # 数据对齐失败，无法继续分析
                # 可能原因：时间范围不重叠、数据量不足、数据质量不合格
                return None
            base_df_aligned, alt_df_aligned = aligned_data

        # ========== 步骤2: 相关性分析与最优延迟计算 ==========
        # 使用互相关分析（Cross-correlation）技术，寻找两个时间序列的最佳对齐关系
        
        # 调用 find_optimal_delay 方法进行深度分析
        # 输入：两个币种的收益率序列（return = (price_t - price_t-1) / price_t-1）
        # 算法原理：
        #   1. 计算不同时间延迟（lag）下的互相关系数
        #   2. 找出相关系数最大（绝对值）时对应的延迟值
        #   3. 返回最优延迟 tau_star 和对应的相关系数
        # 返回值：(tau_star, _, related_matrix)
        #   - tau_star: 最优时间延迟（正值表示基准币领先，负值表示山寨币领先）
        #   - _: 中间变量（未使用，用下划线忽略）
        #   - related_matrix: 在最优延迟下的相关系数
        tau_star, _, related_matrix = self.find_optimal_delay(
            base_df_aligned['return'].values,  # 基准币收益率序列（numpy数组）
            alt_df_aligned['return'].values,   # 山寨币收益率序列（numpy数组）
            coin=coin  # 传入币种名称用于日志输出
        )

        # ========== 步骤3: 结果记录与返回 ==========
        # 输出调试日志，便于开发调试和问题排查
        logger.debug(
            f"分析中间结果 | 币种: {coin} | timeframe: {timeframe} | period: {period} | "
            f"tau_star: {tau_star} | 相关系数: {related_matrix:.4f}"
        )

        # 返回分析结果元组
        # 格式：(相关系数, 时间周期, 数据周期, 最优延迟)
        # 用途：供上层方法（如批量分析）汇总和比较不同组合的表现
        return (related_matrix, timeframe, period, tau_star)

    def _detect_anomaly_pattern(self, results: list, price_data_cache: dict = None,
                               coin: str = None) -> tuple[bool, float, float, float]:
        """
        检测异常模式：('4h', '60d') 组合的相关系数 > 0.6

        新规则（简化版）：
        - 仅判断 ('4h', '60d') 组合的相关系数是否 > TARGET_CORR_THRESHOLD (0.6)
        - 满足条件 → 保留并进入 Z-score 验证
        - 不满足条件 → 剔除跳过

        Args:
            results: 分析结果列表，格式 [(correlation, timeframe, period, tau_star), ...]
            price_data_cache: 价格数据缓存（保留参数，用于后续 Z-score 计算）
            coin: 币种名称（用于日志）

        Returns:
            (is_anomaly, target_corr, 0.0, 0.0):
                - is_anomaly: 是否满足新规则
                - target_corr: ('4h', '60d') 的相关系数值
                - 0.0, 0.0: 占位符（兼容原返回值格式）
        """
        # ========== 新规则：仅判断目标组合的相关系数 ==========
        target_corr = None

        # 从 results 中查找目标组合
        for result in results:
            if len(result) >= 3:
                corr, tf, p = result[0], result[1], result[2]
                if tf == self.TARGET_TIMEFRAME and p == self.TARGET_PERIOD:
                    target_corr = corr
                    break

        # 数据验证：检查是否找到目标组合
        if target_corr is None:
            logger.warning(
                f"未找到目标组合 ({self.TARGET_TIMEFRAME}, {self.TARGET_PERIOD}) | "
                f"币种: {coin} | 可用结果: {results}"
            )
            return False, 0.0, 0.0, 0.0

        # 新判定逻辑：单一条件判断
        is_anomaly = target_corr > self.TARGET_CORR_THRESHOLD

        # 日志输出
        if is_anomaly:
            logger.info(
                f"✅ 通过相关系数筛选 | 币种: {coin} | "
                f"({self.TARGET_TIMEFRAME}, {self.TARGET_PERIOD}) 相关系数: {target_corr:.4f} > {self.TARGET_CORR_THRESHOLD}"
            )
        else:
            logger.debug(
                f"❌ 未通过相关系数筛选 | 币种: {coin} | "
                f"({self.TARGET_TIMEFRAME}, {self.TARGET_PERIOD}) 相关系数: {target_corr:.4f} <= {self.TARGET_CORR_THRESHOLD}"
            )

        # 返回值（兼容原调用方期望的4值格式）
        # 注意：diff_amount 位置现在是 target_corr
        return is_anomaly, target_corr, 0.0, 0.0


    def _output_results(self, coin: str, results: list, diff_amount: float,
                       zscore: Optional[float] = None,
                       stationarity_level: Optional['StationarityLevel'] = None,
                       p_value: Optional[float] = None):
        """
        输出异常模式的分析结果（增强版：包含 Z-score 和平稳性等级）

        Args:
            coin: 币种名称
            results: 分析结果列表
            diff_amount: ('4h', '60d') 组合的相关系数值
            zscore: Z-score 值（可选）
            stationarity_level: 平稳性等级（可选，用于区分强/弱信号）
            p_value: ADF检验的p-value（可选）
        """
        # 构建结果 DataFrame
        data_rows = []

        for result in results:
            if len(result) != 4:
                # 处理异常格式，记录日志并跳过
                logger.warning(f"结果格式异常，跳过 | 币种: {coin} | 结果长度: {len(result)} | 结果: {result}")
                continue

            corr, tf, p, ts = result

            row = {
                '相关系数': corr,
                '时间周期': tf,
                '数据周期': p,
                '最优延迟': ts
            }

            data_rows.append(row)

        df_results = pd.DataFrame(data_rows)

        logger.info(f"发现异常币种 | 交易所: {self.exchange_name} | 币种: {coin} | 4h/60d 相关系数: {diff_amount:.2f}")

        # 飞书消息内容
        content = f"{self.exchange_name}\n\n{coin} 相关系数分析结果\n{df_results.to_string(index=False)}\n"
        content += f"\n4h/60d 相关系数: {diff_amount:.2f}"

        # 如果有 Z-score 信息，根据平稳性等级添加信号强度提示
        if zscore is not None:
            abs_zscore = abs(zscore)
            direction_desc, direction_code = self._get_trading_direction(zscore, coin)

            # 根据平稳性等级调整信号描述
            if stationarity_level == StationarityLevel.STRONG:
                # 强平稳：标准套利信号输出
                if abs_zscore > 2.0:
                    signal_strength = "强"
                    emoji = "🔥"
                elif abs_zscore > 1.7:
                    signal_strength = "中等"
                    emoji = "📊"
                else:
                    signal_strength = "弱"
                    emoji = "📈" if zscore > 0 else "📉"

                content += f"\n{emoji} {signal_strength}套利信号：Z-score={zscore:.2f}（偏离{abs_zscore:.1f}倍标准差）"
                content += f"\n📌 交易方向：{direction_desc}"
                content += f"\n✅ 平稳性：{stationarity_level.chinese_name}（高质量信号）"
                if p_value is not None:
                    content += f"\n平稳性检验 p-value: {p_value:.4f} (< 0.05)"

            elif stationarity_level == StationarityLevel.WEAK:
                # 弱平稳：降级为探索性信号
                signal_strength = "探索性"
                emoji = "⚠️"

                content += f"\n{emoji} {signal_strength}套利信号：Z-score={zscore:.2f}（偏离{abs_zscore:.1f}倍标准差）"
                content += f"\n📌 交易方向：{direction_desc}"
                content += f"\n⚠️ 平稳性：{stationarity_level.chinese_name}（边缘信号，建议谨慎）"
                if p_value is not None:
                    content += f"\n💡 提示：平稳性检验 p-value: {p_value:.4f} ∈ [0.05, 0.10)，均值回归假设较弱"
                else:
                    content += f"\n💡 提示：平稳性检验 p-value ∈ [0.05, 0.10)，均值回归假设较弱"

            else:
                # 平稳性未知（向后兼容）
                if abs_zscore > 3:
                    signal_strength = "强"
                    emoji = "🔥"
                elif abs_zscore > 2:
                    signal_strength = "中等"
                    emoji = "📊"
                else:
                    signal_strength = "弱"
                    emoji = "📈" if zscore > 0 else "📉"

                content += f"\n{emoji} {signal_strength}套利信号：Z-score={zscore:.2f}（偏离{abs_zscore:.1f}倍标准差）"
                content += f"\n📌 交易方向：{direction_desc}"

        # 如果没有Z-score但有平稳性检验结果，显示非平稳信息
        if zscore is None and stationarity_level == StationarityLevel.NON_STATIONARY:
            content += f"\n❌ 非平稳的特征（平稳性检验失败）"
            if p_value is not None:
                content += f"\n平稳性检验 p-value: {p_value:.4f} (>= 0.10)"
            else:
                content += f"\n平稳性检验 p-value >= 0.10"
            content += f"\n均值回归假设不成立，不适合配对交易"

        logger.debug(f"详细分析结果:\n{df_results.to_string(index=False)}")

        # ========== 分级飞书告警策略 ==========
        if self.lark_hook:
            content += f"\n{self.alert_content}"
            # 强平稳：始终发送
            if stationarity_level == StationarityLevel.STRONG:
                sender(content, self.lark_hook)
            # 弱平稳：根据配置决定是否发送
            elif stationarity_level == StationarityLevel.WEAK:
                if self.ENABLE_WEAK_SIGNAL_FEISHU:
                    # 弱信号标题前缀区分
                    weak_content = f"⚠️ 弱信号告警 ⚠️\n{content}"
                    sender(weak_content, self.lark_hook)
                else:
                    logger.info(f"弱平稳信号仅输出日志，不发送飞书（配置禁用）| 币种: {coin}")
            elif stationarity_level == StationarityLevel.NON_STATIONARY:
                # 非平稳：发送告警，明确标注非平稳特征
                non_stationary_content = f"❌ 非平稳信号告警 ❌\n{content}"
                sender(non_stationary_content, self.lark_hook)
            else:
                # 平稳性未知：仍发送（向后兼容）
                sender(content, self.lark_hook)
        else:
            logger.warning(f"飞书通知未发送（LARKBOT_ID 未配置）| 币种: {coin}")

    def zscore_analysis(self, coin: str, price_data_cache: dict) -> bool:
        """
        分析单个币种的
        多周期，多算法的协整检验结果
        和双窗口策略计算得到的Z-score
        """
        # ========== Z-score 验证（如果启用且检测到异常）==========
        zscore_result = None
        # 保存所有周期数据的Z-score结果(短周期在前面， 长周期在后面)
        zscore_result_list = []
        # 遍历所有周期数据，计算Z-score 和 协整检验结果
        cointegration_result_list = []
        if self.ENABLE_ZSCORE_CHECK:
            for stats_period_key in price_data_cache:
                # 获取当前周期数据
                price_data = price_data_cache[stats_period_key]
                # 获取当前周期数据的协整检验结果
                cointegration_status_total_period, cointegration_status_short_period, cointegration_result = self.multiple_cointegration_analysis(
                    price_data['base_prices'],
                    price_data['alt_prices'],
                    coin=coin,
                    stats_period_key=stats_period_key,
                    beta_window=self.BETA_WINDOW,
                    zscore_window=self.ZSCORE_WINDOW
                )
                # 保存当前周期数据的协整检验结果
                cointegration_result_list.extend([cointegration_status_total_period, cointegration_status_short_period])

                # 方法：OLS回归（Engle-Granger两步法）
                # 双窗口策略：OLS回归使用长窗口（BETA_WINDOW）计算协整参数（α, β），统计量使用短窗口（ZSCORE_WINDOW）
                zscore_result = self._calculate_zscore(
                    price_data['base_prices'],
                    price_data['alt_prices'],
                    window=self.ZSCORE_WINDOW,
                    beta_window=self.BETA_WINDOW,  # 双窗口策略：OLS回归窗口
                    coin=coin,
                    cointegration_result=cointegration_result
                )
                logger.info(f"Z-score: 周期 {stats_period_key} | 币种: {coin} | Z-score: {zscore_result}")
                if zscore_result is not None:
                    zscore_result_list.append(zscore_result)
                else:
                    logger.warning(f"Z-score 计算失败，{stats_period_key} | 币种: {coin}")
        else:
            return None

        # 计算协整检验结果中为True的数量
        cointegration_true_count = sum(1 for result in cointegration_result_list if result is True)
        logger.info(f"协整检验结果统计 | 币种: {coin} | True数量: {cointegration_true_count} | 总数量: {len(cointegration_result_list)}")

        # 检查是否有足够的协整检验结果通过
        if cointegration_true_count < self.COINTEGRATION_RESULT_APPROVED_THRESHOLD_NUMBER:
            logger.warning(f"协整检验结果通过的周期数不足，需要 {self.COINTEGRATION_RESULT_APPROVED_THRESHOLD_NUMBER} 个周期通过，实际只有 {cointegration_true_count} 个 | 币种: {coin}")
            return None

        # 检查是否有足够的Z-score结果
        if len(zscore_result_list) < 3:
            logger.warning(f"Z-score 结果不足，需要3个周期，实际只有 {len(zscore_result_list)} 个 | 币种: {coin}")
            return None
        # 长周期（4H）的Z-score
        direction = zscore_result_list[-1]
        # 中间周期（1H）的Z-score
        middle_zscore = zscore_result_list[-2]
        # 短周期（5M）的Z-score
        short_zscore = zscore_result_list[0]
        # 检查3个Z-score的符号是否一致，如果一致，则认为是一个套利机会
        if (direction >= 0) == (middle_zscore >= 0) == (short_zscore >= 0):
            # 长期定方向，中间和短周期做偏离阈值验证，如果都大于阈值，则认为是一个套利机会
            if abs(direction) > self.ZSCORE_THRESHOLD_LONG and abs(middle_zscore) > self.ZSCORE_THRESHOLD_MIDDLE and abs(short_zscore) > self.ZSCORE_THRESHOLD_SHORT:
                return zscore_result_list
        logger.info(f"❌ Z-score 计算不满足告警条件 | 币种: {coin}")
        return None


    def one_coin_analysis(self, coin: str) -> bool:
        """
        分析单个币种与基准币种的相关系数，识别异常模式（增强版：支持 Z-score 验证）

        对指定的山寨币与基准币种（BTC/USDC:USDC）进行相关性分析，
        包括相关系数计算、Beta系数计算、Z-score计算和平稳性检验。

        Args:
            coin: 币种交易对名称，如 "ETH/USDC:USDC"

        Returns:
            bool: 是否发现异常模式（短期低相关但长期高相关，且满足其他阈值条件）
        """
        results = []
        current_alt_df = None  # 当前组合获取的山寨币数据
        # 缓存价格数据，用于 Z-score 计算和平稳性检验
        # 格式: {(timeframe, period): {'base_prices': pd.Series, 'alt_prices': pd.Series}}
        price_data_cache = {}

        # 直接遍历预定义的组合列表：5m/7d 和 1h/30d
        # 注意：虽然遍历两种周期获取数据，但统计检验（Beta/协整/ADF）使用配置周期(STATS_PERIOD)数据
        for timeframe, period in self.combinations:
            # 获取当前组合的数据，检查是否为空
            current_alt_df = self._get_alt_data(coin, period, timeframe, coin)
            if current_alt_df is None:
                # 数据不存在，提前退出所有组合
                logger.warning(f"币种数据不存在，跳过后续所有组合 | 币种: {coin} | {timeframe}/{period}")
                return False

            # 获取基准币种数据并对齐（一次性完成，避免重复调用）
            base_df = self._get_base_data(timeframe, period)
            if base_df is None:
                # 基准币种数据获取失败，跳过该组合
                logger.warning(f"基准币种数据获取失败，跳过组合 | 币种: {coin} | {timeframe}/{period} | 基准币种: {self.base_symbol}")
                continue

            # 对齐和验证数据（一次性完成，结果传递给 _analyze_single_combination 复用）
            aligned_data = self._align_and_validate_data(base_df, current_alt_df, coin, timeframe, period)
            if aligned_data is None:
                # 数据对齐失败，跳过该组合
                continue

            base_aligned, alt_aligned = aligned_data

            # 缓存价格数据（用于 Z-score 计算）
            price_data_cache[(timeframe, period)] = {
                'base_prices': base_aligned['Close'],
                'alt_prices': alt_aligned['Close']
            }

            # 使用已对齐的数据进行分析（传递对齐后的数据，避免重复获取和对齐）
            result = self._safe_execute(
                self._analyze_single_combination,
                coin, timeframe, period, current_alt_df,
                base_df_aligned=base_aligned,
                alt_df_aligned=alt_aligned,
                error_msg=f"处理 {coin} 的 {timeframe}/{period} 时发生异常"
            )
            if result is not None:
                results.append(result)

        # 过滤 NaN 并按相关系数降序排序
        valid_results = []
        for result in results:
            if len(result) != 4:
                # 处理异常格式，记录日志并跳过
                logger.warning(f"结果格式异常，跳过 | 币种: {coin} | 结果长度: {len(result)} | 结果: {result}")
                continue

            corr, tf, p, ts = result
            if not np.isnan(corr):
                valid_results.append((corr, tf, p, ts))

        valid_results = sorted(valid_results, key=lambda x: x[0], reverse=True)

        if not valid_results:
            logger.warning(f"数据不足，无法分析 | 币种: {coin}")
            return False

        is_anomaly, diff_amount, min_short_corr, max_long_corr = self._detect_anomaly_pattern(
            valid_results, price_data_cache=price_data_cache, coin=coin
        )
        logger.info(
            f"相关系数检测 | 币种: {coin} | 是否异常: {is_anomaly} | "
            f"4h/60d 相关系数: {diff_amount:.4f}"
        )

        if is_anomaly:
            zscore_result_list = self.zscore_analysis(coin, price_data_cache)
            if not zscore_result_list:
                logger.info(f"❌ Z-score 计算不满足告警条件 | 币种: {coin}")
                return False
            # 找到绝对值最大的元素（保留原符号）
            zscore_result = zscore_result_list[np.argmax(np.abs(zscore_result_list))]
            self._output_results(coin, valid_results, diff_amount, zscore=zscore_result)
            return True
        else:
            # 计算相关系数统计信息
            corrs = [r[0] for r in valid_results]
            # min_corr = min(corrs) if corrs else 0
            max_corr = max(corrs) if corrs else 0
            logger.info(f"❌ 常规数据 | 币种: {coin} | 最大相关系数: {max_corr:.4f} 小于阈值: {self.TARGET_CORR_THRESHOLD}")
            return False

    def get_all_usdc_perpetuals(self):
        """
        获取Hyperliquid交易所的全量USDC本位永续合约

        Returns:
            list: USDC永续合约交易对列表
        """
        try:
            logger.info("开始获取Hyperliquid全量USDC永续合约列表...")
            markets = self.exchange.load_markets()

            # 筛选USDC本位永续合约（格式：XXX/USDC:USDC）
            usdc_perpetuals = []
            for symbol in markets:
                market = markets[symbol]
                # 检查是否为USDC永续合约且非基准币种
                if (market.get('quote') == 'USDC' and
                    market.get('settle') == 'USDC' and
                    market.get('type') == 'swap' and
                    symbol != self.base_symbol):
                    usdc_perpetuals.append(symbol)

            logger.info(f"获取完成 | 共发现 {len(usdc_perpetuals)} 个USDC永续合约")
            return sorted(usdc_perpetuals)

        except Exception as e:
            logger.error(f"获取USDC永续合约列表失败：{type(e).__name__}: {str(e)}", exc_info=True)
            return []

    def run(self):
        """
        分析全量USDC永续合约与BTC的相关性

        分析Hyperliquid全量USDC永续合约，将其与BTC/USDC:USDC进行相关性分析，
        识别存在时间差套利机会的异常模式。

        注意：基准币种本身会被排除在分析列表之外。
        """
        # 获取全量USDC永续合约
        usdc_coins = self.get_all_usdc_perpetuals()

        if not usdc_coins:
            logger.error("未获取到任何USDC永续合约，程序退出")
            return

        total = len(usdc_coins)

        logger.info(f"启动分析器 | 交易所: {self.exchange_name} | "
                    f"基准币种: {self.base_symbol} | "
                    f"目标币种数量: {total} | "
                    f"K线组合: {self.combinations}")

        anomaly_count = 0
        skip_count = 0
        start_time = time.time()

        # 进度里程碑：25%, 50%, 75%, 100%
        milestones = {max(1, int(total * p)) for p in [0.25, 0.5, 0.75, 1.0]}

        for idx, coin in enumerate(usdc_coins, 1):
            logger.debug(f"检查币种: {coin}")
            self.alert_content = ''
            result = self._safe_execute(
                self.one_coin_analysis,
                coin,
                error_msg=f"分析币种 {coin} 时发生错误"
            )
            if result is True:
                anomaly_count += 1
            elif result is None:
                skip_count += 1

            # 在里程碑位置打印进度
            if idx in milestones:
                logger.info(f"分析进度: {idx}/{total} ({idx * 100 // total}%)")

            # 币种之间的间隔：增加到 2 秒，避免触发 Hyperliquid 的限流
            time.sleep(2)

        elapsed = time.time() - start_time
        logger.info(
            f"分析完成 | 交易所: {self.exchange_name} | "
            f"总数: {total} | 异常: {anomaly_count} | 跳过: {skip_count} | "
            f"耗时: {elapsed:.1f}s | 平均: {elapsed/total:.2f}s/币种"
        )

        # ========== 输出平稳性统计 ==========
        total_signals = self.strong_signal_count + self.weak_signal_count + self.non_stationary_count
        if total_signals > 0:
            logger.info(
                f"平稳性统计 | 强平稳: {self.strong_signal_count} ({self.strong_signal_count*100/total_signals:.1f}%) | "
                f"弱平稳: {self.weak_signal_count} ({self.weak_signal_count*100/total_signals:.1f}%) | "
                f"非平稳: {self.non_stationary_count} ({self.non_stationary_count*100/total_signals:.1f}%)"
            )
        # ===================================


if __name__ == "__main__":
    # 从短周期到长周期的顺序
    default_combinations = [('5m', '7d'), ('1h', '30d'), ('4h', '60d')]
    # while True:
    analyzer = DelayCorrelationAnalyzer(exchange_name="hyperliquid", default_combinations=default_combinations)
    analyzer.run()
        # time.sleep(3)
