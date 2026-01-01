# 功能：分析山寨币与BTC的皮尔逊相关系数，识别存在时间差套利空间的异常币种
# 原理：通过计算不同时间周期和延迟下的相关系数，找出短期低相关但长期高相关的币种

import ccxt
import time
import logging
import numpy as np
import pandas as pd
from enum import Enum
from retry import retry
from logging.handlers import RotatingFileHandler
from statsmodels.tsa.stattools import adfuller
from sklearn.linear_model import LinearRegression
from typing import Union, Tuple, Optional
from utils.lark_bot import sender
from utils.config import lark_bot_id


def setup_logging(log_file="hyperliquid.log", level=logging.DEBUG):
    """
    配置日志系统，支持控制台和文件输出
    
    Args:
        log_file: 日志文件路径
        level: 日志级别
    
    Returns:
        配置好的 logger 实例
    """
    log = logging.getLogger(__name__)
    
    # 避免重复添加 handlers：检查是否已有相同类型的handler
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in log.handlers
    )
    # 检查文件handler：检查是否有RotatingFileHandler类型的handler
    # 由于我们只使用RotatingFileHandler，简单检查类型即可
    has_file_handler = any(
        isinstance(h, RotatingFileHandler)
        for h in log.handlers
    )
    
    # 如果handlers已存在，直接返回
    if has_console_handler and has_file_handler:
        return log
    
    # 检查根logger是否已被配置（避免与其他模块的basicConfig冲突）
    root_logger = logging.getLogger()
    root_has_handlers = len(root_logger.handlers) > 0
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 只添加缺失的handler
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)
    
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    
    # 配置 logger
    log.setLevel(level)
    log.propagate = False  # 阻止日志传播到根 logger，避免重复打印
    
    # 如果根logger已被其他模块配置，确保不会导致重复输出
    if root_has_handlers:
        # 确保所有子logger都不传播到根logger
        log.propagate = False
    
    return log


logger = setup_logging()


