#!/usr/bin/env python3
"""
修复 detect_missing_data 方法的检测逻辑

将此方法替换到 validate_data_consistency.py 中
"""

from typing import List, Dict, Optional, Any
from utils.logging_config import logger


def detect_missing_data_fixed(
    self,
    hours: int = 24,
    symbol: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    检测分析结果中的数据完整性（修复后的版本）

    ⚠️ 修复说明：
    原版本检测的是 klines 表中的K线数据（在分析时刻±1小时内），
    这导致大量误报，因为：
    1. 4h周期的K线每4小时才更新一次，在1小时窗口内经常找不到
    2. 但分析实际使用的是更早的历史数据（7-60天），可能是完整的

    修复后的版本直接检测 analysis_results 表中的字段完整性，
    这才是真正反映数据完整性的指标。

    Args:
        hours: 查询最近N小时的数据
        symbol: 指定币种（可选）

    Returns:
        数据不完整的记录列表，每条记录包含：
        - symbol: 币种
        - analysis_time: 分析时间
        - created_at: 创建时间
        - has_5m_corr, has_1h_corr, has_4h_corr: 相关系数完整性
        - has_5m_zscore, has_1h_zscore, has_4h_zscore: Z-score完整性
        - complete_periods: 完整周期数（0-3）
    """
    logger.info(f"开始检测分析结果数据完整性（最近{hours}小时）...")

    query = """
        SELECT
            symbol,
            analysis_time,
            created_at,
            -- 相关系数完整性
            (corr_5m_7d IS NOT NULL) as has_5m_corr,
            (corr_1h_30d IS NOT NULL) as has_1h_corr,
            (corr_4h_60d IS NOT NULL) as has_4h_corr,
            -- Z-score完整性
            (zscore_5m IS NOT NULL) as has_5m_zscore,
            (zscore_1h IS NOT NULL) as has_1h_zscore,
            (zscore_4h IS NOT NULL) as has_4h_zscore,
            -- 完整周期数（基于相关系数）
            (corr_5m_7d IS NOT NULL)::int +
            (corr_1h_30d IS NOT NULL)::int +
            (corr_4h_60d IS NOT NULL)::int as complete_periods
        FROM analysis_results
        WHERE created_at > NOW() - INTERVAL '%s hours'
            AND (
                corr_5m_7d IS NULL OR
                corr_1h_30d IS NULL OR
                corr_4h_60d IS NULL OR
                zscore_5m IS NULL OR
                zscore_1h IS NULL OR
                zscore_4h IS NULL
            )
    """

    params = [hours]

    if symbol:
        query += " AND symbol = %s"
        params.append(symbol)

    query += " ORDER BY created_at DESC LIMIT 100"

    try:
        records = self.client.execute_query(query, tuple(params))
        if records:
            logger.warning(f"  发现 {len(records)} 条数据不完整记录")
            for record in records:
                # 识别缺失的周期
                missing_fields = []
                if not record['has_5m_corr']:
                    missing_fields.append('5m')
                if not record['has_1h_corr']:
                    missing_fields.append('1h')
                if not record['has_4h_corr']:
                    missing_fields.append('4h')

                self.warnings.append(
                    f"数据不完整: {record['symbol']} @ {record['analysis_time']} | "
                    f"缺失周期: {', '.join(missing_fields)} | "
                    f"完整周期数: {record['complete_periods']}/3"
                )
        else:
            logger.info("  ✅ 所有记录数据完整")
        return records or []
    except Exception as e:
        logger.error(f"  数据完整性检测失败 - {e}")
        return []


# 测试函数
def test_detect_missing_data():
    """测试修复后的detect_missing_data方法"""
    from utils.timescaledb import TimescaleDBClient
    from dataclasses import dataclass

    @dataclass
    class ValidationConfig:
        lag_threshold_seconds: int = 60
        coverage_threshold_pct: float = 95.0
        max_concurrent_queries: int = 3

    class MockValidator:
        def __init__(self):
            self.client = TimescaleDBClient()
            self.warnings = []
            self.config = ValidationConfig()

        def detect_missing_data(self, hours: int = 24, symbol: Optional[str] = None):
            return detect_missing_data_fixed(self, hours, symbol)

    print("=" * 80)
    print("测试修复后的 detect_missing_data 方法")
    print("=" * 80)
    print()

    validator = MockValidator()

    print("测试1: 检查最近1小时的数据")
    print("-" * 80)
    results = validator.detect_missing_data(hours=1)
    print(f"发现不完整记录: {len(results)} 条")

    if results:
        print("\n示例记录:")
        for i, record in enumerate(results[:5], 1):
            print(f"{i}. {record['symbol']} @ {record['analysis_time']}")
            print(f"   相关系数: 5m={record['has_5m_corr']}, "
                  f"1h={record['has_1h_corr']}, 4h={record['has_4h_corr']}")
            print(f"   Z-score: 5m={record['has_5m_zscore']}, "
                  f"1h={record['has_1h_zscore']}, 4h={record['has_4h_zscore']}")
            print(f"   完整周期数: {record['complete_periods']}/3")
    else:
        print("✅ 所有记录数据都完整！")

    print()
    print("=" * 80)
    print("对比：旧方法的结果")
    print("=" * 80)
    print()

    # 运行旧方法的查询逻辑
    old_query = """
        WITH timeframe_bits AS (
            SELECT
                a.symbol,
                a.analysis_time,
                BIT_OR(
                    CASE k.timeframe
                        WHEN '5m' THEN 1
                        WHEN '1h' THEN 2
                        WHEN '4h' THEN 4
                        ELSE 0
                    END
                ) as available_mask
            FROM analysis_results a
            LEFT JOIN klines k ON
                k.symbol = a.symbol
                AND k.timeframe IN ('5m', '1h', '4h')
                AND k.time BETWEEN a.analysis_time - INTERVAL '1 hour' AND a.analysis_time
            WHERE a.analysis_time > NOW() - INTERVAL '1 hour'
            GROUP BY a.symbol, a.analysis_time
        )
        SELECT
            COUNT(*) as total_flagged
        FROM timeframe_bits
        WHERE available_mask IS NULL OR available_mask != 7
    """

    old_result = validator.client.execute_query(old_query, fetch_one=True)
    print(f"旧方法标记为'缺失'的记录数: {old_result['total_flagged']} 条")
    print(f"新方法发现不完整的记录数: {len(results)} 条")
    print(f"差异（误报数）: {old_result['total_flagged'] - len(results)} 条")

    if old_result['total_flagged'] > len(results):
        print(f"\n✅ 修复成功！消除了 {old_result['total_flagged'] - len(results)} 条误报")

    validator.client.close()


if __name__ == '__main__':
    test_detect_missing_data()
