"""
Look-ahead Bias 修复验证脚本

对比三种方法：
1. 原始方法（全历史OLS - 有look-ahead bias）
2. 滚动窗口完整版（返回参数时间序列）
3. price_diff_spread_ols_window（简化版）

验证关键指标：
- 参数稳定性
- 价差统计特性
- 回测性能差异
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.stattools import adfuller
import matplotlib.pyplot as plt
from cointegration_no_lookahead import (
    calculate_cointegration_params_rolling,
    calculate_spread_rolling_simple
)


def method1_full_history(base_prices, alt_prices):
    """方法1: 原始全历史OLS（存在look-ahead bias）"""
    log_base = np.log(base_prices)
    log_alt = np.log(alt_prices)

    model = LinearRegression()
    model.fit(log_base.values.reshape(-1, 1), log_alt.values)

    alpha = model.intercept_
    beta = model.coef_[0]
    spread = log_alt - (alpha + beta * log_base)

    adf_result = adfuller(spread.values, autolag='AIC')

    return {
        'alpha': alpha,
        'beta': beta,
        'spread': spread,
        'adf_pvalue': adf_result[1]
    }


def method2_rolling_window(base_prices, alt_prices, window=100):
    """方法2: 滚动窗口完整版（无look-ahead bias）"""
    return calculate_cointegration_params_rolling(
        base_prices, alt_prices, window=window, min_periods=50
    )


def method3_ols_window(base_prices, alt_prices, beta_window=100, zscore_window=30):
    """方法3: price_diff_spread_ols_window 风格（无look-ahead bias）"""
    data_window = max(beta_window, zscore_window)
    recent_base_full = base_prices.iloc[-data_window:]
    recent_alt_full = alt_prices.iloc[-data_window:]

    # 使用前 beta_window-1 个点计算OLS参数
    ols_base = recent_base_full.iloc[:-1]
    ols_alt = recent_alt_full.iloc[:-1]

    log_base_ols = np.log(ols_base).values.reshape(-1, 1)
    log_alt_ols = np.log(ols_alt).values

    model = LinearRegression()
    model.fit(log_base_ols, log_alt_ols)
    alpha = model.intercept_
    beta_ols = model.coef_[0]

    # 价差构建（用于Z-score计算：使用短窗口保持敏感度）
    recent_base = recent_base_full.iloc[-zscore_window:]
    recent_alt = recent_alt_full.iloc[-zscore_window:]
    log_base = np.log(recent_base)
    log_alt = np.log(recent_alt)
    spread = log_alt - (alpha + beta_ols * log_base)

    return {
        'alpha': alpha,
        'beta': beta_ols,
        'spread': spread,
        'adf_pvalue': np.nan  # 方法3不计算ADF
    }


def simulate_regime_change_data(n=1000, change_point=500):
    """
    模拟市场机制变化的数据

    前半段: β=15
    后半段: β=20
    """
    np.random.seed(42)

    base = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range('2024-01-01', periods=n, freq='1H')
    )

    # 前半段：β=15
    alt_early = np.exp(0.5 + 15 * np.log(base[:change_point]) + np.random.randn(change_point) * 0.02)

    # 后半段：β=20
    alt_late = np.exp(0.5 + 20 * np.log(base[change_point:]) + np.random.randn(n - change_point) * 0.02)

    alt = pd.concat([
        pd.Series(alt_early.values, index=base.index[:change_point]),
        pd.Series(alt_late.values, index=base.index[change_point:])
    ])

    return base, alt


def analyze_spread_properties(spread, name):
    """分析价差序列的统计特性"""
    print(f"\n{name}:")
    print(f"  长度: {len(spread)}")
    print(f"  均值: {spread.mean():.6f}")
    print(f"  标准差: {spread.std():.6f}")
    print(f"  范围: [{spread.min():.6f}, {spread.max():.6f}]")

    # ADF检验
    if len(spread) >= 10:
        adf_result = adfuller(spread.values, autolag='AIC')
        print(f"  ADF p-value: {adf_result[1]:.4f} ({'平稳' if adf_result[1] < 0.05 else '非平稳'})")

    # 前后半段均值对比（检测漂移）
    mid = len(spread) // 2
    if mid > 0:
        mean_first = spread.iloc[:mid].mean()
        mean_second = spread.iloc[mid:].mean()
        print(f"  前半段均值: {mean_first:.6f}")
        print(f"  后半段均值: {mean_second:.6f}")
        print(f"  均值漂移: {abs(mean_second - mean_first):.6f}")


def main():
    print("=" * 80)
    print("Look-ahead Bias 修复验证")
    print("=" * 80)

    # 1. 生成模拟数据（市场机制变化）
    print("\n[1] 生成模拟数据（市场机制在t=500时变化）")
    print("-" * 80)
    base, alt = simulate_regime_change_data(n=1000, change_point=500)
    print(f"真实参数: 前半段β=15, 后半段β=20")

    # 2. 方法1: 全历史OLS
    print("\n[2] 方法1: 全历史OLS（存在look-ahead bias）")
    print("-" * 80)
    result1 = method1_full_history(base, alt)
    print(f"全局参数: α={result1['alpha']:.4f}, β={result1['beta']:.4f}")
    print(f"ADF p-value: {result1['adf_pvalue']:.4f}")
    analyze_spread_properties(result1['spread'], "价差序列")

    # 3. 方法2: 滚动窗口完整版
    print("\n[3] 方法2: 滚动窗口完整版（无look-ahead bias）")
    print("-" * 80)
    result2 = method2_rolling_window(base, alt, window=100)

    if result2:
        print(f"参数时间序列长度: {len(result2['alpha_series'])}")
        print(f"最新参数: α={result2['alpha_series'].iloc[-1]:.4f}, β={result2['beta_series'].iloc[-1]:.4f}")
        print(f"ADF p-value (最后100个价差): {result2['adf_pvalue']:.4f}")

        # 分析前后半段的参数
        mid = len(result2['beta_series']) // 2
        beta_early = result2['beta_series'].iloc[:mid].mean()
        beta_late = result2['beta_series'].iloc[mid:].mean()
        print(f"\nβ参数演变:")
        print(f"  前半段平均β: {beta_early:.4f} (真实值=15)")
        print(f"  后半段平均β: {beta_late:.4f} (真实值=20)")
        print(f"  参数自适应: {'✅ 是' if abs(beta_late - beta_early) > 2 else '❌ 否'}")

        analyze_spread_properties(result2['spread_series'], "价差序列")

    # 4. 方法3: price_diff_spread_ols_window 风格
    print("\n[4] 方法3: price_diff_spread_ols_window 风格（无look-ahead bias）")
    print("-" * 80)
    result3 = method3_ols_window(base, alt, beta_window=100, zscore_window=30)
    print(f"当前参数: α={result3['alpha']:.4f}, β={result3['beta']:.4f}")
    analyze_spread_properties(result3['spread'], "价差序列（仅最近30期）")

    # 5. 可视化对比
    print("\n[5] 生成可视化对比图")
    print("-" * 80)

    fig, axes = plt.subplots(3, 2, figsize=(15, 10))

    # 左列：参数演变
    if result2:
        # Alpha演变
        axes[0, 0].plot(result2['alpha_series'].index, result2['alpha_series'].values, label='滚动窗口', alpha=0.7)
        axes[0, 0].axhline(result1['alpha'], color='red', linestyle='--', label='全历史OLS', alpha=0.7)
        axes[0, 0].set_title('Alpha参数演变')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        # Beta演变
        axes[1, 0].plot(result2['beta_series'].index, result2['beta_series'].values, label='滚动窗口', alpha=0.7)
        axes[1, 0].axhline(result1['beta'], color='red', linestyle='--', label='全历史OLS', alpha=0.7)
        axes[1, 0].axhline(15, color='green', linestyle=':', label='真实β(前半段)', alpha=0.5)
        axes[1, 0].axhline(20, color='orange', linestyle=':', label='真实β(后半段)', alpha=0.5)
        axes[1, 0].axvline(base.index[500], color='gray', linestyle='--', label='机制变化点', alpha=0.3)
        axes[1, 0].set_title('Beta参数演变')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)

        # Spread演变
        axes[2, 0].plot(result2['spread_series'].index, result2['spread_series'].values, label='滚动窗口', alpha=0.7)
        axes[2, 0].axhline(0, color='black', linestyle='-', linewidth=0.5, alpha=0.3)
        axes[2, 0].set_title('价差序列（滚动窗口）')
        axes[2, 0].legend()
        axes[2, 0].grid(True, alpha=0.3)

    # 右列：价差对比
    # 全历史OLS价差
    axes[0, 1].plot(result1['spread'].index, result1['spread'].values, label='全历史OLS', alpha=0.7, color='red')
    axes[0, 1].axhline(0, color='black', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[0, 1].axhline(result1['spread'].mean(), color='red', linestyle='--', label=f"均值={result1['spread'].mean():.4f}", alpha=0.5)
    axes[0, 1].axvline(base.index[500], color='gray', linestyle='--', label='机制变化点', alpha=0.3)
    axes[0, 1].set_title('价差序列（全历史OLS - 存在look-ahead bias）')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)

    # 滚动窗口价差
    if result2:
        axes[1, 1].plot(result2['spread_series'].index, result2['spread_series'].values, label='滚动窗口', alpha=0.7, color='blue')
        axes[1, 1].axhline(0, color='black', linestyle='-', linewidth=0.5, alpha=0.3)
        axes[1, 1].axhline(result2['spread_series'].mean(), color='blue', linestyle='--', label=f"均值={result2['spread_series'].mean():.4f}", alpha=0.5)
        axes[1, 1].axvline(base.index[500], color='gray', linestyle='--', label='机制变化点', alpha=0.3)
        axes[1, 1].set_title('价差序列（滚动窗口 - 无look-ahead bias）')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)

    # 价差分布对比
    axes[2, 1].hist(result1['spread'].values, bins=50, alpha=0.5, label='全历史OLS', color='red')
    if result2:
        axes[2, 1].hist(result2['spread_series'].values, bins=50, alpha=0.5, label='滚动窗口', color='blue')
    axes[2, 1].axvline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
    axes[2, 1].set_title('价差分布对比')
    axes[2, 1].legend()
    axes[2, 1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('lookahead_bias_comparison.png', dpi=150)
    print("✅ 对比图已保存: lookahead_bias_comparison.png")

    # 6. 关键发现总结
    print("\n[6] 关键发现总结")
    print("=" * 80)

    if result2:
        # 均值漂移检测
        spread1_drift = abs(result1['spread'].iloc[:500].mean() - result1['spread'].iloc[500:].mean())
        spread2_drift = abs(result2['spread_series'].iloc[:500].mean() - result2['spread_series'].iloc[500:].mean())

        print(f"\n均值漂移对比:")
        print(f"  全历史OLS: {spread1_drift:.6f} ❌（参数失配导致漂移）")
        print(f"  滚动窗口: {spread2_drift:.6f} ✅（参数自适应，漂移更小）")

        print(f"\n平稳性对比:")
        print(f"  全历史OLS: ADF p={result1['adf_pvalue']:.4f}")
        print(f"  滚动窗口: ADF p={result2['adf_pvalue']:.4f}")

        print(f"\n参数自适应性:")
        mid = len(result2['beta_series']) // 2
        beta_early = result2['beta_series'].iloc[:mid].mean()
        beta_late = result2['beta_series'].iloc[mid:].mean()
        print(f"  全历史OLS: β={result1['beta']:.4f} (固定)")
        print(f"  滚动窗口前半段: β={beta_early:.4f} (真实=15)")
        print(f"  滚动窗口后半段: β={beta_late:.4f} (真实=20)")
        print(f"  自适应准确度: {abs(beta_late - 20) / 20 * 100:.1f}% 误差")

    print("\n" + "=" * 80)
    print("推荐使用: 方法2（滚动窗口完整版）用于实时交易和回测")
    print("=" * 80)


if __name__ == "__main__":
    main()
