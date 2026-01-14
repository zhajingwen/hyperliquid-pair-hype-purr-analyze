"""
改进协整检验方法演示
使用模拟数据展示改进方法的优势
"""

import sys
import logging
import numpy as np
import pandas as pd
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.cointegration_improved import ImprovedCointegrationAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def generate_cointegrated_series(
    n_samples: int = 360,
    beta: float = 3.0,
    alpha: float = 0.0,
    noise_std: float = 0.02,
    seed: int = 42
) -> tuple:
    """
    生成协整的价格序列

    参数：
        n_samples: 样本数量
        beta: 真实β系数
        alpha: 真实α系数
        noise_std: 噪音标准差
        seed: 随机种子

    返回：
        (base_prices, alt_prices)
    """
    np.random.seed(seed)

    # 生成基准币价格（随机游走）
    base_returns = np.random.normal(0, 0.01, n_samples)
    base_log_price = np.cumsum(base_returns)
    base_prices = np.exp(base_log_price)

    # 生成协整的配对币价格
    # log(alt) = alpha + beta * log(base) + noise
    alt_log_price = alpha + beta * base_log_price + np.random.normal(0, noise_std, n_samples)
    alt_prices = np.exp(alt_log_price)

    # 转换为pandas Series
    index = pd.date_range('2024-01-01', periods=n_samples, freq='4h')
    base_series = pd.Series(base_prices, index=index, name='BASE')
    alt_series = pd.Series(alt_prices, index=index, name='ALT')

    return base_series, alt_series


def demo_basic_usage():
    """演示1: 基本使用"""

    logger.info("\n" + "="*100)
    logger.info("演示1: 基本使用 - 强协整关系（α=0.0, β=3.0）")
    logger.info("="*100 + "\n")

    # 生成协整数据（α=0，即无常数项）
    base_prices, alt_prices = generate_cointegrated_series(
        n_samples=360,
        beta=3.0,
        alpha=0.0,  # 无常数项
        noise_std=0.02,
        seed=42
    )

    logger.info(f"数据量: {len(base_prices)}期")
    logger.info(f"基准币价格范围: {base_prices.min():.2f} - {base_prices.max():.2f}")
    logger.info(f"配对币价格范围: {alt_prices.min():.2f} - {alt_prices.max():.2f}")
    logger.info("")

    # 使用改进方法分析（最近100期）
    result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
        base_prices=base_prices,
        alt_prices=alt_prices,
        beta_window=100,
        zscore_window=30,
        alpha_significance_level=0.10,
        verbose=True
    )

    if result:
        logger.info("\n💡 分析:")
        logger.info(f"   真实β = 3.0000, 估计β = {result['beta']:.4f}, 误差 = {abs(3.0 - result['beta']):.4f}")
        logger.info(f"   真实α = 0.0000, 估计α = {result['alpha']:.4f}")
        logger.info(f"   α是否显著: {'是' if result['alpha_significant'] else '否'} (预期: 否)")
        logger.info(f"   模型类型: {result['model_type']} (预期: no_intercept)")


def demo_with_intercept():
    """演示2: 带常数项的协整关系"""

    logger.info("\n" + "="*100)
    logger.info("演示2: 带常数项的协整关系（α=0.5, β=3.0）")
    logger.info("="*100 + "\n")

    # 生成协整数据（α=0.5，显著常数项）
    base_prices, alt_prices = generate_cointegrated_series(
        n_samples=360,
        beta=3.0,
        alpha=0.5,  # 显著常数项
        noise_std=0.02,
        seed=123
    )

    logger.info(f"数据量: {len(base_prices)}期")
    logger.info(f"基准币价格范围: {base_prices.min():.2f} - {base_prices.max():.2f}")
    logger.info(f"配对币价格范围: {alt_prices.min():.2f} - {alt_prices.max():.2f}")
    logger.info("")

    # 使用改进方法分析
    result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
        base_prices=base_prices,
        alt_prices=alt_prices,
        beta_window=100,
        zscore_window=30,
        alpha_significance_level=0.10,
        verbose=True
    )

    if result:
        logger.info("\n💡 分析:")
        logger.info(f"   真实α = 0.5000, 估计α = {result['alpha']:.4f}, 误差 = {abs(0.5 - result['alpha']):.4f}")
        logger.info(f"   真实β = 3.0000, 估计β = {result['beta']:.4f}, 误差 = {abs(3.0 - result['beta']):.4f}")
        logger.info(f"   α是否显著: {'是' if result['alpha_significant'] else '否'} (预期: 是)")
        logger.info(f"   模型类型: {result['model_type']} (预期: with_intercept)")


def demo_comparison():
    """演示3: 方法对比"""

    logger.info("\n" + "="*100)
    logger.info("演示3: 方法对比 - sklearn vs statsmodels")
    logger.info("="*100 + "\n")

    # 生成协整数据（α不显著）
    base_prices, alt_prices = generate_cointegrated_series(
        n_samples=360,
        beta=3.0,
        alpha=0.05,  # 很小的α（不显著）
        noise_std=0.02,
        seed=456
    )

    # 方法对比
    comparison = ImprovedCointegrationAnalyzer.compare_methods(
        base_prices=base_prices,
        alt_prices=alt_prices,
        beta_window=100,
        coin_name="模拟交易对"
    )


