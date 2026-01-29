#!/usr/bin/env python3
"""验证修复效果"""

import sys
sys.path.insert(0, '.')

from utils.timescaledb import TimescaleDBClient
from utils.logging_config import get_logger

logger = get_logger(__name__)

def main():
    print('=' * 80)
    print('验证修复效果')
    print('=' * 80)
    print()

    try:
        client = TimescaleDBClient()

        # 验证1: 时区正确性
        print('验证1: 时区正确性（最近5分钟）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        symbol,
                        kline_time,
                        analysis_time,
                        EXTRACT(TIMEZONE_HOUR FROM kline_time) AS kline_tz_offset,
                        EXTRACT(TIMEZONE_HOUR FROM analysis_time) AS analysis_tz_offset,
                        CASE
                            WHEN EXTRACT(TIMEZONE_HOUR FROM kline_time) = 0
                                 AND EXTRACT(TIMEZONE_HOUR FROM analysis_time) = 0 THEN '✓ UTC+0'
                            ELSE '❌ 时区错误'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes'
                    ORDER BY analysis_time DESC
                    LIMIT 5;
                ''')

                rows = cur.fetchall()
                if rows:
                    for row in rows:
                        print(f'  {row[0]}: {row[5]}')
                else:
                    print('  (暂无新数据)')
                print()

        # 验证2: 延迟准确性
        print('验证2: 延迟准确性（最近5分钟）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        symbol,
                        analysis_delay_seconds AS stored_delay,
                        EXTRACT(EPOCH FROM (analysis_time - kline_time)) AS calculated_delay,
                        ABS(analysis_delay_seconds - EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS error,
                        CASE
                            WHEN ABS(analysis_delay_seconds - EXTRACT(EPOCH FROM (analysis_time - kline_time))) < 0.01 THEN '✓ 准确'
                            ELSE '❌ 误差过大'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes'
                      AND analysis_delay_seconds IS NOT NULL
                    ORDER BY analysis_time DESC
                    LIMIT 5;
                ''')

                rows = cur.fetchall()
                if rows:
                    for row in rows:
                        print(f'  {row[0]}: 存储{row[1]:.2f}s 计算{row[2]:.2f}s 误差{row[3]:.6f}s - {row[4]}')
                else:
                    print('  (暂无新数据)')
                print()

        # 验证3: 字段完整性
        print('验证3: 字段完整性（最近5分钟）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(kline_time) AS has_kline_time,
                        COUNT(analysis_delay_seconds) AS has_delay_seconds,
                        CASE
                            WHEN COUNT(kline_time) = COUNT(*) AND COUNT(analysis_delay_seconds) = COUNT(*) THEN '✓ 完整'
                            ELSE '❌ 缺失字段'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes';
                ''')

                row = cur.fetchone()
                print(f'  总记录数: {row[0]}')
                print(f'  kline_time: {row[1]}/{row[0]}')
                print(f'  analysis_delay_seconds: {row[2]}/{row[0]}')
                print(f'  状态: {row[3]}')
                print()

        # 验证4: 延迟分布
        print('验证4: 延迟分布（最近5分钟）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS sample_size,
                        ROUND(MIN(analysis_delay_seconds)::NUMERIC, 2) AS min_delay,
                        ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds)::NUMERIC, 2) AS p95_delay,
                        ROUND(MAX(analysis_delay_seconds)::NUMERIC, 2) AS max_delay,
                        CASE
                            WHEN AVG(analysis_delay_seconds) BETWEEN 3 AND 10
                                 AND PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds) < 20 THEN '✓ 健康'
                            ELSE '⚠️ 需优化'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes'
                      AND analysis_delay_seconds IS NOT NULL;
                ''')

                row = cur.fetchone()
                if row[0] > 0:
                    print(f'  样本数: {row[0]}')
                    print(f'  最小延迟: {row[1]}s')
                    print(f'  平均延迟: {row[2]}s')
                    print(f'  P95延迟: {row[3]}s')
                    print(f'  最大延迟: {row[4]}s')
                    print(f'  状态: {row[5]}')
                else:
                    print('  (暂无数据)')
                print()

        # 验证5: 无负延迟
        print('验证5: 无负延迟（最近5分钟）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
                        CASE
                            WHEN COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) = 0 THEN '✓ 无负延迟'
                            ELSE '❌ 存在负延迟'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes';
                ''')

                row = cur.fetchone()
                print(f'  总记录数: {row[0]}')
                print(f'  负延迟数: {row[1]}')
                print(f'  状态: {row[2]}')
                print()

        # 总结
        print('=' * 80)
        print('验证总结')
        print('=' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(DISTINCT symbol) AS active_symbols,
                        ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
                        COUNT(CASE WHEN kline_time IS NULL THEN 1 END) AS missing_kline_time,
                        COUNT(CASE WHEN analysis_delay_seconds IS NULL THEN 1 END) AS missing_delay,
                        COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
                        CASE
                            WHEN COUNT(CASE WHEN kline_time IS NULL THEN 1 END) = 0
                                 AND COUNT(CASE WHEN analysis_delay_seconds IS NULL THEN 1 END) = 0
                                 AND COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) = 0 THEN '✅ 修复成功'
                            ELSE '❌ 仍有问题'
                        END AS overall_status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes';
                ''')

                row = cur.fetchone()
                print(f'  最近5分钟记录数: {row[0]}')
                print(f'  活跃币种数: {row[1]}')
                print(f'  平均延迟: {row[2]}s')
                print(f'  kline_time缺失: {row[3]}')
                print(f'  analysis_delay_seconds缺失: {row[4]}')
                print(f'  负延迟数: {row[5]}')
                print()
                print(f'  📊 总体状态: {row[6]}')

        return 0

    except Exception as e:
        print(f'❌ 错误: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
