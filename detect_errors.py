#!/usr/bin/env python3
"""检测历史数据时区错误"""

import sys
sys.path.insert(0, '.')

from utils.timescaledb import TimescaleDBClient
from utils.logging_config import get_logger

logger = get_logger(__name__)

def main():
    print('=' * 80)
    print('检测历史数据时区错误')
    print('=' * 80)
    print()

    try:
        client = TimescaleDBClient()

        # 检测1: 负延迟（8小时偏移标志）
        print('检测1: 负延迟（8小时偏移标志）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        symbol,
                        kline_time,
                        analysis_time,
                        analysis_delay_seconds,
                        EXTRACT(EPOCH FROM (analysis_time - kline_time)) AS calculated_delay,
                        CASE
                            WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN '⚠️ 8小时偏移'
                            WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) > 3600 THEN '⚠️ 异常延迟'
                            WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < 0 THEN '⚠️ 负延迟'
                            ELSE '✓ 正常'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '1 day'
                    ORDER BY analysis_time DESC
                    LIMIT 10;
                ''')

                rows = cur.fetchall()
                if rows:
                    for row in rows:
                        print(f'  {row[0]}: {row[5]}')
                else:
                    print('  (无数据)')
                print()

        # 检测2: 统计时区偏移数据
        print('检测2: 时区偏移统计（最近7天）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN 1 END) AS offset_8h_records,
                        COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < 0 THEN 1 END) AS negative_delay_records,
                        COUNT(CASE WHEN kline_time IS NULL THEN 1 END) AS null_kline_time,
                        COUNT(CASE WHEN analysis_delay_seconds IS NULL THEN 1 END) AS null_delay_seconds,
                        ROUND(
                            100.0 * COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN 1 END) / NULLIF(COUNT(*), 0),
                            2
                        ) AS offset_percentage
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '7 days';
                ''')

                row = cur.fetchone()
                print(f'  总记录数: {row[0]}')
                print(f'  8小时偏移记录: {row[1]} ({row[5]}%)')
                print(f'  负延迟记录: {row[2]}')
                print(f'  kline_time为NULL: {row[3]}')
                print(f'  analysis_delay_seconds为NULL: {row[4]}')
                print()

        # 检测3: 字段完整性
        print('检测3: 字段完整性（最近7天）')
        print('-' * 80)

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(kline_time) AS has_kline_time,
                        COUNT(analysis_delay_seconds) AS has_delay_seconds,
                        ROUND(100.0 * COUNT(kline_time) / NULLIF(COUNT(*), 0), 2) AS kline_time_coverage,
                        ROUND(100.0 * COUNT(analysis_delay_seconds) / NULLIF(COUNT(*), 0), 2) AS delay_seconds_coverage
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '7 days';
                ''')

                row = cur.fetchone()
                print(f'  总记录数: {row[0]}')
                print(f'  kline_time覆盖率: {row[3]}%')
                print(f'  analysis_delay_seconds覆盖率: {row[4]}%')
                print()

        print('✅ 检测完成')
        return 0

    except Exception as e:
        print(f'❌ 错误: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
