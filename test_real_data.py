"""
使用实际数据测试改进的协整检验方法
对比原方法和改进方法在NOT/USDC:USDC上的表现
"""

import sys
import logging
import numpy as np
import pandas as pd
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.cointegration_improved import ImprovedCointegrationAnalyzer
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.stattools import adfuller

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def original_method(base_prices, alt_prices, beta_window=100):
    """原方法（sklearn）"""

    data_window = beta_window
    recent_base_full = base_prices.iloc[-data_window:]
    recent_alt_full = alt_prices.iloc[-data_window:]

    # 使用前99期回归
    ols_base = recent_base_full.iloc[:-1]
    ols_alt = recent_alt_full.iloc[:-1]

    log_base_ols = np.log(ols_base).values.reshape(-1, 1)
    log_alt_ols = np.log(ols_alt).values

    # OLS回归
    model = LinearRegression()
    model.fit(log_base_ols, log_alt_ols)
    alpha = model.intercept_
    beta = model.coef_[0]

    # 价差（使用全部100期）
    log_base_full = np.log(recent_base_full)
    log_alt_full = np.log(recent_alt_full)
    spread_full = log_alt_full - (alpha + beta * log_base_full)

    # ADF检验
    adf_result = adfuller(spread_full.values, autolag='AIC')

    return {
        'alpha': alpha,
        'beta': beta,
        'spread': spread_full,
        'adf_stat': adf_result[0],
        'adf_pvalue': adf_result[1],
        'method': 'sklearn'
    }