def demo_weak_cointegration():
    """演示4: 弱协整关系（边缘案例）"""

    logger.info("\n" + "="*100)
    logger.info("演示4: 弱协整关系 - 较大噪音")
    logger.info("="*100 + "\n")

    # 生成弱协整数据（较大噪音）
    base_prices, alt_prices = generate_cointegrated_series(
        n_samples=360,
        beta=3.0,
        alpha=0.0,
        noise_std=0.08,  # 较大噪音
        seed=789
    )

    logger.info(f"数据量: {len(base_prices)}期")
    logger.info(f"噪音标准差: 0.08 (较大)")
    logger.info("")

    # 使用改进方法分析
    result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
        base_prices=base_prices,
        alt_prices=alt_prices,
        beta_window=100,
        zscore_window=30,
        alpha_significance_level=0.10,
        verbose=True
    )

    if result:
        logger.info("\n💡 分析:")
        logger.info(f"   噪音较大时的表现:")
        logger.info(f"   - R² = {result['rsquared']:.4f} (拟合度)")
        logger.info(f"   - ADF p值 = {result['adf_pvalue']:.4f}")
        logger.info(f"   - 建议阈值 = {result['recommendation']['suggested_adf_threshold']}")
        logger.info(f"   - 是否通过 = {'✅' if result['recommendation']['passes_suggested_threshold'] else '❌'}")


def demo_alpha_validation():
    """演示5: α显著性验证"""

    logger.info("\n" + "="*100)
    logger.info("演示5: α显著性验证")
    logger.info("="*100 + "\n")

    # 案例1: α不显著
    logger.info("案例1: α不显著 (α=0.0)")
    logger.info("-"*80)

    base1, alt1 = generate_cointegrated_series(n_samples=360, beta=3.0, alpha=0.0, seed=111)
    alpha_pvalue1, is_sig1, rec1 = ImprovedCointegrationAnalyzer.validate_alpha_significance(
        base1, alt1, window=100
    )

    logger.info(f"   α的p值: {alpha_pvalue1:.4f}")
    logger.info(f"   是否显著: {'是' if is_sig1 else '否'}")
    logger.info(f"   建议: {rec1}")
    logger.info("")

    # 案例2: α显著
    logger.info("案例2: α显著 (α=0.5)")
    logger.info("-"*80)

    base2, alt2 = generate_cointegrated_series(n_samples=360, beta=3.0, alpha=0.5, seed=222)
    alpha_pvalue2, is_sig2, rec2 = ImprovedCointegrationAnalyzer.validate_alpha_significance(
        base2, alt2, window=100
    )

    logger.info(f"   α的p值: {alpha_pvalue2:.4f}")
    logger.info(f"   是否显著: {'是' if is_sig2 else '否'}")
    logger.info(f"   建议: {rec2}")
    logger.info("")


def demo_sample_size_effect():
    """演示6: 样本量影响"""

    logger.info("\n" + "="*100)
    logger.info("演示6: 样本量对检验结果的影响")
    logger.info("="*100 + "\n")

    # 生成协整数据
    base_prices, alt_prices = generate_cointegrated_series(
        n_samples=360,
        beta=3.0,
        alpha=0.0,
        noise_std=0.03,
        seed=999
    )

    # 测试不同样本量
    sample_sizes = [30, 50, 100, 150, 200]

    logger.info("样本量 | ADF p值 | 建议阈值 | 是否通过 | R²")
    logger.info("-"*80)

    for size in sample_sizes:
        if len(base_prices) < size:
            continue

        result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
            base_prices=base_prices,
            alt_prices=alt_prices,
            beta_window=size,
            zscore_window=30,
            verbose=False
        )

        if result:
            passes = "✅" if result['recommendation']['passes_suggested_threshold'] else "❌"
            logger.info(
                f"{size:>6}期 | {result['adf_pvalue']:>7.4f} | "
                f"{result['recommendation']['suggested_adf_threshold']:>10.2f} | "
                f"{passes:>8} | {result['rsquared']:.4f}"
            )

    logger.info("")
    logger.info("💡 观察:")
    logger.info("   - 样本量越大，ADF检验越稳定")
    logger.info("   - 小样本使用更宽松的阈值（0.10）")
    logger.info("   - 大样本使用更严格的阈值（0.05）")
    logger.info("")


def main():
    """运行所有演示"""

    logger.info("\n" + "🎯 " + "="*96)
    logger.info("改进版协整检验方法完整演示")
    logger.info("="*100 + "\n")

    try:
        # 演示1: 基本使用
        demo_basic_usage()

        # 演示2: 带常数项
        demo_with_intercept()

        # 演示3: 方法对比
        demo_comparison()

        # 演示4: 弱协整
        demo_weak_cointegration()

        # 演示5: α验证
        demo_alpha_validation()

        # 演示6: 样本量影响
        demo_sample_size_effect()

        logger.info("\n" + "="*100)
        logger.info("✅ 所有演示完成！")
        logger.info("="*100 + "\n")

        logger.info("📚 下一步:")
        logger.info("   1. 查看 integration_guide.md 了解如何集成到现有代码")
        logger.info("   2. 使用实际数据测试改进方法")
        logger.info("   3. 对比原方法和改进方法的结果")
        logger.info("")

    except Exception as e:
        logger.error(f"演示失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
