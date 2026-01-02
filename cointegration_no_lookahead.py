"""
协整参数计算 - 无前瞻偏差版本

提供两种解决look-ahead bias的方法：
1. calculate_cointegration_params_rolling: 完整滚动窗口（返回参数时间序列）
2. calculate_spread_rolling_simple: 简化版（仅返回价差序列）
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.stattools import adfuller
from typing import Optional
import logging

logger = logging.getLogger('HyperliquidAnalyzer')


def calculate_cointegration_params_rolling(
    base_prices: pd.Series,
    alt_prices: pd.Series,
    window: int = 100,
    min_periods: int = 50,
    coin: str = None
) -> Optional[dict]:
    """
    无前瞻偏差的协整参数计算（滚动窗口方法）✅

    对于每个时间点t，仅使用 [t-window+1, t] 的历史数据计算协整参数，
    完全避免使用未来信息，适用于实时交易场景。

    方法原理：
    - 对每个时间点进行独立的OLS回归
    - 使用当期窗口参数计算当期价差
    - 返回参数和价差的完整时间序列

    Args:
        base_prices: 基准币种价格序列（pandas Series）
        alt_prices: 山寨币价格序列（pandas Series）
        window: 滚动窗口大小（默认100）
        min_periods: 最小有效样本数（默认50）
        coin: 币种名称（可选，用于日志）

    Returns:
        dict: {
            'alpha_series': 截距时间序列（pd.Series），每个时间点的α值,
            'beta_series': 斜率时间序列（pd.Series），每个时间点的β值,
            'spread_series': 价差时间序列（pd.Series），无look-ahead的价差,
            'adf_pvalue': 最终窗口的ADF p值（float）
        }
        None: 如果计算失败

    Note:
        - ✅ 无look-ahead bias：每个时间点仅使用历史数据
        - 返回的时间序列长度 = len(base_prices) - min_periods + 1
        - 价差使用当期参数计算当期价差
        - 适用于回测和实时交易
        - ADF检验使用最后window个价差点

    示例：
        >>> params = calculate_cointegration_params_rolling(btc_prices, eth_prices, window=100)
        >>> current_alpha = params['alpha_series'].iloc[-1]  # 当前α
        >>> current_beta = params['beta_series'].iloc[-1]    # 当前β
        >>> current_spread = params['spread_series'].iloc[-1]  # 当前价差
        >>>
        >>> # 绘制参数时间序列
        >>> import matplotlib.pyplot as plt
        >>> params['beta_series'].plot(title='Beta over time')
        >>> plt.show()
    """
    try:
        # 1. 数据验证
        if len(base_prices) != len(alt_prices):
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.warning(f"滚动协整参数计算失败：数据长度不一致 | "
                          f"基准币种: {len(base_prices)}, ALT: {len(alt_prices)}"
                          f"{coin_info}")
            return None

        if len(base_prices) < min_periods:
            coin_info = f" | 币种: {coin}" if coin else ""
            logger.debug(f"滚动协整参数计算失败：数据点不足 | "
                        f"需要至少{min_periods}个点，实际{len(base_prices)}个"
                        f"{coin_info}")
            return None

        # 2. 计算对数价格
        log_base_series = np.log(base_prices)
        log_alt_series = np.log(alt_prices)

        # 3. 初始化结果存储
        alpha_list = []
        beta_list = []
        spread_list = []
        index_list = []

        # 4. 滚动窗口计算（关键：避免look-ahead bias）
        for i in range(len(base_prices)):
            # 确定窗口：[start_idx, end_idx)
            # end_idx = i + 1 表示包含当前时间点
            # start_idx = max(0, i - window + 1) 表示向前取window个点
            start_idx = max(0, i - window + 1)
            end_idx = i + 1

            # 检查是否满足最小样本要求
            current_window_size = end_idx - start_idx
            if current_window_size < min_periods:
                continue

            # 提取当前窗口数据（仅使用历史数据，不包含未来数据）
            window_log_base = log_base_series.iloc[start_idx:end_idx]
            window_log_alt = log_alt_series.iloc[start_idx:end_idx]

            # OLS回归：log_alt = α + β * log_base + ε
            X = window_log_base.values.reshape(-1, 1)
            y = window_log_alt.values

            model = LinearRegression()
            model.fit(X, y)

            alpha = model.intercept_
            beta = model.coef_[0]

            # 计算当前时间点的价差（使用当期窗口计算的参数）
            current_log_base = log_base_series.iloc[i]
            current_log_alt = log_alt_series.iloc[i]
            spread = current_log_alt - (alpha + beta * current_log_base)

            # 存储结果
            alpha_list.append(alpha)
            beta_list.append(beta)
            spread_list.append(spread)
            index_list.append(base_prices.index[i])

        # 5. 创建时间序列
        alpha_series = pd.Series(alpha_list, index=index_list)
        beta_series = pd.Series(beta_list, index=index_list)
        spread_series = pd.Series(spread_list, index=index_list)

        # 6. ADF检验最终窗口的价差平稳性
        if len(spread_list) >= 10:
            # 使用最后window个价差点进行ADF检验
            recent_spread = spread_series.iloc[-min(window, len(spread_series)):]
            adf_result = adfuller(recent_spread.values, autolag='AIC')
            adf_pvalue = adf_result[1]
        else:
            adf_pvalue = np.nan

        return {
            'alpha_series': alpha_series,
            'beta_series': beta_series,
            'spread_series': spread_series,
            'adf_pvalue': adf_pvalue
        }

    except Exception as e:
        coin_info = f" | 币种: {coin}" if coin else ""
        logger.debug(f"滚动OLS协整参数计算失败：{type(e).__name__}: {str(e)}{coin_info}", exc_info=True)
        return None


def calculate_spread_rolling_simple(
    base_prices: pd.Series,
    alt_prices: pd.Series,
    window: int = 100,
    coin: str = None
) -> Optional[pd.Series]:
    """
    简化版滚动OLS价差计算（仅返回价差序列）

    使用滚动窗口方法计算完整的价差时间序列，避免look-ahead bias。

    Args:
        base_prices: 基准币种价格序列
        alt_prices: 山寨币价格序列
        window: 滚动窗口大小（默认100）
        coin: 币种名称（可选，用于日志）

    Returns:
        价差时间序列（pd.Series），长度 = len(base_prices) - window + 1
        None: 如果计算失败

    Note:
        - ✅ 无look-ahead bias
        - 比 calculate_cointegration_params_rolling 更快（不存储alpha/beta）
        - 适用于只需要价差序列的场景

    示例：
        >>> spread = calculate_spread_rolling_simple(btc_prices, eth_prices, window=100)
        >>> zscore = (spread - spread.mean()) / spread.std()
    """
    try:
        if len(base_prices) != len(alt_prices) or len(base_prices) < window:
            return None

        log_base_series = np.log(base_prices)
        log_alt_series = np.log(alt_prices)

        spread_list = []
        index_list = []

        for i in range(window - 1, len(base_prices)):
            # 使用 [i-window+1, i+1) 的历史数据
            start_idx = i - window + 1
            end_idx = i + 1

            window_log_base = log_base_series.iloc[start_idx:end_idx]
            window_log_alt = log_alt_series.iloc[start_idx:end_idx]

            # OLS回归
            X = window_log_base.values.reshape(-1, 1)
            y = window_log_alt.values

            model = LinearRegression()
            model.fit(X, y)

            alpha = model.intercept_
            beta = model.coef_[0]

            # 计算当前价差
            current_log_base = log_base_series.iloc[i]
            current_log_alt = log_alt_series.iloc[i]
            spread = current_log_alt - (alpha + beta * current_log_base)

            spread_list.append(spread)
            index_list.append(base_prices.index[i])

        return pd.Series(spread_list, index=index_list)

    except Exception as e:
        coin_info = f" | 币种: {coin}" if coin else ""
        logger.debug(f"简化滚动价差计算失败：{type(e).__name__}: {str(e)}{coin_info}", exc_info=True)
        return None


def calculate_zscore_from_params(
    params_result: dict,
    zscore_window: int = 20,
    use_rolling_stats: bool = True
) -> Optional[pd.Series]:
    """
    使用 calculate_cointegration_params_rolling 的返回值计算 z-score

    Args:
        params_result: calculate_cointegration_params_rolling 返回的字典
        zscore_window: 用于计算统计量的滚动窗口大小（默认20）
        use_rolling_stats: 是否使用滚动窗口统计量（True）或全历史统计量（False）

    Returns:
        z-score 时间序列（pd.Series），与 spread_series 长度相同
        None: 如果计算失败

    Note:
        - ✅ 无 look-ahead bias：使用历史数据计算统计量
        - 默认使用滚动窗口统计量，更适合实时交易
        - 公式：z-score = (当前价差 - 历史均值) / 历史标准差

    示例：
        >>> params = calculate_cointegration_params_rolling(btc_prices, eth_prices, window=100)
        >>> zscore_series = calculate_zscore_from_params(params, zscore_window=20)
        >>> current_zscore = zscore_series.iloc[-1]  # 当前 z-score
        >>> 
        >>> # 判断交易信号
        >>> if current_zscore > 2.0:
        >>>     print("价差过高，考虑做空价差")
        >>> elif current_zscore < -2.0:
        >>>     print("价差过低，考虑做多价差")
    """
    try:
        if params_result is None:
            return None

        spread_series = params_result.get('spread_series')
        if spread_series is None or len(spread_series) == 0:
            return None

        zscore_list = []
        index_list = []

        if use_rolling_stats:
            # 方法1：滚动窗口统计量（推荐，更敏感）
            for i in range(len(spread_series)):
                # 确定用于计算统计量的窗口
                start_idx = max(0, i - zscore_window + 1)
                end_idx = i  # 不包含当前值，避免 look-ahead bias

                if end_idx <= start_idx:
                    # 数据不足，跳过
                    continue

                # 使用历史数据计算统计量
                historical_spread = spread_series.iloc[start_idx:end_idx]
                spread_mean = historical_spread.mean()
                spread_std = historical_spread.std()

                # 检查统计量有效性
                if pd.isna(spread_mean) or pd.isna(spread_std) or spread_std == 0:
                    continue

                # 计算当前 z-score
                current_spread = spread_series.iloc[i]
                zscore = (current_spread - spread_mean) / spread_std

                if not (np.isnan(zscore) or np.isinf(zscore)):
                    zscore_list.append(zscore)
                    index_list.append(spread_series.index[i])
        else:
            # 方法2：全历史统计量（更稳定，但可能不够敏感）
            for i in range(len(spread_series)):
                # 使用所有历史数据（不包括当前值）
                historical_spread = spread_series.iloc[:i]
                
                if len(historical_spread) < zscore_window:
                    # 数据不足，跳过
                    continue

                spread_mean = historical_spread.mean()
                spread_std = historical_spread.std()

                # 检查统计量有效性
                if pd.isna(spread_mean) or pd.isna(spread_std) or spread_std == 0:
                    continue

                # 计算当前 z-score
                current_spread = spread_series.iloc[i]
                zscore = (current_spread - spread_mean) / spread_std

                if not (np.isnan(zscore) or np.isinf(zscore)):
                    zscore_list.append(zscore)
                    index_list.append(spread_series.index[i])

        if len(zscore_list) == 0:
            return None

        return pd.Series(zscore_list, index=index_list)

    except Exception as e:
        logger.debug(f"Z-score 计算失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


def get_current_zscore(
    params_result: dict,
    zscore_window: int = 20
) -> Optional[float]:
    """
    获取当前时间点的 z-score（便捷函数）

    Args:
        params_result: calculate_cointegration_params_rolling 返回的字典
        zscore_window: 用于计算统计量的滚动窗口大小（默认20）

    Returns:
        当前 z-score 值（float）
        None: 如果计算失败

    示例：
        >>> params = calculate_cointegration_params_rolling(btc_prices, eth_prices, window=100)
        >>> current_zscore = get_current_zscore(params, zscore_window=20)
        >>> if current_zscore and current_zscore > 2.0:
        >>>     print(f"当前 z-score: {current_zscore:.2f}，价差偏高")
    """
    try:
        if params_result is None:
            return None

        spread_series = params_result.get('spread_series')
        if spread_series is None or len(spread_series) < zscore_window + 1:
            return None

        # 使用最近 zscore_window 个历史价差计算统计量（不包括当前值）
        historical_spread = spread_series.iloc[-(zscore_window + 1):-1]
        spread_mean = historical_spread.mean()
        spread_std = historical_spread.std()

        # 检查统计量有效性
        if pd.isna(spread_mean) or pd.isna(spread_std) or spread_std == 0:
            return None

        # 计算当前 z-score
        current_spread = spread_series.iloc[-1]
        zscore = (current_spread - spread_mean) / spread_std

        if np.isnan(zscore) or np.isinf(zscore):
            return None

        return float(zscore)

    except Exception as e:
        logger.debug(f"当前 Z-score 计算失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


def analyze_zscore_for_trading(
    zscore_series: pd.Series,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
    coin_pair: str = None
) -> dict:
    """
    分析 z-score 序列，生成交易信号和统计信息

    Args:
        zscore_series: z-score 时间序列
        entry_threshold: 入场阈值（默认 2.0，即 2σ）
        exit_threshold: 平仓阈值（默认 0.5）
        coin_pair: 交易对名称（可选，如 "AR/HYPE"）

    Returns:
        dict: {
            'current_zscore': 当前 z-score 值,
            'signal': 交易信号 ('long', 'short', 'exit_long', 'exit_short', 'hold'),
            'signal_description': 信号描述,
            'direction': 交易方向 ('long_alt_short_base', 'short_alt_long_base', 'neutral'),
            'stats': 统计信息字典,
            'extreme_periods': 极端值时间段
        }

    示例：
        >>> params = calculate_cointegration_params_rolling(btc_prices, eth_prices, window=100)
        >>> zscore_series = calculate_zscore_from_params(params, zscore_window=20)
        >>> trading_info = analyze_zscore_for_trading(zscore_series, entry_threshold=2.0)
        >>> 
        >>> print(f"当前信号: {trading_info['signal_description']}")
        >>> if trading_info['signal'] == 'long':
        >>>     print("执行做多价差交易")
    """
    try:
        if zscore_series is None or len(zscore_series) == 0:
            return None

        current_zscore = zscore_series.iloc[-1]
        
        # 1. 判断交易信号
        if current_zscore > entry_threshold:
            signal = 'short'
            signal_desc = f"做空价差 (z-score={current_zscore:.2f} > {entry_threshold})"
            direction = 'short_alt_long_base'
            direction_desc = "做空山寨币/做多基准币种"
        elif current_zscore < -entry_threshold:
            signal = 'long'
            signal_desc = f"做多价差 (z-score={current_zscore:.2f} < -{entry_threshold})"
            direction = 'long_alt_short_base'
            direction_desc = "做多山寨币/做空基准币种"
        elif abs(current_zscore) < exit_threshold:
            # 判断是否需要平仓（如果之前有持仓）
            if current_zscore > 0:
                signal = 'exit_short'
                signal_desc = f"平空仓 (z-score={current_zscore:.2f} 回归至 {exit_threshold} 以内)"
            else:
                signal = 'exit_long'
                signal_desc = f"平多仓 (z-score={current_zscore:.2f} 回归至 {exit_threshold} 以内)"
            direction = 'neutral'
            direction_desc = "无方向"
        else:
            signal = 'hold'
            signal_desc = f"观望 (z-score={current_zscore:.2f} 在 {exit_threshold} 和 {entry_threshold} 之间)"
            direction = 'neutral'
            direction_desc = "无方向"

        # 2. 统计信息
        stats = {
            'mean': float(zscore_series.mean()),
            'std': float(zscore_series.std()),
            'min': float(zscore_series.min()),
            'max': float(zscore_series.max()),
            'current': float(current_zscore),
            'extreme_count': len(zscore_series[abs(zscore_series) > entry_threshold]),
            'extreme_ratio': len(zscore_series[abs(zscore_series) > entry_threshold]) / len(zscore_series)
        }

        # 3. 找出极端值时间段
        extreme_mask = abs(zscore_series) > entry_threshold
        extreme_periods = zscore_series[extreme_mask]

        coin_info = f" ({coin_pair})" if coin_pair else ""

        return {
            'current_zscore': float(current_zscore),
            'signal': signal,
            'signal_description': signal_desc + coin_info,
            'direction': direction,
            'direction_description': direction_desc,
            'stats': stats,
            'extreme_periods': extreme_periods,
            'entry_threshold': entry_threshold,
            'exit_threshold': exit_threshold
        }

    except Exception as e:
        logger.debug(f"Z-score 交易分析失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None


def get_trading_signal(
    zscore_series: pd.Series,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5
) -> tuple:
    """
    快速获取交易信号（简化版）

    Args:
        zscore_series: z-score 时间序列
        entry_threshold: 入场阈值（默认 2.0）
        exit_threshold: 平仓阈值（默认 0.5）

    Returns:
        tuple: (信号代码, 信号描述, z-score值)
            - 信号代码: 'long', 'short', 'exit', 'hold'
            - 信号描述: 人类可读的描述
            - z-score值: 当前的 z-score

    示例：
        >>> zscore_series = calculate_zscore_from_params(params, zscore_window=20)
        >>> signal, desc, zscore = get_trading_signal(zscore_series)
        >>> if signal == 'long':
        >>>     print(f"执行做多: {desc}")
    """
    try:
        if zscore_series is None or len(zscore_series) == 0:
            return None, "数据不足", None

        current_zscore = zscore_series.iloc[-1]

        if current_zscore > entry_threshold:
            return 'short', f"做空价差 (z={current_zscore:.2f})", current_zscore
        elif current_zscore < -entry_threshold:
            return 'long', f"做多价差 (z={current_zscore:.2f})", current_zscore
        elif abs(current_zscore) < exit_threshold:
            return 'exit', f"平仓 (z={current_zscore:.2f})", current_zscore
        else:
            return 'hold', f"观望 (z={current_zscore:.2f})", current_zscore

    except Exception as e:
        logger.debug(f"交易信号获取失败：{type(e).__name__}: {str(e)}", exc_info=True)
        return None, "计算失败", None


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 模拟数据
    np.random.seed(42)
    n = 200

    # 生成协整的价格序列
    base = pd.Series(np.cumsum(np.random.randn(n)) + 100,
                     index=pd.date_range('2024-01-01', periods=n, freq='1H'))
    alt = np.exp(0.5 + 1.5 * np.log(base) + np.random.randn(n) * 0.02)
    alt = pd.Series(alt.values, index=base.index)

    print("=" * 60)
    print("方法1: 完整滚动窗口（返回参数时间序列）")
    print("=" * 60)

    params = calculate_cointegration_params_rolling(base, alt, window=100, min_periods=50)

    if params:
        print(f"\n返回的时间序列长度: {len(params['spread_series'])}")
        print(f"ADF p-value (最后100个价差): {params['adf_pvalue']:.4f}")
        print(f"\n最近5个时间点的参数:")
        print(f"Alpha: {params['alpha_series'].tail().values}")
        print(f"Beta: {params['beta_series'].tail().values}")
        print(f"Spread: {params['spread_series'].tail().values}")

        # 计算 Z-score
        print("\n" + "=" * 60)
        print("Z-score 计算示例")
        print("=" * 60)
        
        # 方法1：获取完整的 z-score 时间序列
        zscore_series = calculate_zscore_from_params(params, zscore_window=20, use_rolling_stats=True)
        if zscore_series is not None:
            print(f"\nZ-score 序列长度: {len(zscore_series)}")
            print(f"最近5个 Z-score: {zscore_series.tail().values}")
            print(f"当前 Z-score: {zscore_series.iloc[-1]:.4f}")
            
            # ========== 实际使用场景 ==========
            print("\n" + "-" * 60)
            print("场景1: 快速获取交易信号")
            print("-" * 60)
            signal, desc, zscore = get_trading_signal(zscore_series, entry_threshold=2.0, exit_threshold=0.5)
            print(f"信号: {signal} | {desc}")
            
            print("\n" + "-" * 60)
            print("场景2: 详细交易分析")
            print("-" * 60)
            trading_info = analyze_zscore_for_trading(zscore_series, entry_threshold=2.0, exit_threshold=0.5, coin_pair="ALT/BASE")
            if trading_info:
                print(f"当前 Z-score: {trading_info['current_zscore']:.4f}")
                print(f"交易信号: {trading_info['signal']}")
                print(f"信号描述: {trading_info['signal_description']}")
                print(f"交易方向: {trading_info['direction_description']}")
                print(f"\n统计信息:")
                print(f"  均值: {trading_info['stats']['mean']:.4f}")
                print(f"  标准差: {trading_info['stats']['std']:.4f}")
                print(f"  最小值: {trading_info['stats']['min']:.4f}")
                print(f"  最大值: {trading_info['stats']['max']:.4f}")
                print(f"  极端值次数: {trading_info['stats']['extreme_count']} ({trading_info['stats']['extreme_ratio']*100:.1f}%)")
            
            print("\n" + "-" * 60)
            print("场景3: 回测分析 - 遍历历史信号")
            print("-" * 60)
            # 模拟回测：遍历每个时间点
            signals_count = {'long': 0, 'short': 0, 'exit': 0, 'hold': 0}
            for i in range(20, len(zscore_series)):  # 从第20个点开始（确保有足够历史数据）
                historical_zscore = zscore_series.iloc[:i+1]
                signal, _, _ = get_trading_signal(historical_zscore, entry_threshold=2.0, exit_threshold=0.5)
                if signal:
                    signals_count[signal] = signals_count.get(signal, 0) + 1
            print(f"历史信号统计: {signals_count}")
            
            print("\n" + "-" * 60)
            print("场景4: 筛选交易机会")
            print("-" * 60)
            # 找出所有极端值时间点
            extreme_mask = abs(zscore_series) > 2.0
            extreme_periods = zscore_series[extreme_mask]
            if len(extreme_periods) > 0:
                print(f"发现 {len(extreme_periods)} 个交易机会 (|z-score| > 2.0):")
                for idx, zscore_val in extreme_periods.tail(5).items():
                    signal, desc, _ = get_trading_signal(pd.Series([zscore_val], index=[idx]), entry_threshold=2.0)
                    print(f"  {idx}: {desc}")
            else:
                print("当前无极端交易机会")

        # 方法2：直接获取当前 z-score（便捷方法）
        current_zscore = get_current_zscore(params, zscore_window=20)
        if current_zscore is not None:
            print(f"\n当前 Z-score (便捷方法): {current_zscore:.4f}")

        # 可视化参数演变
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(4, 1, figsize=(12, 10))

        params['alpha_series'].plot(ax=axes[0], title='Alpha over time')
        params['beta_series'].plot(ax=axes[1], title='Beta over time')
        params['spread_series'].plot(ax=axes[2], title='Spread over time')
        
        if zscore_series is not None:
            zscore_series.plot(ax=axes[3], title='Z-score over time', color='red')
            axes[3].axhline(y=2.0, color='r', linestyle='--', alpha=0.5, label='+2σ')
            axes[3].axhline(y=-2.0, color='r', linestyle='--', alpha=0.5, label='-2σ')
            axes[3].axhline(y=0, color='gray', linestyle='-', alpha=0.3)
            axes[3].legend()

        plt.tight_layout()
        plt.savefig('rolling_params.png')
        print("\n参数演变图已保存: rolling_params.png")

    print("\n" + "=" * 60)
    print("方法2: 简化版（仅返回价差序列）")
    print("=" * 60)

    spread = calculate_spread_rolling_simple(base, alt, window=100)

    if spread is not None:
        print(f"\n价差序列长度: {len(spread)}")
        print(f"价差统计: 均值={spread.mean():.4f}, 标准差={spread.std():.4f}")
        print(f"最近5个价差: {spread.tail().values}")

        # 计算Z-score
        zscore = (spread - spread.iloc[:-1].mean()) / spread.iloc[:-1].std()
        print(f"\n当前Z-score: {zscore.iloc[-1]:.2f}")

    print("\n" + "=" * 60)
    print("对比: 原始方法 vs 滚动窗口方法")
    print("=" * 60)

    # 原始方法（全历史）
    log_base_full = np.log(base)
    log_alt_full = np.log(alt)
    model_full = LinearRegression()
    model_full.fit(log_base_full.values.reshape(-1, 1), log_alt_full.values)

    alpha_full = model_full.intercept_
    beta_full = model_full.coef_[0]
    spread_full = log_alt_full - (alpha_full + beta_full * log_base_full)

    print(f"\n全历史OLS:")
    print(f"  Alpha: {alpha_full:.4f} (固定值)")
    print(f"  Beta: {beta_full:.4f} (固定值)")
    print(f"  价差均值: {spread_full.mean():.4f}")
    print(f"  价差标准差: {spread_full.std():.4f}")

    if params:
        print(f"\n滚动窗口OLS (最新值):")
        print(f"  Alpha: {params['alpha_series'].iloc[-1]:.4f} (动态更新)")
        print(f"  Beta: {params['beta_series'].iloc[-1]:.4f} (动态更新)")
        print(f"  价差均值: {params['spread_series'].mean():.4f}")
        print(f"  价差标准差: {params['spread_series'].std():.4f}")

        print(f"\n参数差异:")
        print(f"  Alpha差异: {abs(alpha_full - params['alpha_series'].iloc[-1]):.4f}")
        print(f"  Beta差异: {abs(beta_full - params['beta_series'].iloc[-1]):.4f}")
