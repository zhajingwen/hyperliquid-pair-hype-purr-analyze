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
from statsmodels.tsa.stattools import coint
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

def test_cointegration(
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
    计算价格比率的Z-score（标准化差异）

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
        is_cointegrated, pvalue = test_cointegration(base_klines, alt_klines, coint_significance)
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


# =====================================================
# 导出接口
# =====================================================

__all__ = [
    'prepare_price_series',
    'calculate_correlation',
    'test_cointegration',
    'calculate_zscore',
    'detect_anomaly',
    'analyze_pair'
]
