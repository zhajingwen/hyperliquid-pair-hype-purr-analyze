"""
测试改进的协整检验方法
对比原方法和改进方法的差异
"""

import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.cointegration_improved import ImprovedCointegrationAnalyzer
from utils.file_util import load_data_csv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def load_pair_data(coin_pair: str = "NOT/USDC:USDC", data_dir: str = "data_4h"):
    """
    加载交易对数据

    参数：
        coin_pair: 交易对格式 "ALT/BASE:QUOTE"
        data_dir: 数据目录

    返回：
        (base_prices, alt_prices)
    """
    try:
        # 解析交易对
        parts = coin_pair.split(":")
        if len(parts) != 2:
            raise ValueError(f"无效的交易对格式: {coin_pair}")

        pair = parts[0]  # NOT/USDC
        quote = parts[1]  # USDC

        alt_symbol, base_symbol = pair.split("/")  # NOT, USDC

        logger.info(f"加载数据: {alt_symbol} vs {base_symbol} (计价币: {quote})")

        # 加载数据
        base_file = f"{base_symbol}_{quote}_4h.csv"
        alt_file = f"{alt_symbol}_{quote}_4h.csv"

        base_df = load_data_csv(base_file, data_dir)
        alt_df = load_data_csv(alt_file, data_dir)

        if base_df is None or alt_df is None:
            logger.error("数据加载失败")
            return None, None

        # 对齐时间戳
        base_df = base_df.set_index('timestamp')
        alt_df = alt_df.set_index('timestamp')

        # 取交集
        common_index = base_df.index.intersection(alt_df.index)
        base_df = base_df.loc[common_index]
        alt_df = alt_df.loc[common_index]

        logger.info(f"数据量: {len(base_df)}期")
        logger.info(f"时间范围: {base_df.index[0]} 到 {base_df.index[-1]}")

        return base_df['close'], alt_df['close']

    except Exception as e:
        logger.error(f"加载数据失败: {e}", exc_info=True)
        return None, None


def test_single_pair(coin_pair: str, beta_window: int = 100):
    """测试单个交易对"""

    logger.info("\n" + "="*100)
    logger.info(f"🧪 测试交易对: {coin_pair}")
    logger.info("="*100 + "\n")

    # 加载数据
    base_prices, alt_prices = load_pair_data(coin_pair)

    if base_prices is None or alt_prices is None:
        logger.error("数据加载失败")
        return

    # 检查数据量
    if len(base_prices) < beta_window:
        logger.warning(f"数据量不足: {len(base_prices)} < {beta_window}")
        return

    # ===== 1. 方法对比 =====
    logger.info("\n" + "🔬 步骤1: 方法对比分析\n")
    comparison = ImprovedCointegrationAnalyzer.compare_methods(
        base_prices, alt_prices,
        beta_window=beta_window,
        coin_name=coin_pair
    )

    # ===== 2. α显著性验证 =====
    logger.info("\n" + "🔬 步骤2: α显著性独立验证\n")
    logger.info("="*80)

    alpha_pvalue, is_significant, recommendation = \
        ImprovedCointegrationAnalyzer.validate_alpha_significance(
            base_prices, alt_prices, window=beta_window
        )

    logger.info(f"α的p值: {alpha_pvalue:.4f}")
    logger.info(f"是否显著(α=0.10): {'✅ 是' if is_significant else '❌ 否'}")
    logger.info(f"建议: {recommendation}")
    logger.info("="*80)

    # ===== 3. 改进方法详细输出 =====
    logger.info("\n" + "🔬 步骤3: 改进方法详细分析\n")

    result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
        base_prices, alt_prices,
        beta_window=beta_window,
        zscore_window=30,
        alpha_significance_level=0.10,
        verbose=True  # 显示详细信息
    )

    # ===== 4. 交易建议 =====
    if result:
        logger.info("\n" + "💡 步骤4: 交易建议\n")
        logger.info("="*80)

        adf_pvalue = result['adf_pvalue']
        suggested_threshold = result['recommendation']['suggested_adf_threshold']
        passes = result['recommendation']['passes_suggested_threshold']

        logger.info(f"样本量: {result['recommendation']['sample_size']}期")
        logger.info(f"样本充分性: {result['recommendation']['sample_adequacy']}")
        logger.info(f"建议ADF阈值: {suggested_threshold}")
        logger.info("")

        # 判断是否可交易
        if passes:
            logger.info(f"✅ 协整检验通过 (p={adf_pvalue:.4f} ≤ {suggested_threshold})")
            logger.info(f"")
            logger.info(f"📈 交易建议:")
            logger.info(f"   状态: 可以交易")
            logger.info(f"   模型: {result['model_description']}")
            logger.info(f"   置信度: {'高' if adf_pvalue < 0.03 else '中' if adf_pvalue < suggested_threshold else '低'}")
            logger.info(f"")
            logger.info(f"⚠️  风险控制:")

            if adf_pvalue > suggested_threshold * 0.8:
                logger.info(f"   - 降低仓位至基准的70%（接近临界值）")
                logger.info(f"   - 设置更严格的止损（Z-score = ±2.0）")
                logger.info(f"   - 提高入场门槛（Z-score ≥ 2.0）")
            else:
                logger.info(f"   - 正常仓位配置")
                logger.info(f"   - 标准止损（Z-score = ±2.5）")
                logger.info(f"   - 标准入场门槛（Z-score ≥ 1.5）")

            if not result['alpha_significant']:
                logger.info(f"   - 注意：α不显著，已使用无常数项模型")
                logger.info(f"   - 建议：定期重新校准β系数")

        else:
            if adf_pvalue < 0.10:
                logger.info(f"⚠️  协整检验勉强通过 (p={adf_pvalue:.4f})")
                logger.info(f"")
                logger.info(f"📈 交易建议:")
                logger.info(f"   状态: 可以谨慎交易")
                logger.info(f"   置信度: 低")
                logger.info(f"   建议: 降低仓位至基准的50%")
                logger.info(f"   建议: 增加监控频率")
            else:
                logger.info(f"❌ 协整检验未通过 (p={adf_pvalue:.4f} > 0.10)")
                logger.info(f"")
                logger.info(f"📈 交易建议:")
                logger.info(f"   状态: 不建议交易")
                logger.info(f"   原因: 价差非平稳，协整关系不显著")

        logger.info("="*80)

    # ===== 5. 总结 =====
    logger.info("\n" + "📊 测试完成\n")


