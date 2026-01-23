"""
分析核心模块 (Analysis Core)

提供共享的时序分析算法，包括：
- 相关性分析
- 协整检验
- Z-score计算
- 异常检测

被以下模块调用：
- realtime_kline_service.py (实时分析引擎)
- multi_coins.py (批量分析，如需改造)

Author: Claude Code
Date: 2026-01-19
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from statsmodels.tsa.stattools import coint, adfuller
import statsmodels.api as sm
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================================================
# 数据预处理
# =====================================================

def prepare_price_series(
    klines: List[Dict],
    price_col: str = 'close'
) -> pd.Series:
    """
    将K线数据转换为价格序列

    Args:
        klines: K线数据列表 [{"time": datetime, "close": float, ...}, ...]
        price_col: 价格字段名（默认 'close'）

    Returns:
        pd.Series: 价格序列，索引为时间
    """
    if not klines:
        return pd.Series()

    df = pd.DataFrame(klines)

    # 确保时间排序
    df = df.sort_values('time')

    # 设置时间索引
    df = df.set_index('time')

    return df[price_col]


# =====================================================
# 相关性分析
# =====================================================

def calculate_correlation(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    method: str = 'pearson'
) -> float:
    """
    计算两个币种的价格相关系数

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        method: 相关系数类型 ('pearson' | 'spearman' | 'kendall')

    Returns:
        float: 相关系数 (-1.0 ~ 1.0)
    """
    try:
        base_prices = prepare_price_series(base_klines)
        alt_prices = prepare_price_series(alt_klines)

        if len(base_prices) < 20 or len(alt_prices) < 20:
            logger.warning("数据点不足20个，无法计算可靠的相关性")
            return 0.0

        # 对齐时间索引
        aligned = pd.DataFrame({
            'base': base_prices,
            'alt': alt_prices
        }).dropna()

        if len(aligned) < 20:
            logger.warning("对齐后数据点不足20个")
            return 0.0

        # 计算相关系数
        correlation = aligned['base'].corr(aligned['alt'], method=method)

        return float(correlation)

    except Exception as e:
        logger.error(f"相关性计算失败: {e}")
        return 0.0


# =====================================================
# 协整检验
# =====================================================

def check_cointegration(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    significance_level: float = 0.05
) -> Tuple[bool, float]:
    """
    协整检验（Engle-Granger）

    检测两个价格序列是否存在长期均衡关系

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        significance_level: 显著性水平（默认0.05）

    Returns:
        (is_cointegrated, pvalue): 是否协整，p值
    """
    try:
        base_prices = prepare_price_series(base_klines)
        alt_prices = prepare_price_series(alt_klines)

        if len(base_prices) < 30 or len(alt_prices) < 30:
            logger.warning("数据点不足30个，协整检验不可靠")
            return False, 1.0

        # 对齐时间索引
        aligned = pd.DataFrame({
            'base': base_prices,
            'alt': alt_prices
        }).dropna()

        if len(aligned) < 30:
            logger.warning("对齐后数据点不足30个")
            return False, 1.0

        # Engle-Granger协整检验
        _, pvalue, _ = coint(aligned['base'], aligned['alt'])

        is_cointegrated = pvalue < significance_level

        return is_cointegrated, float(pvalue)

    except Exception as e:
        logger.error(f"协整检验失败: {e}")
        return False, 1.0


# =====================================================
# Z-score计算
# =====================================================

def calculate_zscore(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    window: Optional[int] = None
) -> float:
    """
    计算价格比率的Z-score（标准化差异）- 简单版本

    Z-score = (当前价格比率 - 均值) / 标准差

    注意：这是简单版本，用于向后兼容。推荐使用 calculate_zscore_ols 获取更准确的结果。

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        window: 滚动窗口大小（None = 使用全部数据）

    Returns:
        float: Z-score值
    """
    return calculate_zscore_simple(base_klines, alt_klines, window)


def calculate_zscore_simple(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    window: Optional[int] = None
) -> float:
    """
    简单Z-score计算（基于价格比率）

    Z-score = (当前价格比率 - 均值) / 标准差

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        window: 滚动窗口大小（None = 使用全部数据）

    Returns:
        float: Z-score值
    """
    try:
        base_prices = prepare_price_series(base_klines)
        alt_prices = prepare_price_series(alt_klines)

        if len(base_prices) < 30 or len(alt_prices) < 30:
            logger.warning("数据点不足30个，Z-score计算不可靠")
            return 0.0

        # 对齐时间索引
        aligned = pd.DataFrame({
            'base': base_prices,
            'alt': alt_prices
        }).dropna()

        if len(aligned) < 30:
            logger.warning("对齐后数据点不足30个")
            return 0.0

        # 计算价格比率
        ratio = aligned['alt'] / aligned['base']

        # 计算Z-score
        if window:
            mean = ratio.rolling(window=window).mean().iloc[-1]
            std = ratio.rolling(window=window).std().iloc[-1]
        else:
            mean = ratio.mean()
            std = ratio.std()

        if std == 0:
            logger.warning("标准差为0，无法计算Z-score")
            return 0.0

        current_ratio = ratio.iloc[-1]
        zscore = (current_ratio - mean) / std

        return float(zscore)

    except Exception as e:
        logger.error(f"Z-score计算失败: {e}")
        return 0.0


# =====================================================
# OLS 协整分析（高级方法）
# =====================================================

def _select_cointegration_model(
    alpha: float,
    alpha_pvalue: float
) -> Tuple[str, bool, str]:
    """
    智能协整模型选择

    根据α的显著性和绝对值大小选择最优模型：
    - |α| > 5 且显著 → 无α模型（跨资产类配对）
    - |α| < 2 且显著 → 标准EG模型（同类资产配对）
    - 其他 → 无α模型

    Args:
        alpha: OLS回归截距项
        alpha_pvalue: α的p值

    Returns:
        (model_type, use_alpha, model_reason): 模型类型、是否使用α、选择原因
    """
    if alpha_pvalue < 0.05 and abs(alpha) > 5:
        # α显著且绝对值很大 → 跨资产类配对（如NEAR/BTC）
        return "no_intercept_forced", False, f"|α|={abs(alpha):.1f}>5, 跨资产类配对"

    elif alpha_pvalue < 0.05 and abs(alpha) < 2:
        # α显著且绝对值较小 → 同类资产配对（如UNI/SUSHI）
        return "standard_EG", True, f"|α|={abs(alpha):.1f}<2, 同类资产配对"

    else:
        # α不显著或中等范围（2<=|α|<=5）
        if alpha_pvalue >= 0.05:
            reason = "α不显著"
        else:
            reason = f"|α|={abs(alpha):.1f}∈[2,5], 中等范围"
        return "no_intercept", False, reason


def calculate_cointegration_params_ols(
    base_klines: List[Dict],
    alt_klines: List[Dict]
) -> Optional[Dict]:
    """
    全量数据OLS协整参数计算（Engle-Granger两步法）

    使用全量数据计算OLS回归参数和ADF检验，适用于事后验证分析。

    注意：此方法存在 look-ahead bias，仅用于验证性分析，不适用于实时交易。
    实时交易请使用 calculate_cointegration_params_dual_window。

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据

    Returns:
        Dict: {
            'alpha': 截距项,
            'beta': 斜率,
            'spread': 价差序列,
            'adf_pvalue': ADF检验p值,
            'alpha_pvalue': α的p值,
            'beta_pvalue': β的p值,
            'rsquared': R²,
            'model_type': 模型类型,
            'use_alpha': 是否使用α,
            'model_reason': 模型选择原因
        } 或 None
    """
    try:
        base_prices = prepare_price_series(base_klines)
        alt_prices = prepare_price_series(alt_klines)

        # 数据验证
        if len(base_prices) != len(alt_prices):
            logger.warning(f"协整参数计算失败：数据长度不一致")
            return None

        if len(base_prices) < 10:
            logger.debug(f"协整参数计算失败：数据点不足10个")
            return None

        # 对齐时间索引
        aligned = pd.DataFrame({
            'base': base_prices,
            'alt': alt_prices
        }).dropna()

        if len(aligned) < 10:
            return None

        # 计算对数价格
        log_base_series = np.log(aligned['base'])
        log_alt_series = np.log(aligned['alt'])

        # statsmodels OLS回归：log_alt = α + β * log_base + ε
        X = sm.add_constant(log_base_series)
        model = sm.OLS(log_alt_series, X).fit()

        alpha = model.params.iloc[0]
        beta = model.params.iloc[1]
        alpha_pvalue = model.pvalues.iloc[0]
        beta_pvalue = model.pvalues.iloc[1]
        rsquared = model.rsquared

        # 智能模型选择
        model_type, use_alpha, model_reason = _select_cointegration_model(alpha, alpha_pvalue)

        # 计算价差
        if use_alpha:
            spread_ols = log_alt_series - (alpha + beta * log_base_series)
        else:
            spread_ols = log_alt_series - beta * log_base_series

        # ADF检验价差平稳性
        adf_result = adfuller(spread_ols.values, autolag='AIC')
        adf_pvalue = adf_result[1]

        logger.debug(
            f"OLS协整参数 | α={alpha:.4f} (p={alpha_pvalue:.4f}) | "
            f"β={beta:.4f} (p={beta_pvalue:.4f}) | R²={rsquared:.4f} | "
            f"模型: {model_type} | 原因: {model_reason} | ADF p={adf_pvalue:.4f}"
        )

        return {
            'alpha': alpha,
            'beta': beta,
            'spread': spread_ols,
            'adf_pvalue': adf_pvalue,
            'alpha_pvalue': alpha_pvalue,
            'beta_pvalue': beta_pvalue,
            'rsquared': rsquared,
            'model_type': model_type,
            'use_alpha': use_alpha,
            'model_reason': model_reason
        }

    except Exception as e:
        logger.debug(f"OLS协整参数计算失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


def calculate_cointegration_params_dual_window(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    beta_window: int = 100,
    zscore_window: int = 30
) -> Optional[Dict]:
    """
    双窗口策略OLS协整参数计算

    关键特性：
    - beta_window (100期): 用于稳定的OLS回归参数估计
    - zscore_window (30期): 用于敏感的均值回归检测
    - 避免 look-ahead bias：使用前 beta_window-1 个点计算OLS

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        beta_window: OLS回归窗口大小（默认100）
        zscore_window: Z-score计算窗口大小（默认30）

    Returns:
        Dict: {
            'alpha': 截距项,
            'beta': 斜率,
            'spread': 价差序列（用于Z-score计算）,
            'adf_pvalue': ADF检验p值,
            'alpha_pvalue': α的p值,
            'beta_pvalue': β的p值,
            'rsquared': R²,
            'model_type': 模型类型,
            'use_alpha': 是否使用α,
            'model_reason': 模型选择原因
        } 或 None
    """
    try:
        base_prices = prepare_price_series(base_klines)
        alt_prices = prepare_price_series(alt_klines)

        # 数据验证
        if len(base_prices) != len(alt_prices):
            logger.warning(f"双窗口OLS失败：数据长度不一致")
            return None

        data_window = max(beta_window, zscore_window)
        if len(base_prices) < data_window:
            logger.warning(f"双窗口OLS失败：数据点不足{data_window}个")
            return None

        # 对齐时间索引
        aligned = pd.DataFrame({
            'base': base_prices,
            'alt': alt_prices
        }).dropna()

        if len(aligned) < data_window:
            return None

        # 数据切片：取足够计算OLS和统计量的数据
        recent_base_full = aligned['base'].iloc[-data_window:]
        recent_alt_full = aligned['alt'].iloc[-data_window:]

        # OLS回归：使用前 beta_window-1 个点（避免 look-ahead bias）
        ols_base = recent_base_full.iloc[:-1]
        ols_alt = recent_alt_full.iloc[:-1]

        # 计算对数价格
        log_base_ols = np.log(ols_base)
        log_alt_ols = np.log(ols_alt)

        # statsmodels OLS回归
        X = sm.add_constant(log_base_ols)
        model = sm.OLS(log_alt_ols, X).fit()

        alpha = model.params.iloc[0]
        beta_ols = model.params.iloc[1]
        alpha_pvalue = model.pvalues.iloc[0]
        beta_pvalue = model.pvalues.iloc[1]
        rsquared = model.rsquared

        # 智能模型选择
        model_type, use_alpha, model_reason = _select_cointegration_model(alpha, alpha_pvalue)

        # 计算价差（用于ADF检验，使用全部beta_window期）
        log_base_full = np.log(recent_base_full)
        log_alt_full = np.log(recent_alt_full)

        if use_alpha:
            spread_full = log_alt_full - (alpha + beta_ols * log_base_full)
        else:
            spread_full = log_alt_full - beta_ols * log_base_full

        # ADF检验价差平稳性
        adf_result = adfuller(spread_full.values, autolag='AIC')
        adf_pvalue = adf_result[1]

        # 价差构建（用于Z-score计算：使用短窗口保持敏感度）
        recent_base = recent_base_full.iloc[-zscore_window:]
        recent_alt = recent_alt_full.iloc[-zscore_window:]
        log_base = np.log(recent_base)
        log_alt = np.log(recent_alt)

        if use_alpha:
            spread = log_alt - (alpha + beta_ols * log_base)
        else:
            spread = log_alt - beta_ols * log_base

        logger.debug(
            f"双窗口OLS | α={alpha:.4f} (p={alpha_pvalue:.4f}) | "
            f"β={beta_ols:.4f} (p={beta_pvalue:.4f}) | R²={rsquared:.4f} | "
            f"模型: {model_type} | 原因: {model_reason} | ADF p={adf_pvalue:.4f}"
        )

        return {
            'alpha': alpha,
            'beta': beta_ols,
            'spread': spread,  # 用于Z-score计算的价差序列
            'adf_pvalue': adf_pvalue,
            'alpha_pvalue': alpha_pvalue,
            'beta_pvalue': beta_pvalue,
            'rsquared': rsquared,
            'model_type': model_type,
            'use_alpha': use_alpha,
            'model_reason': model_reason
        }

    except Exception as e:
        logger.debug(f"双窗口OLS计算失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


def calculate_zscore_ols(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    window: int = 30,
    beta_window: int = 100,
    cointegration_result: Optional[Dict] = None
) -> Optional[float]:
    """
    基于OLS价差的Z-score计算（更科学的方法）

    公式：zscore = (current_spread - spread_mean) / spread_std

    其中 spread 来自 OLS 回归残差，而非简单价格比率。

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        window: Z-score统计窗口大小（默认30）
        beta_window: OLS回归窗口大小（默认100）
        cointegration_result: 预计算的协整结果（可选）

    Returns:
        float: Z-score值，失败返回None
    """
    try:
        # 如果未提供协整结果，自动计算
        if cointegration_result is None:
            cointegration_result = calculate_cointegration_params_dual_window(
                base_klines, alt_klines, beta_window, window
            )
            if cointegration_result is None:
                return None

        # 从协整结果中提取价差序列
        spread = cointegration_result.get('spread')
        if spread is None or len(spread) < 2:
            logger.warning("价差序列无效，无法计算Z-score")
            return None

        # 计算统计量（使用前N-1期避免样本偏差）
        spread_mean = spread.iloc[:-1].mean()
        spread_std = spread.iloc[:-1].std()
        current_spread = spread.iloc[-1]

        # 验证统计量有效性
        if pd.isna(spread_mean) or pd.isna(spread_std):
            logger.warning("统计量包含NaN")
            return None

        if spread_std == 0 or np.isnan(spread_std):
            logger.warning("标准差为0或NaN")
            return None

        # 计算当前Z-score
        zscore = (current_spread - spread_mean) / spread_std

        if np.isnan(zscore) or np.isinf(zscore):
            logger.warning("Z-score为NaN或Inf")
            return None

        return float(zscore)

    except Exception as e:
        logger.warning(f"OLS Z-score计算失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


# =====================================================
# 异常检测
# =====================================================

def detect_anomaly(
    zscore: float,
    threshold: float = 2.0
) -> Tuple[bool, str]:
    """
    基于Z-score的异常检测

    判断规则:
    - |zscore| > threshold: 异常信号
    - zscore > threshold: 目标币种相对高估 → 做空方向
    - zscore < -threshold: 目标币种相对低估 → 做多方向

    Args:
        zscore: Z-score值
        threshold: 异常阈值（默认2.0，即2倍标准差）

    Returns:
        (is_anomaly, direction): 是否异常，交易方向
    """
    abs_zscore = abs(zscore)

    if abs_zscore < threshold:
        return False, 'none'

    # 确定交易方向
    if zscore > threshold:
        direction = 'short'  # 做空（目标币种高估，价格回归预期下跌）
    else:
        direction = 'long'   # 做多（目标币种低估，价格回归预期上涨）

    return True, direction


# =====================================================
# 综合分析
# =====================================================

def analyze_pair(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    corr_threshold: float = 0.5,
    coint_significance: float = 0.05,
    zscore_threshold: float = 2.0
) -> Dict:
    """
    综合分析两个币种的配对交易机会

    流程:
    1. 相关性检测 → 如果相关性<阈值，直接返回
    2. 协整检验 → 如果不协整，直接返回
    3. Z-score计算 → 计算当前偏离度
    4. 异常检测 → 判断是否存在套利机会

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        corr_threshold: 相关性阈值（默认0.5）
        coint_significance: 协整检验显著性水平（默认0.05）
        zscore_threshold: Z-score异常阈值（默认2.0）

    Returns:
        Dict: 分析结果
            {
                'correlation': float,
                'cointegration_passed': bool,
                'adf_pvalue': float,
                'zscore': float,
                'is_anomaly': bool,
                'trading_direction': str,
                'signal_strength': str
            }
    """
    result = {
        'correlation': 0.0,
        'cointegration_passed': False,
        'adf_pvalue': 1.0,
        'zscore': 0.0,
        'is_anomaly': False,
        'trading_direction': 'none',
        'signal_strength': 'none'
    }

    try:
        # 1. 相关性分析
        correlation = calculate_correlation(base_klines, alt_klines)
        result['correlation'] = correlation

        if correlation < corr_threshold:
            logger.debug(f"相关性不足: {correlation:.3f} < {corr_threshold}")
            return result

        # 2. 协整检验
        is_cointegrated, pvalue = check_cointegration(base_klines, alt_klines, coint_significance)
        result['cointegration_passed'] = is_cointegrated
        result['adf_pvalue'] = pvalue

        if not is_cointegrated:
            logger.debug(f"协整检验失败: p-value={pvalue:.4f}")
            return result

        # 3. Z-score计算
        zscore = calculate_zscore(base_klines, alt_klines)
        result['zscore'] = zscore

        # 4. 异常检测
        is_anomaly, direction = detect_anomaly(zscore, zscore_threshold)
        result['is_anomaly'] = is_anomaly
        result['trading_direction'] = direction

        # 5. 信号强度评估
        if is_anomaly:
            abs_zscore = abs(zscore)
            if abs_zscore > 2.5:
                result['signal_strength'] = 'strong'
            elif abs_zscore > 2.0:
                result['signal_strength'] = 'medium'
            else:
                result['signal_strength'] = 'weak'

        return result

    except Exception as e:
        logger.error(f"综合分析失败: {e}", exc_info=True)
        return result


def analyze_pair_advanced(
    base_klines: List[Dict],
    alt_klines: List[Dict],
    beta_window: int = 100,
    zscore_window: int = 30,
    zscore_threshold: float = 2.0,
    enable_health_monitor: bool = True,
    stats_period_key: Optional[Tuple[str, str]] = None
) -> Dict:
    """
    高级配对分析（完整算法）

    流程：
    1. 数据预处理和相关性分析
    2. Old方法：全量OLS协整分析
    3. New方法：双窗口OLS协整分析
    4. 健康监控（如果启用且周期为4h/60d）
    5. Z-score计算（基于OLS价差）
    6. 异常检测

    Args:
        base_klines: 基础币种K线数据
        alt_klines: 目标币种K线数据
        beta_window: OLS回归窗口大小（默认100）
        zscore_window: Z-score计算窗口大小（默认30）
        zscore_threshold: Z-score异常阈值（默认2.0）
        enable_health_monitor: 是否启用健康监控（默认True）
        stats_period_key: 统计周期键，如 ('4h', '60d')，用于判断是否启用健康监控

    Returns:
        Dict: {
            'correlation': float,
            'cointegration_old': {
                'passed': bool,
                'alpha': float,
                'beta': float,
                'adf_pvalue': float,
                'model_type': str,
                'use_alpha': bool
            },
            'cointegration_new': {
                'passed': bool,
                'alpha': float,
                'beta': float,
                'adf_pvalue': float,
                'model_type': str,
                'use_alpha': bool
            },
            'health_monitor': {
                'long_window': {...},
                'short_window': {...},
                'score_diff': float
            } or None,
            'zscore': float,
            'is_anomaly': bool,
            'trading_direction': str,
            'signal_strength': str
        }
    """
    result = {
        'correlation': 0.0,
        'cointegration_old': {
            'passed': False,
            'alpha': None,
            'beta': None,
            'adf_pvalue': 1.0,
            'model_type': None,
            'use_alpha': False
        },
        'cointegration_new': {
            'passed': False,
            'alpha': None,
            'beta': None,
            'adf_pvalue': 1.0,
            'model_type': None,
            'use_alpha': False
        },
        'health_monitor': None,
        'zscore': 0.0,
        'is_anomaly': False,
        'trading_direction': 'none',
        'signal_strength': 'none'
    }

    try:
        # 1. 相关性分析
        correlation = calculate_correlation(base_klines, alt_klines)
        result['correlation'] = correlation

        # 2. Old方法：全量OLS协整分析
        coint_old = calculate_cointegration_params_ols(base_klines, alt_klines)
        if coint_old:
            result['cointegration_old'] = {
                'passed': coint_old['adf_pvalue'] < 0.05,
                'alpha': coint_old['alpha'],
                'beta': coint_old['beta'],
                'adf_pvalue': coint_old['adf_pvalue'],
                'model_type': coint_old['model_type'],
                'use_alpha': coint_old['use_alpha'],
                'alpha_pvalue': coint_old.get('alpha_pvalue'),
                'beta_pvalue': coint_old.get('beta_pvalue'),
                'rsquared': coint_old.get('rsquared')
            }

        # 3. New方法：双窗口OLS协整分析
        coint_new = calculate_cointegration_params_dual_window(
            base_klines, alt_klines, beta_window, zscore_window
        )
        if coint_new:
            result['cointegration_new'] = {
                'passed': coint_new['adf_pvalue'] < 0.05,
                'alpha': coint_new['alpha'],
                'beta': coint_new['beta'],
                'adf_pvalue': coint_new['adf_pvalue'],
                'model_type': coint_new['model_type'],
                'use_alpha': coint_new['use_alpha'],
                'alpha_pvalue': coint_new.get('alpha_pvalue'),
                'beta_pvalue': coint_new.get('beta_pvalue'),
                'rsquared': coint_new.get('rsquared')
            }

        # 4. 健康监控（仅在4h/60d周期启用）
        if enable_health_monitor and stats_period_key:
            timeframe, window_str = stats_period_key
            if timeframe == '4h' and window_str == '60d':
                try:
                    from utils.coingetation_more_check import CointegrationHealthMonitor

                    base_prices = prepare_price_series(base_klines)
                    alt_prices = prepare_price_series(alt_klines)

                    # 对齐数据
                    aligned = pd.DataFrame({
                        'base': base_prices,
                        'alt': alt_prices
                    }).dropna()

                    if len(aligned) >= 200:
                        log_base_series = np.log(aligned['base'])
                        log_alt_series = np.log(aligned['alt'])

                        # 长期监控（200期 = 33天）
                        monitor_long = CointegrationHealthMonitor(
                            window=200,
                            enable_diagnostics=True,
                            state_thresholds=(18, 14, 10)
                        )
                        result_long = monitor_long.update(log_base_series, log_alt_series)

                        # 短期监控（100期 = 16.7天）
                        monitor_short = CointegrationHealthMonitor(
                            window=100,
                            enable_diagnostics=True,
                            state_thresholds=(18, 14, 10)
                        )
                        result_short = monitor_short.update(log_base_series, log_alt_series)

                        result['health_monitor'] = {
                            'long_window': result_long,
                            'short_window': result_short,
                            'score_diff': result_long['health_score'] - result_short['health_score']
                        }

                        logger.debug(
                            f"健康监控 | 长期得分: {result_long['health_score']:.1f} | "
                            f"短期得分: {result_short['health_score']:.1f} | "
                            f"状态: {result_long['state']} / {result_short['state']}"
                        )

                except Exception as e:
                    logger.warning(f"健康监控失败：{e}")

        # 5. Z-score计算（基于OLS价差）
        if coint_new:
            zscore = calculate_zscore_ols(
                base_klines,
                alt_klines,
                window=zscore_window,
                beta_window=beta_window,
                cointegration_result=coint_new
            )
            if zscore is not None:
                result['zscore'] = zscore

        # 6. 异常检测
        is_anomaly, direction = detect_anomaly(result['zscore'], zscore_threshold)
        result['is_anomaly'] = is_anomaly
        result['trading_direction'] = direction

        # 7. 信号强度评估
        if is_anomaly:
            abs_zscore = abs(result['zscore'])
            if abs_zscore > 2.5:
                result['signal_strength'] = 'strong'
            elif abs_zscore > 2.0:
                result['signal_strength'] = 'medium'
            else:
                result['signal_strength'] = 'weak'

        return result

    except Exception as e:
        logger.error(f"高级配对分析失败: {e}", exc_info=True)
        return result


# =====================================================
# 导出接口
# =====================================================

__all__ = [
    # 数据预处理
    'prepare_price_series',

    # 相关性分析
    'calculate_correlation',

    # 协整检验
    'check_cointegration',  # 旧版简单协整
    'calculate_cointegration_params_ols',  # 新增：全量OLS
    'calculate_cointegration_params_dual_window',  # 新增：双窗口OLS

    # Z-score计算
    'calculate_zscore',  # 保留（简单版）
    'calculate_zscore_simple',  # 显式简单版
    'calculate_zscore_ols',  # 新增：OLS版

    # 异常检测
    'detect_anomaly',

    # 综合分析
    'analyze_pair',  # 保留（向后兼容）
    'analyze_pair_advanced'  # 新增：完整版
]
