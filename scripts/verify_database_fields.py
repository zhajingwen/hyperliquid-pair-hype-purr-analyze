#!/usr/bin/env python3
"""
验证 analysis_record 数据结构与数据库表结构的兼容性

用途：
1. 验证所有必需字段都存在
2. 验证相关系数字段有实际值（不是 None）
3. 验证字段类型正确
"""

from datetime import datetime, timezone
from typing import Dict, Any


# 数据库表字段定义（来自 init_timescaledb.sql）
REQUIRED_FIELDS = {
    'analysis_time': 'TIMESTAMPTZ',
    'symbol': 'VARCHAR(50)',
    'base_symbol': 'VARCHAR(50)',

    # 相关系数（必需，不应为 None）
    'corr_5m_7d': 'DOUBLE PRECISION',
    'corr_1h_30d': 'DOUBLE PRECISION',
    'corr_4h_60d': 'DOUBLE PRECISION',

    # Z-score（必需）
    'zscore_5m': 'DOUBLE PRECISION',
    'zscore_1h': 'DOUBLE PRECISION',
    'zscore_4h': 'DOUBLE PRECISION',

    # 协整检验（必需）
    'cointegration_passed': 'BOOLEAN',
    'adf_pvalue': 'DOUBLE PRECISION',

    # 信号标识（必需）
    'is_anomaly': 'BOOLEAN',
    'trading_direction': 'VARCHAR(50)',
    'signal_strength': 'VARCHAR(20)',
}


def simulate_multi_period_result() -> Dict[str, Any]:
    """
    模拟 analyze_multi_period 的返回结果
    """
    return {
        'passed': True,
        'zscore_list': [-2.1, -1.8, -0.5],  # 5m, 1h, 4h
        'cointegration_count': 5,
        'direction': 'long',
        'details': {
            ('5m', '7d'): {
                'correlation': 0.85,  # 相关系数（已计算）
                'cointegration_old': {'passed': True, 'adf_pvalue': 0.01},
                'cointegration_new': {'passed': True, 'adf_pvalue': 0.02},
                'zscore': -2.1
            },
            ('1h', '30d'): {
                'correlation': 0.78,  # 相关系数（已计算）
                'cointegration_old': {'passed': True, 'adf_pvalue': 0.03},
                'cointegration_new': {'passed': True, 'adf_pvalue': 0.04},
                'zscore': -1.8
            },
            ('4h', '60d'): {
                'correlation': 0.92,  # 相关系数（已计算）
                'cointegration_old': {'passed': True, 'adf_pvalue': 0.01},
                'cointegration_new': {'passed': True, 'adf_pvalue': 0.02},
                'zscore': -0.5
            }
        }
    }


def build_analysis_record(symbol: str, base_symbol: str, multi_period_result: Dict) -> Dict:
    """
    构建 analysis_record（与 realtime_kline_service.py 中的逻辑一致）
    """
    # ✅ 从 details 中提取每个周期的相关系数
    details = multi_period_result.get('details', {})
    corr_5m_7d = details.get(('5m', '7d'), {}).get('correlation')
    corr_1h_30d = details.get(('1h', '30d'), {}).get('correlation')
    corr_4h_60d = details.get(('4h', '60d'), {}).get('correlation')

    return {
        'analysis_time': datetime.now(timezone.utc),
        'symbol': symbol,
        'base_symbol': base_symbol,

        # ✅ 相关系数（从多周期验证结果中提取）
        'corr_5m_7d': corr_5m_7d,
        'corr_1h_30d': corr_1h_30d,
        'corr_4h_60d': corr_4h_60d,

        # ✅ 多周期Z-score
        'zscore_5m': multi_period_result['zscore_list'][0],
        'zscore_1h': multi_period_result['zscore_list'][1],
        'zscore_4h': multi_period_result['zscore_list'][2],

        # ✅ 协整检验
        'cointegration_passed': multi_period_result['cointegration_count'] >= 2,
        'adf_pvalue': None,

        # ✅ 信号判断
        'is_anomaly': True,
        'trading_direction': multi_period_result['direction'],
        'signal_strength': 'strong',
    }


