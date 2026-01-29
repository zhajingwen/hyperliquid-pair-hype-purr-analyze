#!/usr/bin/env python3
"""验证修复后的新数据"""

import sys
sys.path.insert(0, '.')

from utils.timescaledb import TimescaleDBClient

def main():
    print('=' * 80)
    print('验证修复后的新数据（14:55之后）')
    print('=' * 80)
    print()

    try:
        client = TimescaleDBClient()

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                # 查询14:55之后的数据
                cur.execute('''
                    SELECT
                        COUNT(*) AS total_records,
                        COUNT(kline_time) AS has_kline_time,
                        COUNT(analysis_delay_seconds) AS has_delay_seconds,
                        COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
                        ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds)::NUMERIC, 2) AS p95_delay
                    FROM analysis_results
                    WHERE analysis_time > '2026-01-29 14:55:00+00:00';
                ''')

                row = cur.fetchone()

                print(f'  总记录数: {row[0]}')
                print(f'  kline_time 完整: {row[1]}/{row[0]} ({100.0*row[1]/row[0] if row[0]>0 else 0:.1f}%)')
                print(f'  analysis_delay_seconds 完整: {row[2]}/{row[0]} ({100.0*row[2]/row[0] if row[0]>0 else 0:.1f}%)')
                print(f'  负延迟数: {row[3]}')
                print(f'  平均延迟: {row[4]}s')
                print(f'  P95延迟: {row[5]}s')
                print()

                # 判断结果
                if row[0] > 0:
                    if row[1] == row[0] and row[2] == row[0] and row[3] == 0:
                        print('  ✅ 修复后的新数据100%完整且正确！')
                        print()
                        print('=' * 80)
                        print('🎉 修复验证成功！')
                        print('=' * 80)
                        return 0
                    else:
                        print('  ❌ 修复后的数据仍有问题')
                        return 1
                else:
                    print('  ⚠️  暂无修复后的新数据，需要继续观察')
                    return 0

    except Exception as e:
        print(f'❌ 错误: {e}')
        return 1

if __name__ == '__main__':
    sys.exit(main())
