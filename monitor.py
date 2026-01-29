#!/usr/bin/env python3
"""持续监控修复效果"""

import sys
import time
from datetime import datetime

sys.path.insert(0, '.')

from utils.timescaledb import TimescaleDBClient

def monitor_once():
    """执行一次监控"""
    try:
        client = TimescaleDBClient()

        with client.get_connection() as conn:
            with conn.cursor() as cur:
                # 查询最近1分钟的数据
                cur.execute('''
                    SELECT
                        COUNT(*) AS records,
                        COUNT(DISTINCT symbol) AS symbols,
                        COUNT(kline_time) AS has_kline_time,
                        COUNT(analysis_delay_seconds) AS has_delay,
                        COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
                        ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds)::NUMERIC, 2) AS p95_delay
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '1 minute';
                ''')

                row = cur.fetchone()

                # 显示结果
                status = '✅' if row[0] > 0 and row[2] == row[0] and row[3] == row[0] and row[4] == 0 else '⚠️'

                print(f'{status} {datetime.now().strftime("%H:%M:%S")} | '
                      f'记录:{row[0]:3d} 币种:{row[1]:2d} | '
                      f'kline:{row[2]}/{row[0]} delay:{row[3]}/{row[0]} | '
                      f'负延迟:{row[4]} | '
                      f'平均:{row[5] if row[5] else 0:.1f}s P95:{row[6] if row[6] else 0:.1f}s')

                return row[0] > 0

    except Exception as e:
        print(f'❌ {datetime.now().strftime("%H:%M:%S")} | 错误: {e}')
        return False

def main():
    print('=' * 100)
    print('持续监控（每分钟检查一次，共10次）')
    print('=' * 100)
    print()
    print('时间     | 记录数 币种数 | 字段完整性 | 负延迟 | 延迟指标')
    print('-' * 100)

    for i in range(10):
        has_data = monitor_once()

        if i < 9:  # 不是最后一次
            time.sleep(60)

    print('-' * 100)
    print()
    print('✅ 监控完成')
    return 0

if __name__ == '__main__':
    sys.exit(main())
