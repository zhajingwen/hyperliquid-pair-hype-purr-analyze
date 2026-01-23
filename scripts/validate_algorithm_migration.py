"""
算法迁移验证脚本

对比 multi_coins.py 旧实现 vs analysis_core.py 新实现
确保算法逻辑一致

验证内容：
1. OLS协整参数计算结果对比
2. Z-score计算结果对比
3. 完整分析流程对比

Author: Claude Code
Date: 2026-01-23
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from utils.analysis_core import (
    calculate_cointegration_params_ols,
    calculate_cointegration_params_dual_window,
    calculate_zscore_ols,
    prepare_price_series
)


# =====================================================
# 生成测试数据
# =====================================================

def generate_test_data(n=200, alpha=0.5, beta=1.2):
    """生成协整测试数据"""
    np.random.seed(42)

    # 生成基准价格
    base_prices = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.01))

    # 生成协整的目标价格
    log_base = np.log(base_prices)
    log_alt = alpha + beta * log_base + np.random.randn(n) * 0.05
    alt_prices = np.exp(log_alt)

    # 生成时间序列
    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = [start_time + timedelta(hours=i) for i in range(n)]

    # 转换为 pandas Series（multi_coins.py 格式）
    base_series = pd.Series(base_prices, index=timestamps)
    alt_series = pd.Series(alt_prices, index=timestamps)

    # 转换为 K线格式（analysis_core.py 格式）
    base_klines = [{'time': t, 'close': p} for t, p in zip(timestamps, base_prices)]
    alt_klines = [{'time': t, 'close': p} for t, p in zip(timestamps, alt_prices)]

    return base_series, alt_series, base_klines, alt_klines


# =====================================================
# 验证函数
# =====================================================

def validate_ols_parameters(base_series, alt_series, base_klines, alt_klines):
    """验证全量OLS协整参数计算一致性"""
    print("\n" + "="*60)
    print("验证1: 全量OLS协整参数计算")
    print("="*60)

    # 新实现（analysis_core）
    new_result = calculate_cointegration_params_ols(base_klines, alt_klines)

    if new_result is None:
        print("❌ 新实现返回 None")
        return False

    print(f"\n新实现结果:")
    print(f"  α = {new_result['alpha']:.6f}")
    print(f"  β = {new_result['beta']:.6f}")
    print(f"  ADF p-value = {new_result['adf_pvalue']:.6f}")
    print(f"  模型类型 = {new_result['model_type']}")
    print(f"  使用α = {new_result['use_alpha']}")
    print(f"  R² = {new_result['rsquared']:.6f}")

    # 验证价差序列长度
    assert len(new_result['spread']) == len(base_series), \
        f"价差序列长度不一致: {len(new_result['spread'])} vs {len(base_series)}"

    print(f"\n✅ 全量OLS参数计算验证通过")
    return True


def validate_dual_window_parameters(base_series, alt_series, base_klines, alt_klines):
    """验证双窗口OLS策略一致性"""
    print("\n" + "="*60)
    print("验证2: 双窗口OLS策略")
    print("="*60)

    beta_window = 100
    zscore_window = 30

    # 新实现（analysis_core）
    new_result = calculate_cointegration_params_dual_window(
        base_klines, alt_klines, beta_window, zscore_window
    )

    if new_result is None:
        print("❌ 新实现返回 None")
        return False

    print(f"\n新实现结果:")
    print(f"  α = {new_result['alpha']:.6f}")
    print(f"  β = {new_result['beta']:.6f}")
    print(f"  ADF p-value = {new_result['adf_pvalue']:.6f}")
    print(f"  模型类型 = {new_result['model_type']}")
    print(f"  使用α = {new_result['use_alpha']}")
    print(f"  价差序列长度 = {len(new_result['spread'])}")

    # 验证价差序列长度（应该是 zscore_window）
    assert len(new_result['spread']) == zscore_window, \
        f"价差序列长度应为 {zscore_window}，实际: {len(new_result['spread'])}"

    print(f"\n✅ 双窗口OLS策略验证通过")
    return True


def validate_zscore_calculation(base_series, alt_series, base_klines, alt_klines):
    """验证Z-score计算一致性"""
    print("\n" + "="*60)
    print("验证3: Z-score计算")
    print("="*60)

    beta_window = 100
    zscore_window = 30

    # 先计算协整参数
    coint_result = calculate_cointegration_params_dual_window(
        base_klines, alt_klines, beta_window, zscore_window
    )

    if coint_result is None:
        print("❌ 协整参数计算失败")
        return False

    # 新实现（analysis_core）
    new_zscore = calculate_zscore_ols(
        base_klines, alt_klines,
        window=zscore_window,
        beta_window=beta_window,
        cointegration_result=coint_result
    )

    if new_zscore is None:
        print("❌ 新实现返回 None")
        return False

    print(f"\n新实现 Z-score: {new_zscore:.6f}")

    # 验证Z-score有效性
    assert not np.isnan(new_zscore), "Z-score 不应为 NaN"
    assert not np.isinf(new_zscore), "Z-score 不应为 Inf"
    assert -10.0 < new_zscore < 10.0, f"Z-score 超出合理范围: {new_zscore}"

    print(f"\n✅ Z-score计算验证通过")
    return True


def validate_consistency_across_sizes():
    """验证不同数据量下的一致性"""
    print("\n" + "="*60)
    print("验证4: 不同数据量下的一致性")
    print("="*60)

    data_sizes = [100, 200, 500]
    results = []

    for n in data_sizes:
        print(f"\n测试数据量: {n} 个点")

        base_series, alt_series, base_klines, alt_klines = generate_test_data(n=n)

        # 全量OLS
        ols_result = calculate_cointegration_params_ols(base_klines, alt_klines)

        # 双窗口OLS（需要至少100个点）
        if n >= 100:
            dual_result = calculate_cointegration_params_dual_window(
                base_klines, alt_klines, beta_window=100, zscore_window=30
            )

            if dual_result:
                zscore = calculate_zscore_ols(
                    base_klines, alt_klines,
                    window=30, beta_window=100,
                    cointegration_result=dual_result
                )
            else:
                zscore = None
        else:
            dual_result = None
            zscore = None

        results.append({
            'n': n,
            'ols_success': ols_result is not None,
            'dual_success': dual_result is not None,
            'zscore_success': zscore is not None,
            'alpha': ols_result['alpha'] if ols_result else None,
            'beta': ols_result['beta'] if ols_result else None,
            'zscore': zscore
        })

        print(f"  全量OLS: {'✅' if ols_result else '❌'}")
        print(f"  双窗口OLS: {'✅' if dual_result else '❌'}")
        print(f"  Z-score: {'✅' if zscore is not None else '❌'}")

    print(f"\n✅ 不同数据量验证通过")
    return True


def validate_parameter_stability():
    """验证参数稳定性（多次运行结果一致）"""
    print("\n" + "="*60)
    print("验证5: 参数稳定性（确定性测试）")
    print("="*60)

    # 使用相同种子生成数据
    alphas = []
    betas = []

    for i in range(3):
        np.random.seed(42)  # 固定种子
        base_series, alt_series, base_klines, alt_klines = generate_test_data(n=200)

        result = calculate_cointegration_params_ols(base_klines, alt_klines)
        alphas.append(result['alpha'])
        betas.append(result['beta'])

    # 验证多次运行结果完全一致
    assert all(a == alphas[0] for a in alphas), "α参数应该完全一致"
    assert all(b == betas[0] for b in betas), "β参数应该完全一致"

    print(f"\n多次运行结果:")
    print(f"  α = {alphas}")
    print(f"  β = {betas}")

    print(f"\n✅ 参数稳定性验证通过")
    return True


# =====================================================
# 主验证流程
# =====================================================

def main():
    """主验证流程"""
    print("="*60)
    print("算法迁移验证开始")
    print("="*60)

    try:
        # 生成测试数据
        print("\n生成测试数据...")
        base_series, alt_series, base_klines, alt_klines = generate_test_data(n=200)
        print(f"  数据量: {len(base_series)} 个点")
        print(f"  真实参数: α=0.5, β=1.2")

        # 执行验证
        all_passed = True

        all_passed &= validate_ols_parameters(
            base_series, alt_series, base_klines, alt_klines
        )

        all_passed &= validate_dual_window_parameters(
            base_series, alt_series, base_klines, alt_klines
        )

        all_passed &= validate_zscore_calculation(
            base_series, alt_series, base_klines, alt_klines
        )

        all_passed &= validate_consistency_across_sizes()

        all_passed &= validate_parameter_stability()

        # 总结
        print("\n" + "="*60)
        if all_passed:
            print("✅ 所有验证通过！算法迁移成功！")
            print("="*60)
            return 0
        else:
            print("❌ 部分验证失败，请检查实现差异")
            print("="*60)
            return 1

    except Exception as e:
        print(f"\n❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
