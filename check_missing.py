#!/usr/bin/env python3
"""检查缺失字段的记录"""

import sys
sys.path.insert(0, '.')

from utils.timescaledb import TimescaleDBClient

def main():
    print('检查缺失字段的记录')
    print('=' * 80)

    try:
        client = TimescaleDBClient()

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        analysis_time,
                        symbol,
                        kline_time,
                        analysis_delay_seconds,
                        CASE
                            WHEN kline_time IS NULL THEN '缺失kline_time'
                            WHEN analysis_delay_seconds IS NULL THEN '缺失analysis_delay_seconds'
                            ELSE '正常'
                        END AS status
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '5 minutes'
                      AND (kline_time IS NULL OR analysis_delay_seconds IS NULL)
                    ORDER BY analysis_time DESC;
                ''')

                rows = cur.fetchall()
                if rows:
                    print(f'找到 {len(rows)} 条缺失记录：')
                    print()
                    for row in rows:
                        print(f'  时间: {row[0]}')
                        print(f'  币种: {row[1]}')
                        print(f'  kline_time: {row[2]}')
                        print(f'  analysis_delay_seconds: {row[3]}')
                        print(f'  状态: {row[4]}')
                        print()
                else:
                    print('✅ 无缺失记录')

        return 0

    except Exception as e:
        print(f'❌ 错误: {e}')
        return 1

if __name__ == '__main__':
    sys.exit(main())
