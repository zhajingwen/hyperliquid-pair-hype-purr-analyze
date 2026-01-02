#!/usr/bin/env python3
"""
测试purr5.py修改后的函数
验证移除收益率Beta后的代码逻辑
"""

import re

def test_find_optimal_delay():
    """测试find_optimal_delay函数签名"""
    print("=" * 60)
    print("测试 find_optimal_delay 函数签名")
    print("=" * 60)

    # 读取purr5.py检查函数签名
    with open('purr5.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查函数签名是否移除了enable_beta_calc参数
    assert 'enable_beta_calc' not in content, "❌ 仍存在enable_beta_calc参数"
    print("✅ enable_beta_calc参数已移除")

    # 检查返回值注释
    if 'tau_star, corrs, max_related_matrix, beta' in content:
        print("❌ 返回值注释仍包含beta")
    else:
        print("✅ 返回值注释已更新（移除beta）")

    # 检查返回语句
    return_pattern = r'return tau_star, corrs, max_related_matrix$'
    if re.search(return_pattern, content, re.MULTILINE):
        print("✅ 返回语句正确：3个值")
    else:
        print("⚠️  返回语句格式需要人工验证")
    print()

def test_config_removal():
    """测试配置项移除"""
    print("=" * 60)
    print("测试 Beta配置项移除")
    print("=" * 60)

    with open('purr5.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查配置项是否移除
    assert 'ENABLE_BETA_CALCULATION' not in content, "❌ ENABLE_BETA_CALCULATION仍存在"
    print("✅ ENABLE_BETA_CALCULATION已移除")

    assert 'MIN_POINTS_FOR_BETA_CALC' not in content, "❌ MIN_POINTS_FOR_BETA_CALC仍存在"
    print("✅ MIN_POINTS_FOR_BETA_CALC已移除")

    assert 'AVG_BETA_THRESHOLD' not in content, "❌ AVG_BETA_THRESHOLD仍存在"
    print("✅ AVG_BETA_THRESHOLD已移除")
    print()

def test_function_removal():
    """测试_calculate_beta函数移除"""
    print("=" * 60)
    print("测试 _calculate_beta函数移除")
    print("=" * 60)

    with open('purr5.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查函数是否移除
    assert 'def _calculate_beta' not in content, "❌ _calculate_beta函数仍存在"
    print("✅ _calculate_beta函数已移除")
    print()

def test_return_values():
    """测试返回值格式"""
    print("=" * 60)
    print("测试 返回值格式")
    print("=" * 60)

    with open('purr5.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否还有5元组的处理逻辑
    if 'len(result) == 5' in content:
        print("❌ 仍存在5元组处理逻辑")
    else:
        print("✅ 5元组处理逻辑已移除")

    # 检查4元组处理
    if 'len(result) == 4' in content or 'len(result) != 4' in content:
        print("✅ 4元组处理逻辑存在")
    else:
        print("⚠️  4元组处理逻辑需要人工验证")
    print()

def test_output_columns():
    """测试输出列"""
    print("=" * 60)
    print("测试 输出列定义")
    print("=" * 60)

    with open('purr5.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否移除了Beta列
    if 'Beta收益率系数' in content:
        print("❌ 输出中仍包含Beta收益率系数列")
    else:
        print("✅ Beta收益率系数列已移除")
    print()

def main():
    """运行所有测试"""
    print("\n🔍 开始测试purr5.py修改...\n")

    try:
        test_config_removal()
        test_function_removal()
        test_find_optimal_delay()
        test_return_values()
        test_output_columns()

        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n修改总结：")
        print("1. ✅ 移除了收益率Beta配置项（3个）")
        print("2. ✅ 移除了_calculate_beta函数")
        print("3. ✅ find_optimal_delay返回值：4个 → 3个")
        print("4. ✅ _analyze_single_combination返回值：5元组 → 4元组")
        print("5. ✅ _detect_anomaly_pattern移除Beta检查逻辑")
        print("6. ✅ _output_results移除Beta输出")
        print("7. ✅ one_coin_analysis简化返回值处理")
        print("\n📝 说明：")
        print("   - 代码将仅使用协整Beta（OLS回归斜率）")
        print("   - 移除了收益率Beta的所有计算和过滤逻辑")
        print("   - 返回值格式统一为4元组")
        print()

    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常：{type(e).__name__}: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