def test_multiple_pairs():
    """测试多个交易对"""

    # 测试交易对列表
    test_pairs = [
        "NOT/USDC:USDC",
        # "PONKE/SOL:USD",  # 如果有其他交易对可以添加
    ]

    for pair in test_pairs:
        try:
            test_single_pair(pair, beta_window=100)
        except Exception as e:
            logger.error(f"测试{pair}失败: {e}", exc_info=True)

        logger.info("\n" + "="*100 + "\n")


def compare_with_health_monitor():
    """与健康监控方法对比"""

    logger.info("\n" + "="*100)
    logger.info("🔬 三种方法完整对比")
    logger.info("="*100 + "\n")

    coin_pair = "NOT/USDC:USDC"

    # 加载数据
    base_prices, alt_prices = load_pair_data(coin_pair)

    if base_prices is None or alt_prices is None:
        return

    # 导入健康监控
    try:
        from utils.coingetation_more_check import CointegrationHealthMonitor

        # 健康监控分析
        log_base = np.log(base_prices)
        log_alt = np.log(alt_prices)

        monitor = CointegrationHealthMonitor(window=100)
        health_result = monitor.update(log_base, log_alt)

        logger.info("📊 方法3: 健康监控 (100期)")
        logger.info("-"*80)
        logger.info(f"   ADF p值: {health_result['adf_pvalue']:.4f}")
        logger.info(f"   健康得分: {health_result['health_score']:.2f}")
        logger.info(f"   健康状态: {health_result['health_status']}")
        logger.info(f"   β系数: {health_result['beta']:.4f}")
        logger.info("")

    except ImportError:
        logger.warning("无法导入健康监控模块")

    # 改进方法
    result = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
        base_prices, alt_prices,
        beta_window=100,
        verbose=False
    )

    if result:
        logger.info("📊 方法2: 改进方法 (statsmodels)")
        logger.info("-"*80)
        logger.info(f"   ADF p值: {result['adf_pvalue']:.4f}")
        logger.info(f"   α: {result['alpha']:.4f} (p={result['alpha_pvalue']:.4f})")
        logger.info(f"   β: {result['beta']:.4f} (p={result['beta_pvalue']:.4f})")
        logger.info(f"   模型类型: {result['model_type']}")
        logger.info(f"   R²: {result['rsquared']:.4f}")
        logger.info("")

    # 原方法
    comparison = ImprovedCointegrationAnalyzer.compare_methods(
        base_prices, alt_prices,
        beta_window=100,
        coin_name=coin_pair
    )

    logger.info("\n" + "💡 三种方法对比总结:")
    logger.info("-"*80)
    logger.info(f"方法1 (sklearn, 99期回归): ADF p={comparison['old_method']['adf_pvalue']:.4f}")
    if result:
        logger.info(f"方法2 (statsmodels, 100期): ADF p={result['adf_pvalue']:.4f}")
    if 'health_result' in locals():
        logger.info(f"方法3 (健康监控, 100期):  ADF p={health_result['adf_pvalue']:.4f}")

    logger.info("\n" + "="*100 + "\n")


if __name__ == "__main__":
    # 测试单个交易对
    test_single_pair("NOT/USDC:USDC", beta_window=100)

    # 如果想测试多个交易对
    # test_multiple_pairs()

    # 三种方法完整对比
    # compare_with_health_monitor()
