"""
改进的协整检验方法
使用statsmodels进行更严格的统计检验
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ImprovedCointegrationAnalyzer:
    """改进的协整分析器"""

    @staticmethod
    def price_diff_spread_ols_window_improved(
        base_prices: pd.Series,
        alt_prices: pd.Series,
        beta_window: int = 100,
        zscore_window: int = 30,
        alpha_significance_level: float = 0.10,
        use_log: bool = True,
        verbose: bool = True
    ) -> Optional[Dict]:
        """
        改进版OLS协整分析（使用statsmodels）

        主要改进：
        1. 使用statsmodels.OLS替代sklearn（更严格的统计检验）
        2. 增加α显著性检验，动态选择模型
        3. 提供更丰富的统计信息（R²、t统计量等）
        4. 支持小样本的p值阈值调整建议

        参数：
            base_prices: 基准币价格序列
            alt_prices: 配对币价格序列
            beta_window: OLS回归窗口大小（默认100）
            zscore_window: Z-score计算窗口大小（默认30）
            alpha_significance_level: α显著性水平（默认0.10）
            use_log: 是否使用对数价格（默认True）
            verbose: 是否输出详细信息（默认True）

        返回：
            dict包含:
                - alpha: 截距项
                - beta: 斜率系数
                - alpha_pvalue: α的p值
                - beta_pvalue: β的p值
                - alpha_significant: α是否显著
                - model_type: 'with_intercept' 或 'no_intercept'
                - spread: 价差序列（用于交易信号）
                - spread_full: 完整价差序列（用于ADF检验）
                - adf_pvalue: ADF检验p值
                - adf_stat: ADF统计量
                - rsquared: R²决定系数
                - ols_model: statsmodels模型对象
                - recommendation: 根据样本量给出的p值阈值建议
        """
        try:
            # ===== 1. 数据准备 =====
            data_window = max(beta_window, zscore_window)

            # 检查数据量
            if len(base_prices) < data_window or len(alt_prices) < data_window:
                logger.warning(
                    f"数据量不足：需要至少{data_window}期，"
                    f"实际base={len(base_prices)}, alt={len(alt_prices)}"
                )
                return None

            # 取最近数据
            recent_base_full = base_prices.iloc[-data_window:]
            recent_alt_full = alt_prices.iloc[-data_window:]

            # ===== 2. OLS回归（使用statsmodels） =====
            if use_log:
                log_base = np.log(recent_base_full)
                log_alt = np.log(recent_alt_full)
            else:
                log_base = recent_base_full
                log_alt = recent_alt_full

            # 添加常数项
            X = sm.add_constant(log_base)

            # OLS回归
            model = sm.OLS(log_alt, X).fit()

            # 提取参数
            alpha = model.params.iloc[0]  # 常数项
            beta = model.params.iloc[1]   # 斜率
            alpha_pvalue = model.pvalues.iloc[0]
            beta_pvalue = model.pvalues.iloc[1]
            alpha_tstat = model.tvalues.iloc[0]
            beta_tstat = model.tvalues.iloc[1]
            rsquared = model.rsquared

            # ===== 3. 判断α是否显著 =====
            alpha_significant = alpha_pvalue <= alpha_significance_level

            # ===== 4. 根据α显著性选择价差计算方法 =====
            if alpha_significant:
                # α显著，使用标准Engle-Granger模型
                spread_full = log_alt - (alpha + beta * log_base)
                model_type = "with_intercept"
                model_desc = f"log(ALT) = {alpha:.4f} + {beta:.4f}×log(BASE)"
            else:
                # α不显著，使用无常数项模型
                spread_full = log_alt - beta * log_base
                model_type = "no_intercept"
                model_desc = f"log(ALT) = {beta:.4f}×log(BASE)"

                if verbose:
                    logger.info(
                        f"⚠️ α不显著(p={alpha_pvalue:.4f} > {alpha_significance_level})，"
                        f"使用无常数项模型可能更稳健"
                    )

            # ===== 5. ADF检验 =====
            adf_result = adfuller(spread_full.values, autolag='AIC')
            adf_stat = adf_result[0]
            adf_pvalue = adf_result[1]
            adf_critical_values = adf_result[4]

            # ===== 6. 根据样本量给出p值阈值建议 =====
            sample_size = len(spread_full)
            if sample_size < 50:
                suggested_threshold = 0.10
                sample_adequacy = "小样本"
            elif sample_size < 150:
                suggested_threshold = 0.08
                sample_adequacy = "中等样本"
            else:
                suggested_threshold = 0.05
                sample_adequacy = "大样本"

            recommendation = {
                'sample_size': sample_size,
                'sample_adequacy': sample_adequacy,
                'suggested_adf_threshold': suggested_threshold,
                'passes_suggested_threshold': adf_pvalue <= suggested_threshold
            }

            # ===== 7. 短窗口价差（用于交易信号） =====
            spread_short = spread_full.iloc[-zscore_window:]

            # ===== 8. 输出详细信息 =====
            if verbose:
                logger.info("=" * 80)
                logger.info("📊 改进版OLS协整分析结果")
                logger.info("-" * 80)
                logger.info(f"数据窗口: {data_window}期 | 样本充分性: {sample_adequacy}")
                logger.info(f"")
                logger.info(f"🔍 OLS回归结果:")
                logger.info(f"   模型类型: {model_type}")
                logger.info(f"   方程: {model_desc}")
                logger.info(f"   R²: {rsquared:.4f}")
                logger.info(f"")
                logger.info(f"📈 参数估计:")
                logger.info(f"   α (截距)  = {alpha:>8.4f}  [t={alpha_tstat:>6.2f}, p={alpha_pvalue:.4f}] {'✅显著' if alpha_significant else '❌不显著'}")
                logger.info(f"   β (斜率)  = {beta:>8.4f}  [t={beta_tstat:>6.2f}, p={beta_pvalue:.4f}] {'✅显著' if beta_pvalue <= 0.05 else '⚠️不显著'}")
                logger.info(f"")
                logger.info(f"📉 ADF平稳性检验:")
                logger.info(f"   ADF统计量: {adf_stat:.4f}")
                logger.info(f"   p值: {adf_pvalue:.4f}")
                logger.info(f"   临界值: 1%={adf_critical_values['1%']:.2f}, "
                           f"5%={adf_critical_values['5%']:.2f}, "
                           f"10%={adf_critical_values['10%']:.2f}")
                logger.info(f"")
                logger.info(f"💡 建议:")
                logger.info(f"   样本量: {sample_size}期")
                logger.info(f"   建议p值阈值: {suggested_threshold}")
                logger.info(f"   是否通过: {'✅' if recommendation['passes_suggested_threshold'] else '❌'}")
                logger.info("=" * 80)

            # ===== 9. 返回结果 =====
            return {
                # 基本参数
                'alpha': alpha,
                'beta': beta,
                'alpha_pvalue': alpha_pvalue,
                'beta_pvalue': beta_pvalue,
                'alpha_tstat': alpha_tstat,
                'beta_tstat': beta_tstat,
                'alpha_significant': alpha_significant,
                'model_type': model_type,
                'model_description': model_desc,

                # 价差序列
                'spread': spread_short,      # 短窗口（用于交易）
                'spread_full': spread_full,  # 完整窗口（用于检验）

                # ADF检验结果
                'adf_stat': adf_stat,
                'adf_pvalue': adf_pvalue,
                'adf_critical_values': adf_critical_values,

                # 模型质量
                'rsquared': rsquared,
                'ols_model': model,

                # 建议
                'recommendation': recommendation
            }

        except Exception as e:
            logger.error(f"改进版OLS协整分析失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def compare_methods(
        base_prices: pd.Series,
        alt_prices: pd.Series,
        beta_window: int = 100,
        coin_name: str = "Unknown"
    ) -> Dict:
        """
        对比原方法和改进方法

        参数：
            base_prices: 基准币价格序列
            alt_prices: 配对币价格序列
            beta_window: 窗口大小
            coin_name: 币种名称

        返回：
            dict包含两种方法的对比结果
        """
        from sklearn.linear_model import LinearRegression

        logger.info(f"\n{'='*80}")
        logger.info(f"🔬 方法对比分析: {coin_name}")
        logger.info(f"{'='*80}\n")

        # 数据准备
        data_window = beta_window
        recent_base = base_prices.iloc[-data_window:]
        recent_alt = alt_prices.iloc[-data_window:]

        # ===== 原方法（sklearn） =====
        logger.info("📊 原方法 (sklearn.LinearRegression)")
        logger.info("-" * 80)

        # OLS回归（使用前99期）
        ols_base_old = recent_base.iloc[:-1]
        ols_alt_old = recent_alt.iloc[:-1]
        log_base_ols_old = np.log(ols_base_old).values.reshape(-1, 1)
        log_alt_ols_old = np.log(ols_alt_old).values

        model_old = LinearRegression()
        model_old.fit(log_base_ols_old, log_alt_ols_old)
        alpha_old = model_old.intercept_
        beta_old = model_old.coef_[0]

        # 价差和ADF（使用全部100期）
        log_base_old = np.log(recent_base)
        log_alt_old = np.log(recent_alt)
        spread_old = log_alt_old - (alpha_old + beta_old * log_base_old)
        adf_old = adfuller(spread_old.values, autolag='AIC')

        logger.info(f"   α = {alpha_old:.4f}")
        logger.info(f"   β = {beta_old:.4f}")
        logger.info(f"   ADF p值 = {adf_old[1]:.4f} {'✅通过' if adf_old[1] < 0.05 else '❌未通过(0.05)' if adf_old[1] < 0.10 else '❌未通过(0.10)'}")
        logger.info(f"   模型类型: 强制使用常数项")
        logger.info(f"   回归数据: 前{len(ols_base_old)}期")
        logger.info(f"   检验数据: 全部{len(recent_base)}期\n")

        # ===== 改进方法（statsmodels） =====
        logger.info("📊 改进方法 (statsmodels.OLS)")
        logger.info("-" * 80)

        result_new = ImprovedCointegrationAnalyzer.price_diff_spread_ols_window_improved(
            base_prices, alt_prices,
            beta_window=beta_window,
            zscore_window=30,
            verbose=False  # 避免重复输出
        )

        if result_new:
            logger.info(f"   α = {result_new['alpha']:.4f} (p={result_new['alpha_pvalue']:.4f}) {'✅显著' if result_new['alpha_significant'] else '❌不显著'}")
            logger.info(f"   β = {result_new['beta']:.4f} (p={result_new['beta_pvalue']:.4f})")
            logger.info(f"   R² = {result_new['rsquared']:.4f}")
            logger.info(f"   ADF p值 = {result_new['adf_pvalue']:.4f} {'✅通过' if result_new['adf_pvalue'] < 0.05 else '❌未通过(0.05)' if result_new['adf_pvalue'] < 0.10 else '❌未通过(0.10)'}")
            logger.info(f"   模型类型: {result_new['model_type']}")
            logger.info(f"   建议p值阈值: {result_new['recommendation']['suggested_adf_threshold']}")
            logger.info(f"   是否通过建议阈值: {'✅' if result_new['recommendation']['passes_suggested_threshold'] else '❌'}")
            logger.info(f"   回归数据: 全部{beta_window}期")
            logger.info(f"   检验数据: 全部{beta_window}期\n")

        # ===== 差异分析 =====
        logger.info("📊 差异分析")
        logger.info("-" * 80)

        if result_new:
            alpha_diff = abs(alpha_old - result_new['alpha'])
            beta_diff = abs(beta_old - result_new['beta'])
            adf_diff = abs(adf_old[1] - result_new['adf_pvalue'])

            logger.info(f"   Δα = {alpha_diff:.4f} ({alpha_diff/abs(alpha_old)*100:.1f}%)")
            logger.info(f"   Δβ = {beta_diff:.4f} ({beta_diff/abs(beta_old)*100:.1f}%)")
            logger.info(f"   ΔADF_p值 = {adf_diff:.4f}")
            logger.info(f"")

            # 结论判断
            if result_new['alpha_significant']:
                logger.info(f"   💡 结论: α显著，两种方法应该得到相似结果")
                if adf_diff > 0.02:
                    logger.info(f"   ⚠️  但ADF p值差异较大，可能是因为:")
                    logger.info(f"       1. 回归数据范围不同（99期 vs 100期）")
                    logger.info(f"       2. 数值精度差异")
            else:
                logger.info(f"   💡 结论: α不显著，建议使用无常数项模型")
                logger.info(f"   ✅ 改进方法会自动切换到更稳健的模型")

        logger.info(f"\n{'='*80}\n")

        return {
            'old_method': {
                'alpha': alpha_old,
                'beta': beta_old,
                'adf_pvalue': adf_old[1],
                'adf_stat': adf_old[0]
            },
            'new_method': result_new
        }

    @staticmethod
    def validate_alpha_significance(
        base_prices: pd.Series,
        alt_prices: pd.Series,
        window: int = 100
    ) -> Tuple[float, bool, str]:
        """
        验证α是否显著

        返回：
            (alpha_pvalue, is_significant, recommendation)
        """
        recent_base = base_prices.iloc[-window:]
        recent_alt = alt_prices.iloc[-window:]

        log_base = np.log(recent_base)
        log_alt = np.log(recent_alt)

        X = sm.add_constant(log_base)
        model = sm.OLS(log_alt, X).fit()

        alpha_pvalue = model.pvalues.iloc[0]
        is_significant = alpha_pvalue <= 0.10

        if is_significant:
            recommendation = "使用标准Engle-Granger模型（带常数项）"
        else:
            recommendation = "建议使用无常数项模型，可能更稳健"

        return alpha_pvalue, is_significant, recommendation


def test_improved_method():
    """测试改进方法"""
    import sys
    sys.path.append('/Users/test/Downloads/hyperliquid-pair-hype-purr-analyze')

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    # 这里需要实际数据进行测试
    logger.info("改进方法已准备就绪，请使用实际数据进行测试")


if __name__ == "__main__":
    test_improved_method()