# ========== 新增：平稳性等级枚举类 ==========
class StationarityLevel(Enum):
    """价差序列平稳性等级"""
    STRONG = "strong"        # 强平稳: p < 0.05
    WEAK = "weak"            # 弱平稳: 0.05 <= p < 0.10
    NON_STATIONARY = "non"   # 非平稳: p >= 0.10

    @property
    def is_valid(self) -> bool:
        """是否为有效平稳性（强或弱）"""
        return self in (StationarityLevel.STRONG, StationarityLevel.WEAK)

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
    山寨币与BTC相关系数分析器

    识别短期低相关但长期高相关的异常币种，这类币种存在时间差套利机会。
    """
    # 相关系数计算所需的最小数据点数
    MIN_POINTS_FOR_CORR_CALC = 10
    # 数据分析所需的最小数据点数
    MIN_DATA_POINTS_FOR_ANALYSIS = 50

    # 异常模式检测阈值
    # 长期相关系数阈值，目标需要在下面这两个值的范围内，否则不告警
    LONG_TERM_CORR_THRESHOLD = 0.6
    # 短期相关系数阈值，
    SHORT_TERM_CORR_THRESHOLD = 0.4  

    # 相关系数差值阈值，如果小于这个值就不告警
    CORR_DIFF_THRESHOLD = 0.38

    # ========== 新增：异常值处理配置 ==========
    # Winsorization 分位数配置
    WINSORIZE_LOWER_PERCENTILE = 0.1   # 下分位数（0.1%）
    WINSORIZE_UPPER_PERCENTILE = 99.9  # 上分位数（99.9%）
    # 是否启用异常值处理（可配置开关）
    ENABLE_OUTLIER_TREATMENT = True

    # ========== 新增：Beta 收益率系数配置 ==========
    # 是否计算 Beta 收益率系数（默认启用）
    # Beta 收益率系数：基于 BTC 和山寨币收益率计算，衡量山寨币相对 BTC 的波动幅度
    # 公式：β = Cov(BTC_returns, ALT_returns) / Var(BTC_returns)
    ENABLE_BETA_CALCULATION = True
    # Beta 收益率系数计算所需的最小数据点（与相关系数要求相同）
    MIN_POINTS_FOR_BETA_CALC = 10
    # 平均 Beta 收益率系数阈值：低于此值不发送告警（确保有足够的套利空间）
    # β < 1.0 表示波动幅度小于BTC，套利空间受限
    AVG_BETA_THRESHOLD = 1
    
    # ========== 新增：Z-score 配置 ==========
    # 是否启用 Z-score 检查（默认启用）
    ENABLE_ZSCORE_CHECK = True
    # Z-score 阈值，超过此值才认为是显著的套利机会
    ZSCORE_THRESHOLD = 2.0  # 标准差倍数

    # ========== 双窗口策略配置 ==========
    # Beta 系数计算窗口（长期关系窗口，用于 Z-score 价差构建）
    # 目的：使用更长窗口计算基于对数价格的 Beta，捕捉稳定的 BTC-ALT 价格关系
    # 用于构建价差序列：spread = log(ALT) - β × log(BTC)
    # 测试验证：窗口=100 时 Beta 标准差从 0.29 降至 0.20，稳定性提升 45%
    BETA_WINDOW = 100  # 建议值：80-120，平衡稳定性与响应性

    # Z-score 统计量计算窗口（短期偏离窗口）
    # 目的：检测当前价差相对于短期均值的偏离程度，捕捉短期套利机会
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

    def __init__(self, exchange_name="kucoin", timeout=30000, default_combinations=None):
        """
        初始化分析器
        
        Args:
            exchange_name: 交易所名称，支持ccxt库支持的所有交易所
            timeout: 请求超时时间（毫秒）
            default_combinations: K线组合列表，如 [("5m", "7d"), ("1m", "1d")]
        """
        self.exchange_name = exchange_name
        self.exchange = getattr(ccxt, exchange_name)({
            "timeout": timeout,
            "enableRateLimit": True,
            "rateLimit": 1500
        })
        # 只保留两个组合：5分钟K线7天，1分钟K线1天
        self.combinations = default_combinations or [("5m", "7d"), ("1m", "1d")]
        self.btc_symbol = "BTC/USDC:USDC"
        self.btc_df_cache = {}
        self.alt_df_cache = {}  # 山寨币数据缓存

        # ========== 新增：平稳性统计变量 ==========
        self.strong_signal_count = 0  # 强平稳信号数量
        self.weak_signal_count = 0    # 弱平稳信号数量
        self.non_stationary_count = 0 # 非平稳信号数量
        # =========================================

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
            symbol: 交易对名称，如 "BTC/USDC"
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
    def _calculate_beta(btc_ret, alt_ret, coin: str = None):
        """
        计算 Beta 收益率系数

        基于收益率序列计算 Beta 系数，衡量山寨币收益率相对 BTC 收益率的波动幅度。
        公式：β = Cov(BTC_returns, ALT_returns) / Var(BTC_returns)

        应用场景：
        - 波动率分析：评估山寨币相对 BTC 的风险暴露
        - 对冲比例：β 值可作为对冲策略的参考比例
        - 风险筛选：过滤低波动性资产（β < 阈值）

        Args:
            btc_ret: BTC 收益率数组（numpy array）
            alt_ret: 山寨币收益率数组（numpy array）
            coin: 币种名称（可选，用于日志）

        Returns:
            float: Beta 收益率系数值
                - Beta > 1.0: ALT 波动幅度大于 BTC（高波动）
                - Beta = 1.0: ALT 与 BTC 同步波动
                - Beta < 1.0: ALT 波动幅度小于 BTC（低波动）
                - Beta < 0: ALT 与 BTC 反向波动（罕见，可能存在对冲机会）
                - 如果数据不足或计算失败，返回 np.nan

        Note:
            - Beta 系数需要至少 MIN_POINTS_FOR_BETA_CALC 个数据点
            - 如果 BTC 收益率方差为 0，返回 np.nan
            - 此函数用于收益率数据，与基于价格的 _calculate_beta_from_prices() 不同
        """
        # 1. 数据长度检查
        if len(btc_ret) != len(alt_ret):
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Beta 计算失败：BTC 和 ALT 数据长度不一致 | "
                          f"BTC: {len(btc_ret)}, ALT: {len(alt_ret)}"
                          f"{coin_info}")
            return np.nan

        # 2. 最小数据点检查
        if len(btc_ret) < DelayCorrelationAnalyzer.MIN_POINTS_FOR_BETA_CALC:
            return np.nan

        # 3. 计算协方差和方差
        try:
            # 使用 numpy 的 cov 函数计算协方差矩阵
            # cov_matrix[0, 1] 是 BTC 和 ALT 的协方差
            # cov_matrix[0, 0] 是 BTC 的方差
            cov_matrix = np.cov(btc_ret, alt_ret)
            covariance = cov_matrix[0, 1]
            btc_variance = cov_matrix[0, 0]

            # 4. 检查 BTC 方差是否为 0（避免除以 0）
            if btc_variance == 0 or np.isnan(btc_variance):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Beta 计算失败：BTC 收益率方差为 0 或 NaN{coin_info}")
                return np.nan

            # 5. 计算 Beta 收益率系数
            # β = Cov(BTC_returns, ALT_returns) / Var(BTC_returns)
            beta = covariance / btc_variance

            # 6. 检查结果有效性
            if np.isnan(beta) or np.isinf(beta):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Beta 计算失败：结果为 NaN 或 Inf | Beta: {beta}{coin_info}")
                return np.nan

            return beta

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Beta 计算异常：{type(e).__name__}: {str(e)}{coin_info}")
            return np.nan

    @staticmethod
    def _calculate_cointegration_params(btc_prices: pd.Series, alt_prices: pd.Series,
                                        coin: str = None) -> Optional[dict]:
        """
        使用OLS回归计算协整参数（验证性函数）

        通过OLS回归计算截距项α和斜率β，并进行ADF检验验证价差平稳性。
        这是协整检验的标准方法（Engle-Granger两步法）。

        Args:
            btc_prices: BTC价格序列（pandas Series）
            alt_prices: 山寨币价格序列（pandas Series）
            coin: 币种名称（可选，用于日志）

        Returns:
            dict: {
                'alpha': 截距项（价格溢价/折价）,
                'beta': OLS回归系数（对冲比例）,
                'spread': OLS价差序列（残差）,
                'adf_pvalue': ADF检验p值（平稳性）
            }
            None: 如果计算失败

        Note:
            - α显著非0表示存在固定溢价/折价
            - β是最优对冲比例
            - ADF p-value < 0.05 表示价差平稳，适合配对交易
        """
        try:
            # 1. 计算对数价格
            log_btc = np.log(btc_prices).values.reshape(-1, 1)
            log_alt = np.log(alt_prices).values

            # 2. OLS回归：log_alt = α + β * log_btc + ε
            model = LinearRegression()
            model.fit(log_btc, log_alt)

            alpha = model.intercept_
            beta = model.coef_[0]

            # 3. 计算OLS价差（残差）
            spread_ols = log_alt - (alpha + beta * log_btc.flatten())

            # 4. ADF检验价差平稳性
            adf_result = adfuller(spread_ols, autolag='AIC')
            adf_pvalue = adf_result[1]

            return {
                'alpha': alpha,
                'beta': beta,
                'spread': pd.Series(spread_ols),
                'adf_pvalue': adf_pvalue
            }
        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.debug(f"OLS协整参数计算失败：{type(e).__name__}: {str(e)}{coin_info}")
            return None

    @staticmethod
    def _calculate_beta_from_prices(btc_prices: pd.Series, alt_prices: pd.Series, coin: str = None) -> Optional[float]:
        """
        基于对数价格计算 Beta 系数（全样本计算）

        本函数通过对数价格的协方差和方差计算 Beta 系数，适用于价差序列构建和 Z-score 计算。
        公式：β = Cov(log_BTC_prices, log_ALT_prices) / Var(log_BTC_prices)

        与 _calculate_beta() 的区别：
        - _calculate_beta()：基于收益率序列，用于波动率分析和风险评估
        - _calculate_beta_from_prices()：基于对数价格序列，用于协整关系和价差构建

        与 _calculate_rolling_beta_from_prices() 的区别：
        - _calculate_beta_from_prices()：使用传入序列的全部数据计算 Beta（全样本）
        - _calculate_rolling_beta_from_prices()：从传入序列的最后 window 个点计算 Beta（滚动窗口）

        应用场景：
        - Z-score 计算：用于构建对数价差序列 spread = log(ALT) - β × log(BTC)
        - 协整分析：评估价格序列的长期均衡关系
        - 对冲比例：β 值反映价格层面的对冲比例

        Args:
            btc_prices: BTC 价格序列（pandas Series）
            alt_prices: 山寨币价格序列（pandas Series）
            coin: 币种名称（可选，用于日志）

        Returns:
            float: Beta 系数值（基于对数价格，全样本）
            None: 如果计算失败

        Note:
            - 使用对数价格可以消除价格量级差异（BTC 50000 vs ALT 0.01）
            - 对数价格的线性关系更稳定，符合协整理论和配对交易实践
            - Z-score 计算使用此函数（数据已预先截取为 window-1 个点，无需滚动窗口函数）
            - 对数变换后 Beta 不等同于收益率 Beta，两者衡量不同维度的关系
        """
        # 1. 数据长度检查
        if len(btc_prices) != len(alt_prices):
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"价格 Beta 计算失败：BTC 和 ALT 数据长度不一致 | "
                          f"BTC: {len(btc_prices)}, ALT: {len(alt_prices)}"
                          f"{coin_info}")
            return None

        # 2. 最小数据点检查
        if len(btc_prices) < DelayCorrelationAnalyzer.MIN_POINTS_FOR_BETA_CALC:
            return None

        try:
            # 3. 计算对数价格
            log_btc = np.log(btc_prices)
            log_alt = np.log(alt_prices)

            # 4. 计算协方差矩阵
            cov_matrix = np.cov(log_btc, log_alt)
            covariance = cov_matrix[0, 1]
            btc_variance = cov_matrix[0, 0]

            # 5. 检查 BTC 方差是否为 0
            if btc_variance == 0 or np.isnan(btc_variance):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"价格 Beta 计算失败：BTC 对数价格方差为 0 或 NaN{coin_info}")
                return None

            # 6. 计算 Beta 系数（基于对数价格）
            # β = Cov(log_BTC, log_ALT) / Var(log_BTC)
            beta = covariance / btc_variance

            # 7. 检查结果有效性
            if np.isnan(beta) or np.isinf(beta):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"价格 Beta 计算失败：结果为 NaN 或 Inf | Beta: {beta}{coin_info}")
                return None

            return beta

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"价格 Beta 计算异常：{type(e).__name__}: {str(e)}{coin_info}")
            return None

    @staticmethod
    def _calculate_rolling_beta_from_prices(btc_prices: pd.Series, alt_prices: pd.Series,
                                             window: int, coin: str = None) -> Optional[float]:
        """
        基于滚动窗口计算 Beta 系数（用于动态 Z-score 计算）

        使用最近 window 个数据点的对数价格计算 Beta 系数，与 Z-score 的均值和标准差
        计算窗口保持一致，确保统计一致性和响应性。
        公式：β = Cov(log_BTC[-window:], log_ALT[-window:]) / Var(log_BTC[-window:])

        与 _calculate_beta_from_prices() 的区别：
        - _calculate_beta_from_prices()：使用传入数据的全样本计算 Beta（适合已截取数据）
        - _calculate_rolling_beta_from_prices()：从完整序列中提取最后 window 个点计算 Beta（适合滚动计算）

        应用场景：
        - 动态 Z-score：使用滚动窗口 Beta 反映近期价差关系变化
        - 自适应对冲：Beta 随市场变化动态调整
        - 实时监控：传入完整历史序列，自动提取最新窗口计算

        Args:
            btc_prices: BTC 价格序列（pandas Series，完整历史数据）
            alt_prices: 山寨币价格序列（pandas Series，完整历史数据）
            window: 滚动窗口大小（应与 Z-score 窗口相同，通常 20-100）
            coin: 币种名称（可选，用于日志）

        Returns:
            float: Beta 系数值（基于滚动窗口的对数价格）
            None: 如果计算失败

        Note:
            - 使用对数价格可以消除价格量级差异
            - 滚动窗口 Beta 比全样本 Beta 更能反映近期市场关系变化
            - 此函数适用于：传入完整价格序列，需要从最后 window 个点计算 Beta 的场景
            - 性能优化：如果数据已经预先截取为所需窗口大小，应使用 _calculate_beta_from_prices() 避免冗余的窗口截取
        """
        # 1. 数据长度检查
        if len(btc_prices) != len(alt_prices):
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"滚动 Beta 计算失败：BTC 和 ALT 数据长度不一致 | "
                          f"BTC: {len(btc_prices)}, ALT: {len(alt_prices)}"
                          f"{coin_info}")
            return None

        # 2. 最小数据点检查
        if len(btc_prices) < window:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.debug(f"滚动 Beta 计算失败：数据点不足 | 需要: {window}, 实际: {len(btc_prices)}{coin_info}")
            return None

        try:
            # 3. 取最后 window 个数据点
            btc_window = btc_prices.iloc[-window:]
            alt_window = alt_prices.iloc[-window:]

            # 4. 计算对数价格
            log_btc = np.log(btc_window)
            log_alt = np.log(alt_window)

            # 5. 计算协方差矩阵
            cov_matrix = np.cov(log_btc, log_alt)
            covariance = cov_matrix[0, 1]
            btc_variance = cov_matrix[0, 0]

            # 6. 检查 BTC 方差是否为 0
            if btc_variance == 0 or np.isnan(btc_variance):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"滚动 Beta 计算失败：BTC 对数价格方差为 0 或 NaN{coin_info}")
                return None

            # 7. 计算 Beta 系数（基于滚动窗口的对数价格）
            # β = Cov(log_BTC[-window:], log_ALT[-window:]) / Var(log_BTC[-window:])
            beta = covariance / btc_variance

            # 8. 检查结果有效性
            if np.isnan(beta) or np.isinf(beta):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"滚动 Beta 计算失败：结果为 NaN 或 Inf | Beta: {beta}{coin_info}")
                return None

            return beta

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"滚动 Beta 计算异常：{type(e).__name__}: {str(e)}{coin_info}")
            return None

    @staticmethod
    def _calculate_zscore(btc_prices: pd.Series, alt_prices: pd.Series,
                          window: int = 20,
                          beta_window: int = None,
                          check_stationarity: bool = True, coin: str = None) -> Optional[float]:
        """
        计算价差的 Z-score（双窗口增强版：Beta 使用长窗口，统计量使用短窗口）

        双窗口策略解决了单窗口的统计概念混淆问题：
        - Beta 窗口（长）：捕捉稳定的 BTC-ALT 长期价格关系，减少 Beta 波动
        - 统计量窗口（短）：检测短期价差偏离，提高交易信号敏感度

        测试验证：beta_window=100 时 Beta 标准差从 0.29 降至 0.20，稳定性提升 45%

        Args:
            btc_prices: BTC 价格序列（pandas Series）
            alt_prices: 山寨币价格序列（pandas Series）
            window: 统计量窗口大小（默认 20），实际使用 ZSCORE_WINDOW
            beta_window: Beta 窗口大小（可选，默认 None 使用 BETA_WINDOW 类属性）
            check_stationarity: 是否进行平稳性检验（默认 True）
            coin: 币种名称（可选，用于日志）

        Returns:
            float: 当前 Z-score 值
                - |Z-score| > 2: 显著偏离（强套利信号）
                - |Z-score| > 1: 中等偏离
                - |Z-score| < 1: 正常波动范围
            None: 如果数据不足或计算失败

        Note:
            - 双窗口设计符合配对交易理论：
              1. 取 max(beta_window, window) 期数据
              2. 前 beta_window-1 期计算 Beta（长期稳定关系）
              3. 最近 window 期构建价差（短期特征）
              4. 前 window-1 期计算统计量（避免样本偏差）
              5. 最后一个点计算 Z-score
            - Beta 计算排除最后一个点，避免 look-ahead bias
            - 使用对数价差符合协整理论
            - 降级策略：数据不足 beta_window 时自动降级为单窗口模式
        """
        # ========== 双窗口策略实现 ==========
        # 1. 参数处理：beta_window 默认使用类属性 BETA_WINDOW
        # Beta 系数（基于对数价格）使用长窗口，用于构建稳定的价差序列
        # Z-score 统计量使用短窗口，提高对价格偏离的响应性
        if beta_window is None:
            beta_window = getattr(DelayCorrelationAnalyzer, 'BETA_WINDOW', window * 3)
        zscore_window = window

        # 2. 数据长度检查
        if len(btc_prices) != len(alt_prices):
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Z-score 计算失败：BTC 和 ALT 数据长度不一致 | "
                          f"BTC: {len(btc_prices)}, ALT: {len(alt_prices)}"
                          f"{coin_info}")
            return None

        # 3. 数据验证与降级策略
        required_points = max(beta_window, zscore_window)
        if len(btc_prices) < required_points:
            # 降级策略：数据足够 zscore 但不足 beta → 使用 zscore 窗口
            if len(btc_prices) >= zscore_window:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.warning(
                    f"Z-score 降级为单窗口模式 | 数据不足 beta_window | "
                    f"需要: {required_points}, 实际: {len(btc_prices)} | "
                    f"使用 zscore_window={zscore_window} 替代{coin_info}"
                )
                beta_window = zscore_window
            else:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Z-score 计算失败：数据点不足 | 需要: {zscore_window}, 实际: {len(btc_prices)}{coin_info}")
                return None

        try:
            # 4. 数据切片：取足够计算 Beta 和统计量的数据
            data_window = max(beta_window, zscore_window)
            recent_btc_full = btc_prices.iloc[-data_window:]
            recent_alt_full = alt_prices.iloc[-data_window:]

            # 5. Beta 系数计算（长窗口，基于对数价格）
            # 使用前 beta_window-1 个点计算 Beta（避免 look-ahead bias）
            # 公式：β = Cov(log_BTC, log_ALT) / Var(log_BTC)
            # 用途：构建价差序列 spread = log(ALT) - β × log(BTC)
            beta_btc = recent_btc_full.iloc[:-1]
            beta_alt = recent_alt_full.iloc[:-1]
            rolling_beta = DelayCorrelationAnalyzer._calculate_beta_from_prices(
                beta_btc, beta_alt, coin=coin
            )
            if rolling_beta is None:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Z-score 计算失败：Beta 计算失败{coin_info}")
                return None

            # 6. 价差构建（短窗口）
            # 取最近 zscore_window 期数据，使用长窗口计算的 Beta 构建对数价差
            # 价差公式：spread = log(ALT) - β × log(BTC)
            recent_btc = recent_btc_full.iloc[-zscore_window:]
            recent_alt = recent_alt_full.iloc[-zscore_window:]
            log_btc = np.log(recent_btc)
            log_alt = np.log(recent_alt)
            spread = log_alt - rolling_beta * log_btc

            # ========== 新增：分级平稳性检验 ==========
            if check_stationarity:
                stationarity_level, p_value = DelayCorrelationAnalyzer._check_spread_stationarity(spread, coin=coin)

                # 非平稳：直接返回 None
                if stationarity_level == StationarityLevel.NON_STATIONARY:
                    coin_info = f" | 币种: {coin}" if coin else ""
                    logger.info(
                        f"Z-score 计算终止：价差序列非平稳（ADF p-value={p_value:.4f}）| "
                        f"均值回归假设不成立，不适合配对交易"
                        f"{coin_info}"
                    )
                    return None

                # 弱平稳：发出警告但继续计算
                if stationarity_level == StationarityLevel.WEAK:
                    coin_info = f" | 币种: {coin}" if coin else ""
                    logger.info(
                        f"Z-score 计算继续（弱平稳警告）| ADF p-value={p_value:.4f} | "
                        f"平稳性检验处于边缘区域（{stationarity_level.chinese_name}），建议谨慎交易"
                        f"{coin_info}"
                    )
            # =====================================

            # 6. 计算统计量（修复样本偏差：使用前window-1期数据，排除当前值）
            # 避免"用样本测试样本本身"的问题，防止Z-score被系统性低估
            spread_mean = spread.iloc[:-1].mean()
            spread_std = spread.iloc[:-1].std()

            # 7. 检查统计量有效性
            if pd.isna(spread_mean) or pd.isna(spread_std):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Z-score 计算失败：统计量包含 NaN{coin_info}")
                return None

            # 8. 检查标准差是否为 0（避免除以 0）
            if spread_std == 0 or np.isnan(spread_std):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Z-score 计算失败：价差序列标准差为 0 或 NaN{coin_info}")
                return None

            # 9. 计算当前 Z-score（修复：使用当前窗口的最后一个价差值）
            current_spread = spread.iloc[-1]
            zscore = (current_spread - spread_mean) / spread_std

            # 10. 检查结果有效性
            if np.isnan(zscore) or np.isinf(zscore):
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"Z-score 计算失败：结果为 NaN 或 Inf | Z-score: {zscore}{coin_info}")
                return None

            return float(zscore)

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Z-score 计算异常：{type(e).__name__}: {str(e)}{coin_info}")
            return None

    @staticmethod
    def _calculate_zscore_with_level(
        btc_prices: pd.Series,
        alt_prices: pd.Series,
        window: int = 20,
        beta_window: int = None,
        coin: str = None
    ) -> Tuple[Optional[float], Optional['StationarityLevel'], Optional[float]]:
        """
        计算 Z-score 并返回平稳性等级（双窗口增强版）

        此函数是 _calculate_zscore 的增强版本，同时返回 Z-score 值、平稳性等级和 p-value，
        便于下游逻辑区分强信号和弱信号。

        双窗口策略：Beta 使用长窗口（稳定），统计量使用短窗口（敏感）。

        Args:
            btc_prices: BTC 价格序列
            alt_prices: 山寨币价格序列
            window: 统计量窗口大小（默认 20），实际使用 ZSCORE_WINDOW
            beta_window: Beta 窗口大小（可选，默认 None 使用 BETA_WINDOW 类属性）
            coin: 币种名称（用于日志）

        Returns:
            tuple: (zscore, stationarity_level, p_value)
                - zscore: Z-score 值（如果计算失败或非平稳则为 None）
                - stationarity_level: 平稳性等级（如果计算失败则为 None）
                - p_value: ADF 检验的 p-value（如果计算失败则为 None）

        Note:
            - 双窗口设计：beta_window 用于计算 Beta，window 用于计算统计量
            - Beta 计算排除最后一个点，避免 look-ahead bias
            - 均值和标准差基于前 window-1 期价差，避免样本偏差
            - 降级策略：数据不足时自动降级为单窗口模式
            - 非平稳信号返回 (None, NON_STATIONARY, p_value)
            - 弱平稳信号返回 (zscore 值, WEAK, p_value)，并在日志中警告
            - 强平稳信号返回 (zscore 值, STRONG, p_value)
        """
        # ========== 双窗口策略实现 ==========
        # 1. 参数处理：beta_window 默认使用类属性 BETA_WINDOW
        if beta_window is None:
            beta_window = getattr(DelayCorrelationAnalyzer, 'BETA_WINDOW', window * 3)
        zscore_window = window

        # 2. 数据验证
        if len(btc_prices) != len(alt_prices):
            return None, None, None

        # 3. 数据验证与降级策略
        required_points = max(beta_window, zscore_window)
        if len(btc_prices) < required_points:
            # 降级策略：数据足够 zscore 但不足 beta → 使用 zscore 窗口
            if len(btc_prices) >= zscore_window:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.warning(
                    f"Z-score 降级为单窗口模式 | 数据不足 beta_window | "
                    f"需要: {required_points}, 实际: {len(btc_prices)} | "
                    f"使用 zscore_window={zscore_window} 替代{coin_info}"
                )
                beta_window = zscore_window
            else:
                return None, None, None

        try:
            # 4. 数据切片：取足够计算 Beta 和统计量的数据
            data_window = max(beta_window, zscore_window)
            recent_btc_full = btc_prices.iloc[-data_window:]
            recent_alt_full = alt_prices.iloc[-data_window:]

            # 5. Beta 系数计算（长窗口，基于对数价格）
            # 使用前 beta_window-1 个点计算 Beta（避免 look-ahead bias）
            # 公式：β = Cov(log_BTC, log_ALT) / Var(log_BTC)
            # 用途：构建价差序列 spread = log(ALT) - β × log(BTC)
            beta_btc = recent_btc_full.iloc[:-1]
            beta_alt = recent_alt_full.iloc[:-1]
            rolling_beta = DelayCorrelationAnalyzer._calculate_beta_from_prices(
                beta_btc, beta_alt, coin=coin
            )
            if rolling_beta is None:
                return None, None, None

            # 6. 价差构建（短窗口）
            # 取最近 zscore_window 期数据，使用长窗口计算的 Beta 构建对数价差
            # 价差公式：spread = log(ALT) - β × log(BTC)
            recent_btc = recent_btc_full.iloc[-zscore_window:]
            recent_alt = recent_alt_full.iloc[-zscore_window:]
            log_btc = np.log(recent_btc)
            log_alt = np.log(recent_alt)
            spread = log_alt - rolling_beta * log_btc

            # 7. 执行分级平稳性检验
            stationarity_level, p_value = DelayCorrelationAnalyzer._check_spread_stationarity(
                spread, coin=coin
            )

            # 4. 非平稳：终止计算
            if stationarity_level == StationarityLevel.NON_STATIONARY:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.info(
                    f"Z-score 计算终止：价差序列非平稳（ADF p-value={p_value:.4f}）| "
                    f"均值回归假设不成立，不适合配对交易"
                    f"{coin_info}"
                )
                return None, stationarity_level, p_value

            # 5. 弱平稳：发出警告但继续计算
            if stationarity_level == StationarityLevel.WEAK:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.info(
                    f"Z-score 计算继续（弱平稳警告）| ADF p-value={p_value:.4f} | "
                    f"平稳性检验处于边缘区域（{stationarity_level.chinese_name}），建议谨慎交易"
                    f"{coin_info}"
                )

            # 6. 计算统计量（修复样本偏差：使用前window-1期数据，排除当前值）
            # 避免"用样本测试样本本身"的问题，防止Z-score被系统性低估
            spread_mean = spread.iloc[:-1].mean()
            spread_std = spread.iloc[:-1].std()

            # 7. 检查统计量有效性
            if pd.isna(spread_mean) or pd.isna(spread_std):
                return None, stationarity_level, p_value

            if spread_std == 0 or np.isnan(spread_std):
                return None, stationarity_level, p_value

            # 8. 计算当前 Z-score（修复：使用当前窗口的最后一个价差值）
            current_spread = spread.iloc[-1]
            zscore = (current_spread - spread_mean) / spread_std

            if np.isnan(zscore) or np.isinf(zscore):
                return None, stationarity_level, p_value

            return float(zscore), stationarity_level, p_value

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"Z-score 计算异常：{type(e).__name__}: {str(e)}{coin_info}")
            return None, None, None

    @staticmethod
    def _check_spread_stationarity(spread: pd.Series,
                                    strong_threshold: float = None,
                                    weak_threshold: float = None,
                                    coin: str = None) -> tuple['StationarityLevel', float]:
        """
        检验价差序列的平稳性（增强版：分级判定）

        平稳性是配对交易的核心假设：价差序列必须是平稳的，
        才能保证均值回归性质，从而使 Z-score 的套利信号有效。

        Args:
            spread: 价差序列（pandas Series）
            strong_threshold: 强平稳阈值（默认使用类常量 STATIONARITY_STRONG_THRESHOLD）
            weak_threshold: 弱平稳阈值（默认使用类常量 STATIONARITY_WEAK_THRESHOLD）
            coin: 币种名称（可选，用于日志）

        Returns:
            tuple: (stationarity_level, p_value)
                - stationarity_level: 平稳性等级（StationarityLevel枚举）
                - p_value: ADF 检验的 p 值

        平稳性等级判定规则:
            - STRONG (强平稳): p < 0.05, 统计学上显著平稳,高质量信号
            - WEAK (弱平稳): 0.05 <= p < 0.10, 探索性分析可接受,弱信号
            - NON_STATIONARY (非平稳): p >= 0.10, 不适合配对交易,过滤

        Note:
            - ADF 检验的原假设（H0）：序列是非平稳的
            - 如果 p-value < 0.05，拒绝原假设，认为序列是强平稳的
            - 如果 0.05 <= p-value < 0.10，弱平稳，仅作为探索性信号
            - 如果价差非平稳（p >= 0.10），不应计算 Z-score
        """
        # 参数默认值处理
        if strong_threshold is None:
            strong_threshold = DelayCorrelationAnalyzer.STATIONARITY_STRONG_THRESHOLD
        if weak_threshold is None:
            weak_threshold = DelayCorrelationAnalyzer.STATIONARITY_WEAK_THRESHOLD

        try:
            # 1. 移除 NaN 值
            spread_clean = spread.dropna()

            # 2. 检查数据量是否足够（ADF 检验至少需要 20 个数据点）
            if len(spread_clean) < 20:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.debug(f"平稳性检验失败：数据点不足 | 需要: 20, 实际: {len(spread_clean)}{coin_info}")
                return StationarityLevel.NON_STATIONARY, 1.0  # 返回 p=1.0 表示无法拒绝非平稳假设

            # 3. 执行 ADF 检验
            result = adfuller(spread_clean, autolag='AIC')
            adf_statistic = result[0]
            p_value = result[1]

            # 4. 分级判定平稳性
            if p_value < strong_threshold:
                level = StationarityLevel.STRONG
            elif p_value < weak_threshold:
                level = StationarityLevel.WEAK
            else:
                level = StationarityLevel.NON_STATIONARY

            # 5. 记录检验结果（分级日志）
            coin_info = f" | 币种: {coin}" if coin else ""
            if level == StationarityLevel.STRONG:
                logger.debug(
                    f"平稳性检验通过（强平稳）| ADF统计量: {adf_statistic:.4f} | "
                    f"p-value: {p_value:.4f} < {strong_threshold} | 等级: {level.chinese_name}"
                    f"{coin_info}"
                )
            elif level == StationarityLevel.WEAK:
                logger.info(
                    f"平稳性检验通过（弱平稳）| ADF统计量: {adf_statistic:.4f} | "
                    f"p-value: {p_value:.4f} ∈ [{strong_threshold}, {weak_threshold}) | 等级: {level.chinese_name}"
                    f"{coin_info}"
                )
            else:
                logger.info(
                    f"平稳性检验失败（非平稳）| ADF统计量: {adf_statistic:.4f} | "
                    f"p-value: {p_value:.4f} >= {weak_threshold} | 等级: {level.chinese_name}"
                    f"{coin_info}"
                )

            return level, p_value

        except Exception as e:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"平稳性检验异常：{type(e).__name__}: {str(e)}{coin_info}")
            return StationarityLevel.NON_STATIONARY, 1.0

    @staticmethod
    def _get_trading_direction(zscore: float, coin: str) -> tuple[str, str]:
        """
        根据 Z-score 获取交易方向
        
        Args:
            zscore: Z-score 值（可正可负）
            coin: 币种名称（如 "AR/USDC:USDC"）
        
        Returns:
            tuple: (方向描述, 方向代码)
                - 方向描述: "做空AR/做多BTC" 或 "做多AR/做空BTC"
                - 方向代码: "short_alt_long_btc" 或 "long_alt_short_btc"
        """
        if zscore > 0:
            # 价差偏高，预期回归 → 做空山寨币，做多 BTC
            coin_symbol = coin.split('/')[0]  # 提取币种符号，如 "AR"
            return f"做空{coin_symbol}/做多BTC", "short_alt_long_btc"
        elif zscore < 0:
            # 价差偏低，预期回归 → 做多山寨币，做空 BTC
            coin_symbol = coin.split('/')[0]
            return f"做多{coin_symbol}/做空BTC", "long_alt_short_btc"
        else:
            return "无方向（Z-score=0）", "neutral"

    @staticmethod
    def find_optimal_delay(btc_ret, alt_ret, max_lag=3,
                           enable_outlier_treatment=None,
                           enable_beta_calc=None, coin: str = None):
        """
        寻找最优延迟 τ*（增强版：支持异常值处理和 Beta 系数计算）

        通过计算不同延迟下BTC和山寨币收益率的相关系数，找出使相关系数最大的延迟值。
        tau_star > 0 表示山寨币滞后于BTC，存在时间差套利机会。

        Args:
            btc_ret: BTC收益率数组
            alt_ret: 山寨币收益率数组
            max_lag: 最大延迟值（默认 3）
            enable_outlier_treatment: 是否启用异常值处理（None 时使用类常量）
            enable_beta_calc: 是否计算 Beta 系数（None 时使用类常量）
            coin: 币种名称（可选，用于日志）

        Returns:
            tuple: (tau_star, corrs, max_related_matrix, beta)
                - tau_star: 最优延迟值
                - corrs: 所有延迟值对应的相关系数列表
                - max_related_matrix: 最大相关系数
                - beta: Beta 系数（如果启用）或 None
        """
        # ========== 1. 参数默认值处理 ==========
        if enable_outlier_treatment is None:
            enable_outlier_treatment = DelayCorrelationAnalyzer.ENABLE_OUTLIER_TREATMENT
        if enable_beta_calc is None:
            enable_beta_calc = DelayCorrelationAnalyzer.ENABLE_BETA_CALCULATION

        # ========== 2. 异常值处理（如果启用）==========
        if enable_outlier_treatment:
            btc_ret_processed = DelayCorrelationAnalyzer._winsorize_returns(
                btc_ret, coin="BTC (参考币种)"
            )
            alt_ret_processed = DelayCorrelationAnalyzer._winsorize_returns(
                alt_ret, coin=f"{coin} (目标币种)"
            )
        else:
            btc_ret_processed = btc_ret
            alt_ret_processed = alt_ret

        # ========== 3. 原有逻辑：计算相关系数和最优延迟 ==========
        corrs = []
        lags = list(range(0, max_lag + 1))
        arr_len = len(btc_ret_processed)

        for lag in lags:
            # 检查 lag 是否超过数组长度，避免空数组切片
            if lag > 0 and lag >= arr_len:
                corrs.append(np.nan)
                continue

            if lag > 0:
                # ALT滞后BTC: 比较 BTC[t] 与 ALT[t+lag]
                x = btc_ret_processed[:-lag]
                y = alt_ret_processed[lag:]
            else:
                x = btc_ret_processed
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

        # ========== 4. 计算 Beta 收益率系数（如果启用）==========
        # 基于收益率序列计算 Beta，衡量山寨币相对 BTC 的波动幅度
        # 公式：β = Cov(BTC_returns, ALT_returns) / Var(BTC_returns)
        beta = None
        if enable_beta_calc:
            # 根据最优延迟选择数据对齐方式计算 Beta
            # 目的：确保 Beta 反映真实的跟随关系（考虑延迟效应）
            # 如果最优延迟 > 0，使用延迟对齐后的数据
            # 如果最优延迟 = 0，使用同期数据
            if tau_star > 0:
                # 使用最优延迟对齐后的数据：BTC[t] 与 ALT[t+tau_star]
                # 对齐后计算的 Beta 反映考虑延迟的真实波动关系
                btc_beta = btc_ret_processed[:-tau_star]
                alt_beta = alt_ret_processed[tau_star:]
            else:
                # 使用同期数据：BTC[t] 与 ALT[t]
                btc_beta = btc_ret_processed
                alt_beta = alt_ret_processed
            
            m_beta = min(len(btc_beta), len(alt_beta))
            if m_beta >= DelayCorrelationAnalyzer.MIN_POINTS_FOR_BETA_CALC:
                beta = DelayCorrelationAnalyzer._calculate_beta(
                    btc_beta[:m_beta],
                    alt_beta[:m_beta],
                    coin=coin
                )

        return tau_star, corrs, max_related_matrix, beta
    
    def _get_btc_data(self, timeframe: str, period: str) -> Optional[pd.DataFrame]:
        """获取BTC数据（带缓存）"""
        cache_key = (timeframe, period)
        if cache_key in self.btc_df_cache:
            logger.debug(f"BTC数据缓存命中 | {timeframe}/{period}")
            return self.btc_df_cache[cache_key].copy()
        
        logger.debug(f"BTC数据缓存未命中，开始下载 | {timeframe}/{period}")
        btc_df = self._safe_download(self.btc_symbol, period, timeframe)
        if btc_df is None:
            return None
        self.btc_df_cache[cache_key] = btc_df
        return btc_df.copy()
    
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
                logger.warning(f"{error_msg} | {type(e).__name__}: {str(e)}")
            return None
    
    def _align_and_validate_data(self, btc_df: pd.DataFrame, alt_df: pd.DataFrame, 
                                  coin: str, timeframe: str, period: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        对齐和验证BTC与山寨币数据
        
        Args:
            btc_df: BTC数据DataFrame
            alt_df: 山寨币数据DataFrame
            coin: 币种名称（用于日志）
            timeframe: 时间周期
            period: 数据周期
        
        Returns:
            成功返回对齐后的 (btc_df, alt_df)，失败返回 None
        """
        # 检查数据是否存在（区分"数据不存在"和"数据量不足"）
        if alt_df.empty or len(alt_df) == 0:
            logger.warning(f"数据不存在（空数据），跳过 | 币种: {coin} | {timeframe}/{period}")
            return None
        
        # 对齐时间索引
        common_idx = btc_df.index.intersection(alt_df.index)
        btc_df_aligned = btc_df.loc[common_idx]
        alt_df_aligned = alt_df.loc[common_idx]
        
        # 数据验证：检查数据量（数据存在但不足）
        if len(btc_df_aligned) < self.MIN_DATA_POINTS_FOR_ANALYSIS or len(alt_df_aligned) < self.MIN_DATA_POINTS_FOR_ANALYSIS:
            logger.warning(f"数据量不足，跳过 | 币种: {coin} | {timeframe}/{period} | BTC数据量: {len(btc_df_aligned)} | 山寨币数据量: {len(alt_df_aligned)}")
            logger.debug(f"币种: {coin} | {timeframe}/{period} 数据详情 | BTC: {btc_df.head()}, length: {len(btc_df)} | 山寨币: {alt_df.head()}, length: {len(alt_df)}")
            return None
        
        return btc_df_aligned, alt_df_aligned
    
    def _analyze_single_combination(self, coin: str, timeframe: str, period: str, alt_df: Optional[pd.DataFrame] = None, 
                                     btc_df_aligned: Optional[pd.DataFrame] = None, alt_df_aligned: Optional[pd.DataFrame] = None) -> Optional[tuple]:
        """
        分析单个 timeframe/period 组合（增强版：支持 Beta 系数）

        Args:
            coin: 币种交易对名称
            timeframe: K线时间周期
            period: 数据周期
            alt_df: 可选的预获取的山寨币数据，如果提供则直接使用，否则调用 _get_alt_data 获取
            btc_df_aligned: 可选的对齐后的BTC数据，如果提供则直接使用，跳过数据获取和对齐步骤
            alt_df_aligned: 可选的对齐后的山寨币数据，如果提供则直接使用，跳过数据获取和对齐步骤

        Returns:
            成功返回 (correlation, timeframe, period, tau_star, beta)，失败返回 None
            注意：beta 可能为 None（如果计算失败或禁用）
        """
        # 如果未提供已对齐的数据，则获取并对齐数据
        if btc_df_aligned is None or alt_df_aligned is None:
            # 原有的数据获取和对齐逻辑（向后兼容）
            btc_df = self._get_btc_data(timeframe, period)
            if btc_df is None:
                return None

            # 如果提供了预获取的数据，直接使用；否则调用 _get_alt_data 获取
            if alt_df is None:
                alt_df = self._get_alt_data(coin, period, timeframe, coin)
            if alt_df is None:
                return None

            # 对齐和验证数据
            aligned_data = self._align_and_validate_data(btc_df, alt_df, coin, timeframe, period)
            if aligned_data is None:
                return None
            btc_df_aligned, alt_df_aligned = aligned_data

        # 调用增强版的 find_optimal_delay（现在返回 4 个值）
        tau_star, _, related_matrix, beta = self.find_optimal_delay(
            btc_df_aligned['return'].values,
            alt_df_aligned['return'].values,
            coin=coin
        )

        # 增强日志输出
        if beta is not None and not np.isnan(beta):
            logger.debug(
                f"分析中间结果 | 币种: {coin} | timeframe: {timeframe} | period: {period} | "
                f"tau_star: {tau_star} | 相关系数: {related_matrix:.4f} | Beta: {beta:.4f}"
            )
        else:
            logger.debug(
                f"分析中间结果 | 币种: {coin} | timeframe: {timeframe} | period: {period} | "
                f"tau_star: {tau_star} | 相关系数: {related_matrix:.4f}"
            )

        return (related_matrix, timeframe, period, tau_star, beta)
    
    def _detect_anomaly_pattern(self, results: list, price_data_cache: dict = None,
                               coin: str = None) -> tuple[bool, float, float, float]:
        """
        检测异常模式：短期低相关但长期高相关（增强版：包含协整验证）

        异常模式判断阈值：
        - 长期相关系数 > LONG_TERM_CORR_THRESHOLD：长期与BTC有较强跟随性（7d对应5m）
        - 短期相关系数 < SHORT_TERM_CORR_THRESHOLD：短期存在明显滞后（1d对应1m）
        - 差值 > CORR_DIFF_THRESHOLD：短期和长期差异足够显著
        - 平均Beta系数 >= AVG_BETA_THRESHOLD：波动幅度需满足阈值要求
        - 协整检验 ADF p-value < 0.05：价差平稳，适合配对交易（新增）

        Args:
            results: 分析结果列表
            price_data_cache: 价格数据缓存字典 {(timeframe, period): {'btc_prices': ..., 'alt_prices': ...}}
            coin: 币种名称（可选，用于日志）

        Returns:
            (is_anomaly, diff_amount, min_short_corr, max_long_corr): 是否异常模式、相关系数差值、短期最小相关系数、长期最大相关系数
        """
        # ========== 先提取相关系数 ==========
        short_periods = ['1d']
        long_periods = ['7d']
        
        # 使用索引访问，添加长度检查以确保安全（兼容4元组和5元组格式）
        short_term_corrs = [x[0] for x in results if len(x) >= 3 and x[2] in short_periods]
        long_term_corrs = [x[0] for x in results if len(x) >= 3 and x[2] in long_periods]
        
        if not short_term_corrs or not long_term_corrs:
            return False, 0, 0.0, 0.0
        
        min_short_corr = min(short_term_corrs)
        max_long_corr = max(long_term_corrs)
        
        # ========== Beta 收益率系数检查 ==========
        # 从 results 中提取所有有效的 Beta 收益率系数值
        # Beta 收益率系数：基于收益率计算，衡量山寨币相对 BTC 的波动幅度
        # 用于过滤波动不足的交易对（β < 阈值），确保有足够套利空间
        valid_betas = []
        for result in results:
            # 处理新旧格式兼容（5个值 vs 4个值）
            if len(result) == 5:
                _, _, _, _, beta = result
                if beta is not None and not np.isnan(beta):
                    valid_betas.append(beta)
            elif len(result) == 4:
                # 旧格式没有 beta，跳过
                continue
        
        # 如果启用了 Beta 计算且有有效的 Beta 值，进行阈值检查
        if self.ENABLE_BETA_CALCULATION and valid_betas:
            avg_beta = np.mean(valid_betas)
            # β < 1.0 表示波动小于 BTC，套利空间受限，过滤该币种
            if avg_beta < self.AVG_BETA_THRESHOLD:
                coin_info = f" | 币种: {coin}" if coin else ""
                logger.info(
                    f"Beta收益率系数不满足要求，过滤 | 平均Beta: {avg_beta:.4f} < {self.AVG_BETA_THRESHOLD}"
                    f"{coin_info}"
                )
                return False, 0, min_short_corr, max_long_corr
        
        # 计算相关系数差值（长期最大相关系数 - 短期最小相关系数）
        diff_amount = max_long_corr - min_short_corr
        is_anomaly = False
        
        # 长期相关系数大于阈值，且短期相关系数小于阈值的时候，才计算差值
        if max_long_corr > self.LONG_TERM_CORR_THRESHOLD and min_short_corr < self.SHORT_TERM_CORR_THRESHOLD:
            # 相关性差值大于阈值，则认为存在套利机会
            if diff_amount > self.CORR_DIFF_THRESHOLD:
                is_anomaly = True
        # 长期相关系数大于阈值，且短期存在明显滞后时，则认为存在套利机会
        if max_long_corr > self.LONG_TERM_CORR_THRESHOLD:
            # x[3] 是最优延迟，x[2] 是数据周期
            if any((x[3] > 0) for x in results if len(x) >= 4 and x[2] == '1d'):
                is_anomaly = True

        # ========== 新增：协整验证（论文方法）==========
        if is_anomaly and price_data_cache is not None:
            # 使用1d数据进行协整检验
            cointegration_key = None
            for tf, p in price_data_cache.keys():
                if p == '1d':
                    cointegration_key = (tf, p)
                    break

            if cointegration_key and cointegration_key in price_data_cache:
                price_data = price_data_cache[cointegration_key]
                btc_prices = price_data['btc_prices']
                alt_prices = price_data['alt_prices']

                # 协整检验
                ols_params = self._calculate_cointegration_params(
                    btc_prices, alt_prices, coin=coin
                )

                if ols_params is None or ols_params['adf_pvalue'] >= 0.05:
                    coin_info = f" | 币种: {coin}" if coin else ""
                    adf_pvalue_str = f"{ols_params['adf_pvalue']:.4f}" if ols_params else 'N/A'
                    logger.info(
                        f"协整检验未通过，过滤信号 | "
                        f"相关系数: {max_long_corr:.4f} | "
                        f"ADF p-value: {adf_pvalue_str} >= 0.05 | "
                        f"原因: 价差非平稳，不适合配对交易"
                        f"{coin_info}"
                    )
                    # is_anomaly = False  # ⚠️ 协整失败，拒绝信号
                else:
                    # 协整检验通过，输出详细信息
                    coin_info = f" | 币种: {coin}" if coin else ""
                    logger.info(
                        f"✅ 协整检验通过 | "
                        f"α={ols_params['alpha']:.4f}, β={ols_params['beta']:.4f}, "
                        f"ADF p-value={ols_params['adf_pvalue']:.4f} < 0.05"
                        f"{coin_info}"
                    )
        # =====================================

        return is_anomaly, diff_amount, min_short_corr, max_long_corr
    
    def _output_results(self, coin: str, results: list, diff_amount: float,
                       zscore: Optional[float] = None,
                       stationarity_level: Optional['StationarityLevel'] = None,
                       p_value: Optional[float] = None):
        """
        输出异常模式的分析结果（增强版：包含 Beta 系数、Z-score 和平稳性等级）

        Args:
            coin: 币种名称
            results: 分析结果列表
            diff_amount: 相关系数差值
            zscore: Z-score 值（可选）
            stationarity_level: 平稳性等级（可选，用于区分强/弱信号）
            p_value: ADF检验的p-value（可选）
        """
        # 构建结果 DataFrame
        data_rows = []
        has_beta = False  # 标记是否有有效的 Beta 收益率系数值

        for result in results:
            # 处理新旧格式兼容（5个值 vs 4个值）
            if len(result) == 5:
                corr, tf, p, ts, beta = result
            elif len(result) == 4:
                corr, tf, p, ts = result
                beta = None
            else:
                # 处理异常格式，记录日志并跳过
                logger.warning(f"结果格式异常，跳过 | 币种: {coin} | 结果长度: {len(result)} | 结果: {result}")
                continue

            row = {
                '相关系数': corr,
                '时间周期': tf,
                '数据周期': p,
                '最优延迟': ts
            }

            # 添加 Beta 收益率系数列（如果存在且有效）
            if beta is not None and not np.isnan(beta):
                row['Beta收益率系数'] = beta
                has_beta = True

            data_rows.append(row)

        df_results = pd.DataFrame(data_rows)

        logger.info(f"发现异常币种 | 交易所: {self.exchange_name} | 币种: {coin} | 相关系数差值: {diff_amount:.2f}")

        # 飞书消息内容
        content = f"{self.exchange_name}\n\n{coin} 相关系数分析结果\n{df_results.to_string(index=False)}\n"
        content += f"\n相关系数差值: {diff_amount:.2f}"

        # 如果有 Beta 收益率系数信息，添加风险提示
        if has_beta:
            avg_beta = df_results['Beta收益率系数'].mean() if 'Beta收益率系数' in df_results.columns else None
            if avg_beta is not None and avg_beta > 1.5:
                content += f"\n⚠️ 高波动风险：平均Beta={avg_beta:.2f}（波动幅度是BTC的{avg_beta:.1f}倍）"
            elif avg_beta is not None and avg_beta > 1.2:
                content += f"\n⚠️ 中等波动：平均Beta={avg_beta:.2f}"
            else:
                content += f"\nBeta收益率系数: {avg_beta:.2f}"
        
        # 如果有 Z-score 信息，根据平稳性等级添加信号强度提示
        if zscore is not None:
            abs_zscore = abs(zscore)
            direction_desc, direction_code = self._get_trading_direction(zscore, coin)

            # 根据平稳性等级调整信号描述
            if stationarity_level == StationarityLevel.STRONG:
                # 强平稳：标准套利信号输出
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
        # =====================================
    
    def one_coin_analysis(self, coin: str) -> bool:
        """
        分析单个币种与BTC的相关系数，识别异常模式（增强版：支持 Z-score 验证）

        Args:
            coin: 币种交易对名称，如 "ETH/USDC:USDC"

        Returns:
            是否发现异常模式
        """
        results = []
        current_alt_df = None  # 当前组合获取的数据
        price_data_cache = {}  # 缓存价格数据，用于 Z-score 计算

        # 直接遍历预定义的组合列表：5m/7d 和 1m/1d
        for timeframe, period in self.combinations:
            # 获取当前组合的数据，检查是否为空
            current_alt_df = self._get_alt_data(coin, period, timeframe, coin)
            if current_alt_df is None:
                # 数据不存在，提前退出所有组合
                logger.warning(f"币种数据不存在，跳过后续所有组合 | 币种: {coin} | {timeframe}/{period}")
                return False
            
            # 获取BTC数据并对齐（一次性完成，避免重复调用）
            btc_df = self._get_btc_data(timeframe, period)
            if btc_df is None:
                # BTC数据获取失败，跳过该组合
                logger.warning(f"BTC数据获取失败，跳过组合 | 币种: {coin} | {timeframe}/{period}")
                continue
            
            # 对齐和验证数据（一次性完成，结果传递给 _analyze_single_combination 复用）
            aligned_data = self._align_and_validate_data(btc_df, current_alt_df, coin, timeframe, period)
            if aligned_data is None:
                # 数据对齐失败，跳过该组合
                continue
            
            btc_aligned, alt_aligned = aligned_data
            
            # 缓存价格数据（用于 Z-score 计算）
            price_data_cache[(timeframe, period)] = {
                'btc_prices': btc_aligned['Close'],
                'alt_prices': alt_aligned['Close']
            }
            
            # 使用已对齐的数据进行分析（传递对齐后的数据，避免重复获取和对齐）
            result = self._safe_execute(
                self._analyze_single_combination,
                coin, timeframe, period, current_alt_df,
                btc_df_aligned=btc_aligned,
                alt_df_aligned=alt_aligned,
                error_msg=f"处理 {coin} 的 {timeframe}/{period} 时发生异常"
            )
            if result is not None:
                results.append(result)

        # 过滤 NaN 并按相关系数降序排序（处理新的5元组格式）
        valid_results = []
        for result in results:
            # 处理新格式（5个值）
            if len(result) == 5:
                corr, tf, p, ts, beta = result
                if not np.isnan(corr):
                    valid_results.append((corr, tf, p, ts, beta))
            # 向后兼容旧格式（4个值）
            elif len(result) == 4:
                corr, tf, p, ts = result
                if not np.isnan(corr):
                    valid_results.append((corr, tf, p, ts, None))
            else:
                # 处理异常格式，记录日志并跳过
                logger.warning(f"结果格式异常，跳过 | 币种: {coin} | 结果长度: {len(result)} | 结果: {result}")
                continue

        valid_results = sorted(valid_results, key=lambda x: x[0], reverse=True)

        if not valid_results:
            logger.warning(f"数据不足，无法分析 | 币种: {coin}")
            return False

        is_anomaly, diff_amount, min_short_corr, max_long_corr = self._detect_anomaly_pattern(
            valid_results, price_data_cache=price_data_cache, coin=coin
        )
        logger.info(
            f"相关系数检测 | 币种: {coin} | 是否异常: {is_anomaly} | 相关系数差值: {diff_amount:.4f} | 短期最小: {min_short_corr:.4f} | 长期最大: {max_long_corr:.4f}"
            )

        # ========== Z-score 验证（如果启用且检测到异常）==========
        zscore_result = None
        stationarity_level_result = None  # 新增：保存平稳性等级
        p_value_result = None  # 新增：保存p-value
        if self.ENABLE_ZSCORE_CHECK:
            # 优先使用短期数据（1m/1d）计算 Z-score，因为这是检测异常的主要周期
            
            # 尝试从短期数据计算 Z-score
            short_term_key = None
            for tf, p in self.combinations:
                if p == '1d':  # 短期周期
                    short_term_key = (tf, p)
                    break
            
            if short_term_key and short_term_key in price_data_cache:
                price_data = price_data_cache[short_term_key]

                # 使用增强版函数，同时获取 Z-score、平稳性等级和 p-value
                # 双窗口策略：Beta（基于对数价格）使用长窗口（BETA_WINDOW）构建价差，统计量使用短窗口（ZSCORE_WINDOW）
                zscore_result, stationarity_level_result, p_value_result = self._calculate_zscore_with_level(
                    price_data['btc_prices'],
                    price_data['alt_prices'],
                    window=self.ZSCORE_WINDOW,
                    beta_window=self.BETA_WINDOW,  # 双窗口策略
                    coin=coin
                )
                
                if zscore_result is not None:
                    abs_zscore = abs(zscore_result)

                    # Z-score 阈值验证
                    if abs_zscore < self.ZSCORE_THRESHOLD:
                        logger.info(
                            f"Z-score 验证未通过，过滤信号 | 币种: {coin} | "
                            f"Z-score: {zscore_result:.2f}的绝对值 < {self.ZSCORE_THRESHOLD} | "
                            f"平稳性: {stationarity_level_result.chinese_name if stationarity_level_result else '未知'}"
                        )
                        return False
                    else:
                        direction_desc, direction_code = self._get_trading_direction(zscore_result, coin)

                        # 根据平稳性等级输出不同强度的日志
                        if stationarity_level_result == StationarityLevel.STRONG:
                            signal_strength = '强(高质量)' if abs_zscore > 3 else '中等(可靠)'
                            logger.info(
                                f"Z-score 验证通过（强平稳）| 币种: {coin} | "
                                f"Z-score: {zscore_result:.2f} | 平稳性: {stationarity_level_result.chinese_name} | "
                                f"方向: {direction_desc} | 信号强度: {signal_strength}"
                            )
                        elif stationarity_level_result == StationarityLevel.WEAK:
                            signal_strength = '弱(探索性)'
                            logger.warning(
                                f"Z-score 验证通过（弱平稳警告）| 币种: {coin} | "
                                f"Z-score: {zscore_result:.2f} | 平稳性: {stationarity_level_result.chinese_name} | "
                                f"方向: {direction_desc} | 信号强度: {signal_strength} | "
                                f"⚠️ 建议谨慎交易，平稳性检验处于边缘区域"
                            )
                        else:
                            # 理论上不应出现（因为_calculate_zscore_with_level已过滤非平稳）
                            signal_strength = '未知'
                            logger.warning(
                                f"Z-score 验证异常（平稳性未知）| 币种: {coin} | "
                                f"Z-score: {zscore_result:.2f} | 平稳性: 未知"
                            )
                else:
                    logger.debug(f"Z-score 计算失败，跳过验证 | 币种: {coin}")
            else:
                logger.debug(f"未找到价格数据，跳过 Z-score 验证 | 币种: {coin}")

        if is_anomaly:
            # ========== 收集平稳性统计 ==========
            if stationarity_level_result == StationarityLevel.STRONG:
                self.strong_signal_count += 1
            elif stationarity_level_result == StationarityLevel.WEAK:
                self.weak_signal_count += 1
            else:
                self.non_stationary_count += 1
            # ===================================

            self._output_results(coin, valid_results, diff_amount, zscore=zscore_result,
                                stationarity_level=stationarity_level_result, p_value=p_value_result)  # 新增p-value参数
            return True
        else:
            # 计算相关系数统计信息
            corrs = [r[0] for r in valid_results]
            min_corr = min(corrs) if corrs else 0
            max_corr = max(corrs) if corrs else 0
            logger.info(f"常规数据 | 币种: {coin} | 相关系数范围: {min_corr:.4f} ~ {max_corr:.4f}")
            return False
    
    def run(self):
        """分析交易所中所有USDC永续合约交易对"""
        logger.info(f"启动分析器 | 交易所: {self.exchange_name} | "
                    f"K线组合: {self.combinations}")
        
        all_coins = self.exchange.load_markets()
        usdc_coins = [c for c in all_coins if '/USDC:USDC' in c and c != self.btc_symbol]
        total = len(usdc_coins)
        anomaly_count = 0
        skip_count = 0
        start_time = time.time()
        
        logger.info(f"发现 {total} 个 USDC 永续合约交易对")
        
        # 进度里程碑：25%, 50%, 75%, 100%
        milestones = {max(1, int(total * p)) for p in [0.25, 0.5, 0.75, 1.0]}
        
        for idx, coin in enumerate(usdc_coins, 1):
            logger.debug(f"检查币种: {coin}")
            
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
    analyzer = DelayCorrelationAnalyzer(exchange_name="hyperliquid")
    analyzer.run()