def validate_analysis_record(record: Dict) -> bool:
    """
    验证 analysis_record 的字段完整性和类型正确性

    Returns:
        bool: 验证是否通过
    """
    print("=" * 80)
    print("验证 analysis_record 数据结构")
    print("=" * 80)

    # 验证1: 检查所有必需字段是否存在
    print("\n[验证1] 检查必需字段...")
    missing_fields = []
    for field in REQUIRED_FIELDS.keys():
        if field not in record:
            missing_fields.append(field)
            print(f"  ❌ 缺失字段: {field}")
        else:
            print(f"  ✅ {field}: {record[field]}")

    if missing_fields:
        print(f"\n❌ 验证失败：缺少 {len(missing_fields)} 个必需字段")
        return False

    # 验证2: 检查是否有多余字段
    print("\n[验证2] 检查多余字段...")
    extra_fields = set(record.keys()) - set(REQUIRED_FIELDS.keys())
    if extra_fields:
        print(f"  ⚠️ 发现多余字段（数据库表中不存在）: {extra_fields}")
        print("  提示：这些字段将无法写入数据库")
    else:
        print("  ✅ 无多余字段")

    # 验证3: 检查相关系数字段是否有实际值
    print("\n[验证3] 检查相关系数字段...")
    corr_fields = ['corr_5m_7d', 'corr_1h_30d', 'corr_4h_60d']
    for field in corr_fields:
        value = record[field]
        if value is None:
            print(f"  ❌ {field} 为 None（应该有实际值）")
            return False
        elif not isinstance(value, (int, float)):
            print(f"  ❌ {field} 类型错误: {type(value)}（应为 float）")
            return False
        elif not (0.0 <= value <= 1.0):
            print(f"  ⚠️ {field} 值超出预期范围 [0.0, 1.0]: {value}")
        else:
            print(f"  ✅ {field}: {value:.4f}")

    # 验证4: 检查 Z-score 字段
    print("\n[验证4] 检查 Z-score 字段...")
    zscore_fields = ['zscore_5m', 'zscore_1h', 'zscore_4h']
    for field in zscore_fields:
        value = record[field]
        if value is None:
            print(f"  ❌ {field} 为 None")
            return False
        elif not isinstance(value, (int, float)):
            print(f"  ❌ {field} 类型错误: {type(value)}")
            return False
        else:
            print(f"  ✅ {field}: {value:+.2f}")

    # 验证5: 检查协整检验字段
    print("\n[验证5] 检查协整检验字段...")
    if not isinstance(record['cointegration_passed'], bool):
        print(f"  ❌ cointegration_passed 类型错误: {type(record['cointegration_passed'])}")
        return False
    else:
        print(f"  ✅ cointegration_passed: {record['cointegration_passed']}")

    if record['adf_pvalue'] is not None:
        print(f"  ⚠️ adf_pvalue 应为 None（多周期验证特性）: {record['adf_pvalue']}")
    else:
        print(f"  ✅ adf_pvalue: None（符合预期）")

    # 验证6: 检查信号字段
    print("\n[验证6] 检查信号字段...")
    if not isinstance(record['is_anomaly'], bool):
        print(f"  ❌ is_anomaly 类型错误: {type(record['is_anomaly'])}")
        return False
    else:
        print(f"  ✅ is_anomaly: {record['is_anomaly']}")

    if record['trading_direction'] not in ['long', 'short', 'none']:
        print(f"  ⚠️ trading_direction 值异常: {record['trading_direction']}")
    else:
        print(f"  ✅ trading_direction: {record['trading_direction']}")

    if record['signal_strength'] not in ['strong', 'medium', 'weak']:
        print(f"  ⚠️ signal_strength 值异常: {record['signal_strength']}")
    else:
        print(f"  ✅ signal_strength: {record['signal_strength']}")

    print("\n" + "=" * 80)
    print("✅ 所有验证通过！数据结构符合数据库表要求")
    print("=" * 80)

    return True


def main():
    """主函数"""
    # 模拟数据
    multi_period_result = simulate_multi_period_result()
    analysis_record = build_analysis_record('ALTUSDT', 'BTCUSDT', multi_period_result)

    # 验证
    success = validate_analysis_record(analysis_record)

    if success:
        print("\n✅ 数据库兼容性验证通过！")
        print("\n建议：")
        print("  1. 启动 realtime 服务进行实际测试")
        print("  2. 查询数据库验证数据写入：")
        print("     SELECT analysis_time, symbol, corr_5m_7d, corr_1h_30d, corr_4h_60d,")
        print("            zscore_5m, zscore_1h, zscore_4h, cointegration_passed")
        print("     FROM analysis_results")
        print("     WHERE analysis_time > NOW() - INTERVAL '1 hour'")
        print("     ORDER BY analysis_time DESC LIMIT 5;")
        return 0
    else:
        print("\n❌ 数据库兼容性验证失败！")
        return 1


if __name__ == '__main__':
    exit(main())
