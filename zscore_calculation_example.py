"""
使用 calculate_cointegration_params_rolling 计算 Z-Score 的示例
"""

import numpy as np
import pandas as pd
from cointegration_no_lookahead import calculate_cointegration_params_rolling


def calculate_zscore_methods(base_prices, alt_prices, window=100):
    """
    展示三种不同的z-score计算方法

    Args:
        base_prices: 基准币种价格序列
        alt_prices: 山寨币价格序列
        window: 滚动窗口大小

    Returns:
        dict: 包含不同方法计算的z-score
    """
    # 1. 获取协整参数和价差
    params = calculate_cointegration_params_rolling(
        base_prices,
        alt_prices,
        window=window,
        min_periods=50
    )

    if params is None:
        return None

    spread = params['spread_series']

    # 方法1: 无前瞻偏差 - 使用历史数据(不含当前点)
    # 这是回测中最严格的方法
    zscore_no_lookahead = pd.Series(index=spread.index, dtype=float)
    for i in range(len(spread)):
        if i == 0:
            zscore_no_lookahead.iloc[i] = 0.0
        else:
            historical_spread = spread.iloc[:i]  # 只使用之前的数据
            mean = historical_spread.mean()
            std = historical_spread.std()
            zscore_no_lookahead.iloc[i] = (spread.iloc[i] - mean) / std if std != 0 else 0.0

    # 方法2: 滚动窗口z-score
    # 使用固定窗口的历史统计量
    zscore_rolling = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()

    # 方法3: 固定窗口(使用最近window个点)
    zscore_fixed_window = pd.Series(index=spread.index, dtype=float)
    for i in range(len(spread)):
        start_idx = max(0, i - window + 1)
        window_spread = spread.iloc[start_idx:i+1]
        mean = window_spread.mean()
        std = window_spread.std()
        zscore_fixed_window.iloc[i] = (spread.iloc[i] - mean) / std if std != 0 else 0.0

    # 方法4: 全历史z-score (仅用于分析,包含look-ahead bias)
    zscore_full = (spread - spread.mean()) / spread.std()

    return {
        'params': params,
        'spread': spread,
        'zscore_no_lookahead': zscore_no_lookahead,
        'zscore_rolling': zscore_rolling,
        'zscore_fixed_window': zscore_fixed_window,
        'zscore_full': zscore_full
    }


def get_current_zscore(base_prices, alt_prices, window=100, zscore_window=100):
    """
    获取当前时刻的z-score (实盘交易场景)

    Args:
        base_prices: 基准币种价格序列
        alt_prices: 山寨币价格序列
        window: 协整参数计算窗口
        zscore_window: z-score统计量计算窗口

    Returns:
        float: 当前z-score值
    """
    params = calculate_cointegration_params_rolling(
        base_prices,
        alt_prices,
        window=window,
        min_periods=50
    )

    if params is None:
        return None

    spread = params['spread_series']

    # 使用最近zscore_window个点计算统计量
    if len(spread) < zscore_window:
        recent_spread = spread
    else:
        recent_spread = spread.iloc[-zscore_window:]

    mean = recent_spread.mean()
    std = recent_spread.std()
    current_spread = spread.iloc[-1]

    if std == 0:
        return 0.0

    current_zscore = (current_spread - mean) / std

    return current_zscore


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 生成模拟数据
    np.random.seed(42)
    n = 300

    base = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range('2024-01-01', periods=n, freq='1H')
    )
    alt = np.exp(0.5 + 1.5 * np.log(base) + np.random.randn(n) * 0.02)
    alt = pd.Series(alt.values, index=base.index)

    print("=" * 70)
    print("Z-Score 计算示例")
    print("=" * 70)

    # 方法对比
    results = calculate_zscore_methods(base, alt, window=100)

    if results:
        print("\n各方法计算的最近5个z-score:")
        print("-" * 70)

        for method_name, zscore_series in [
            ("无前瞻偏差 (推荐回测)", results['zscore_no_lookahead']),
            ("滚动窗口", results['zscore_rolling']),
            ("固定窗口", results['zscore_fixed_window']),
            ("全历史 (含bias)", results['zscore_full'])
        ]:
            print(f"\n{method_name}:")
            print(f"  最近5个值: {zscore_series.tail().values}")
            print(f"  当前值: {zscore_series.iloc[-1]:.4f}")
            print(f"  均值: {zscore_series.mean():.4f}, 标准差: {zscore_series.std():.4f}")

    print("\n" + "=" * 70)
    print("实盘交易场景 - 获取当前z-score")
    print("=" * 70)

    current_z = get_current_zscore(base, alt, window=100, zscore_window=100)

    if current_z is not None:
        print(f"\n当前z-score: {current_z:.4f}")

        # 交易信号
        if current_z > 2:
            print("📉 信号: 价差过高,考虑做空价差 (买base,卖alt)")
        elif current_z < -2:
            print("📈 信号: 价差过低,考虑做多价差 (卖base,买alt)")
        else:
            print("⏸️  信号: 价差在正常范围,观望")

    print("\n" + "=" * 70)
    print("可视化z-score")
    print("=" * 70)

    if results:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # 价差图
        results['spread'].plot(ax=axes[0], label='Spread', color='blue')
        axes[0].axhline(y=results['spread'].mean(), color='r', linestyle='--', label='Mean')
        axes[0].axhline(y=results['spread'].mean() + 2*results['spread'].std(),
                       color='orange', linestyle='--', label='+2σ')
        axes[0].axhline(y=results['spread'].mean() - 2*results['spread'].std(),
                       color='orange', linestyle='--', label='-2σ')
        axes[0].set_title('Price Spread Over Time')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # z-score图
        results['zscore_rolling'].plot(ax=axes[1], label='Rolling Z-Score', color='green')
        axes[1].axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        axes[1].axhline(y=2, color='red', linestyle='--', label='±2σ threshold')
        axes[1].axhline(y=-2, color='red', linestyle='--')
        axes[1].fill_between(results['zscore_rolling'].index,
                            -2, 2, alpha=0.2, color='green')
        axes[1].set_title('Z-Score Over Time (Entry/Exit Signals)')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('zscore_analysis.png', dpi=100)
        print("\nZ-score分析图已保存: zscore_analysis.png")