def test_with_real_data():
    """使用实际数据测试"""

    logger.info("\n" + "="*100)
    logger.info("🔬 实际数据测试: NOT/USDC:USDC")
    logger.info("="*100 + "\n")

    # 尝试加载数据
    try:
        # 方法1: 从CSV文件加载
        import os

        # 查找数据文件
        possible_dirs = ['data_4h', 'data', '.']
        base_file = None
        alt_file = None

        for data_dir in possible_dirs:
            if os.path.exists(data_dir):
                # 查找USDC文件
                for filename in os.listdir(data_dir):
                    if 'USDC_USDC' in filename and filename.endswith('.csv'):
                        base_file = os.path.join(data_dir, filename)
                    if 'NOT_USDC' in filename and filename.endswith('.csv'):
                        alt_file = os.path.join(data_dir, filename)

                if base_file and alt_file:
                    break

        if not base_file or not alt_file:
            logger.warning("未找到数据文件，使用multi_coins4.py中的方法获取数据")
            logger.info("\n请在multi_coins4.py中添加测试代码:")
            logger.info("-" * 80)
            logger.info("""
# 在分析NOT/USDC:USDC时，添加以下代码：
from utils.cointegration_improved import ImprovedCointegrationAnalyzer

# 获取价格数据（在协整分析之前）
base_prices = ...  # USDC/USDC:USDC价格序列
alt_prices = ...   # NOT/USDC:USDC价格序列

# 方法对比
logger.info("\\n" + "="*80)
logger.info("🔬 原方法 vs 改进方法对比")
logger.info("="*80)

comparison = ImprovedCointegrationAnalyzer.compare_methods(
    base_prices, alt_prices,
    beta_window=100,
    coin_name="NOT/USDC:USDC"
)

# α显著性验证
alpha_pvalue, is_significant, recommendation = \\
    ImprovedCointegrationAnalyzer.validate_alpha_significance(
        base_prices, alt_prices, window=100
    )

logger.info(f"\\nα显著性验证:")
logger.info(f"  α的p值: {alpha_pvalue:.4f}")
logger.info(f"  是否显著: {'是' if is_significant else '否'}")
logger.info(f"  建议: {recommendation}")

# 使用改进方法
result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
    base_prices, alt_prices,
    beta_window=100,
    zscore_window=30,
    verbose=True
)

if result:
    logger.info(f"\\n📊 改进方法结果:")
    logger.info(f"  模型类型: {result['model_type']}")
    logger.info(f"  β系数: {result['beta']:.4f}")
    logger.info(f"  ADF p值: {result['adf_pvalue']:.4f}")
    logger.info(f"  建议阈值: {result['recommendation']['suggested_adf_threshold']}")
    logger.info(f"  是否通过: {'✅' if result['recommendation']['passes_suggested_threshold'] else '❌'}")
""")
            logger.info("-" * 80)
            return

        # 加载数据
        logger.info(f"找到数据文件:")
        logger.info(f"  基准币: {base_file}")
        logger.info(f"  配对币: {alt_file}\n")

        base_df = pd.read_csv(base_file)
        alt_df = pd.read_csv(alt_file)

        # 对齐时间戳
        if 'timestamp' in base_df.columns:
            base_df = base_df.set_index('timestamp')
            alt_df = alt_df.set_index('timestamp')

            common_index = base_df.index.intersection(alt_df.index)
            base_df = base_df.loc[common_index]
            alt_df = alt_df.loc[common_index]

        base_prices = base_df['close']
        alt_prices = alt_df['close']

        logger.info(f"数据量: {len(base_prices)}期")
        logger.info(f"时间范围: {base_df.index[0]} 到 {base_df.index[-1]}")
        logger.info(f"基准币价格范围: {base_prices.min():.4f} - {base_prices.max():.4f}")
        logger.info(f"配对币价格范围: {alt_prices.min():.4f} - {alt_prices.max():.4f}")
        logger.info("")

        # ===== 1. 原方法测试 =====
        logger.info("📊 步骤1: 原方法（sklearn）测试")
        logger.info("-" * 80)

        old_result = original_method(base_prices, alt_prices, beta_window=100)

        logger.info(f"  α = {old_result['alpha']:.4f}")
        logger.info(f"  β = {old_result['beta']:.4f}")
        logger.info(f"  ADF统计量 = {old_result['adf_stat']:.4f}")
        logger.info(f"  ADF p值 = {old_result['adf_pvalue']:.4f}")
        logger.info(f"  是否通过(0.05): {'✅' if old_result['adf_pvalue'] < 0.05 else '❌'}")
        logger.info(f"  是否通过(0.08): {'✅' if old_result['adf_pvalue'] < 0.08 else '❌'}")
        logger.info("")

        # ===== 2. α显著性验证 =====
        logger.info("📊 步骤2: α显著性验证")
        logger.info("-" * 80)

        alpha_pvalue, is_significant, recommendation = \
            ImprovedCointegrationAnalyzer.validate_alpha_significance(
                base_prices, alt_prices, window=100
            )

        logger.info(f"  α的p值: {alpha_pvalue:.4f}")
        logger.info(f"  是否显著(α=0.10): {'✅ 是' if is_significant else '❌ 否'}")
        logger.info(f"  建议: {recommendation}")
        logger.info("")

        # ===== 3. 改进方法测试 =====
        logger.info("📊 步骤3: 改进方法（statsmodels）测试")
        logger.info("-" * 80)

        new_result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
            base_prices, alt_prices,
            beta_window=100,
            zscore_window=30,
            alpha_significance_level=0.10,
            verbose=True
        )

        if not new_result:
            logger.error("改进方法失败")
            return

        # ===== 4. 对比分析 =====
        logger.info("\n" + "📊 步骤4: 对比分析")
        logger.info("=" * 80)

        logger.info(f"\n{'指标':<20} | {'原方法':<15} | {'改进方法':<15} | {'差异':<15}")
        logger.info("-" * 80)
        logger.info(f"{'α系数':<20} | {old_result['alpha']:>15.4f} | {new_result['alpha']:>15.4f} | {abs(old_result['alpha']-new_result['alpha']):>15.4f}")
        logger.info(f"{'β系数':<20} | {old_result['beta']:>15.4f} | {new_result['beta']:>15.4f} | {abs(old_result['beta']-new_result['beta']):>15.4f}")
        logger.info(f"{'ADF p值':<20} | {old_result['adf_pvalue']:>15.4f} | {new_result['adf_pvalue']:>15.4f} | {abs(old_result['adf_pvalue']-new_result['adf_pvalue']):>15.4f}")
        logger.info(f"{'模型类型':<20} | {'强制常数项':>15} | {new_result['model_type']:>15} | {'-':>15}")
        logger.info(f"{'R²':<20} | {'-':>15} | {new_result['rsquared']:>15.4f} | {'-':>15}")

        # ===== 5. 结论 =====
        logger.info("\n" + "💡 步骤5: 结论和建议")
        logger.info("=" * 80)

        suggested_threshold = new_result['recommendation']['suggested_adf_threshold']

        old_passes_005 = old_result['adf_pvalue'] < 0.05
        old_passes_008 = old_result['adf_pvalue'] < 0.08
        new_passes = new_result['recommendation']['passes_suggested_threshold']

        logger.info(f"\n原方法判断:")
        logger.info(f"  使用0.05阈值: {'✅ 通过' if old_passes_005 else '❌ 未通过'}")
        logger.info(f"  使用0.08阈值: {'✅ 通过' if old_passes_008 else '❌ 未通过'}")

        logger.info(f"\n改进方法判断:")
        logger.info(f"  建议阈值: {suggested_threshold}")
        logger.info(f"  是否通过: {'✅ 通过' if new_passes else '❌ 未通过'}")
        logger.info(f"  模型类型: {new_result['model_type']}")

        if new_result['alpha_significant']:
            logger.info(f"\nα显著性分析:")
            logger.info(f"  α是显著的(p={new_result['alpha_pvalue']:.4f})，两种方法应该得到相似结果")
            if abs(old_result['adf_pvalue'] - new_result['adf_pvalue']) > 0.02:
                logger.info(f"  但ADF p值差异较大({abs(old_result['adf_pvalue'] - new_result['adf_pvalue']):.4f})")
                logger.info(f"  可能原因: 回归数据范围不同（99期 vs 100期）")
        else:
            logger.info(f"\nα显著性分析:")
            logger.info(f"  α不显著(p={new_result['alpha_pvalue']:.4f})，改进方法使用无常数项模型")
            logger.info(f"  这解释了为什么ADF p值可能不同")
            logger.info(f"  无常数项模型可能更稳健（去掉了噪音）")

        logger.info(f"\n交易建议:")
        if new_passes:
            logger.info(f"  ✅ 改进方法通过协整检验，建议可以交易")
            if new_result['adf_pvalue'] > suggested_threshold * 0.8:
                logger.info(f"  ⚠️  但p值接近临界值，建议:")
                logger.info(f"     - 降低仓位至基准的70%")
                logger.info(f"     - 设置更严格止损（Z-score = ±2.0）")
                logger.info(f"     - 提高入场门槛（Z-score ≥ 2.0）")
            else:
                logger.info(f"  正常仓位配置即可")
        else:
            if old_passes_008:
                logger.info(f"  ⚠️  原方法在0.08阈值下通过，但改进方法未通过")
                logger.info(f"  建议谨慎交易或观望")
            else:
                logger.info(f"  ❌ 不建议交易，协整关系不显著")

        logger.info("\n" + "=" * 80)

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    test_with_real_data()
