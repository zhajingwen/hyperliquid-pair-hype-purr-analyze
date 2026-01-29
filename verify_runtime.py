#!/usr/bin/env python
"""
运行时验证脚本
在服务重启后执行，验证新字段是否正常工作
"""
import sys
sys.path.insert(0, '.venv/lib/python3.14/site-packages')

import psycopg
from datetime import datetime, timedelta

# 数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 5432,
    'database': 'crypto_data',
    'user': 'postgres',
    'password': 'postgres'
}

def verify_runtime():
    """验证运行时新数据"""
    print("=" * 70)
    print("运行时验证：新字段数据正确性检查")
    print("=" * 70)

    conninfo = f"host={DB_CONFIG['host']} port={DB_CONFIG['port']} " \
               f"dbname={DB_CONFIG['database']} user={DB_CONFIG['user']} " \
               f"password={DB_CONFIG['password']}"

    try:
        with psycopg.connect(conninfo) as conn:
            with conn.cursor() as cur:
                # 1. 检查最近15分钟的新数据
                print("\n1. 检查最近15分钟的新数据:")
                print("-" * 70)

                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(kline_time) as kline_time_filled,
                        COUNT(analysis_delay_seconds) as delay_filled,
                        MIN(analysis_time) as earliest,
                        MAX(analysis_time) as latest
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '15 minutes';
                """)

                result = cur.fetchone()
                total, kline_filled, delay_filled, earliest, latest = result

                print(f"  总记录数: {total}")
                print(f"  kline_time 填充: {kline_filled}/{total} " +
                      f"({'✓ 完整' if kline_filled == total else '✗ 不完整'})")
                print(f"  delay 填充: {delay_filled}/{total} " +
                      f"({'✓ 完整' if delay_filled == total else '✗ 不完整'})")
                print(f"  时间范围: {earliest} ~ {latest}")

                if total == 0:
                    print("\n⚠️  提示：暂无新数据")
                    print("   原因：服务可能刚重启，或尚未产生新的分析记录")
                    print("   建议：等待5-10分钟后再次执行验证")
                    return True

                # 2. 验证延迟计算准确性
                print("\n2. 验证延迟计算准确性（最近10条）:")
                print("-" * 70)

                cur.execute("""
                    SELECT
                        symbol,
                        kline_time,
                        analysis_time,
                        analysis_delay_seconds,
                        EXTRACT(EPOCH FROM (analysis_time - kline_time)) as calculated_delay,
                        ABS(analysis_delay_seconds - EXTRACT(EPOCH FROM (analysis_time - kline_time))) as diff
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '15 minutes'
                    AND kline_time IS NOT NULL
                    ORDER BY analysis_time DESC
                    LIMIT 10;
                """)

                records = cur.fetchall()
                max_diff = 0
                for symbol, kline_time, analysis_time, delay_stored, delay_calc, diff in records:
                    status = "✓" if diff < 0.001 else "✗"
                    print(f"  {status} {symbol:20s} 延迟: {delay_stored:6.2f}s (计算值: {delay_calc:6.2f}s, 误差: {diff:.4f}s)")
                    max_diff = max(max_diff, diff)

                if max_diff < 0.001:
                    print(f"  ✓ 延迟计算准确（最大误差: {max_diff:.6f}秒）")
                else:
                    print(f"  ⚠️  延迟计算存在误差（最大误差: {max_diff:.6f}秒）")

                # 3. 验证 kline_time 与 klines 表对齐
                print("\n3. 验证 kline_time 与 klines 表对齐:")
                print("-" * 70)

                cur.execute("""
                    SELECT
                        a.symbol,
                        a.kline_time,
                        k.time as klines_time,
                        CASE
                            WHEN a.kline_time = k.time THEN '✓ 对齐'
                            ELSE '✗ 不对齐'
                        END as status
                    FROM analysis_results a
                    LEFT JOIN klines k ON
                        a.symbol = k.symbol
                        AND k.timeframe = '5m'
                        AND k.time = a.kline_time
                    WHERE a.analysis_time > NOW() - INTERVAL '15 minutes'
                    AND a.kline_time IS NOT NULL
                    ORDER BY a.analysis_time DESC
                    LIMIT 10;
                """)

                records = cur.fetchall()
                aligned_count = 0
                for symbol, kline_time, klines_time, status in records:
                    print(f"  {status:10s} {symbol:20s} {kline_time}")
                    if status == '✓ 对齐':
                        aligned_count += 1

                if aligned_count == len(records):
                    print(f"  ✓ 所有记录完美对齐 ({aligned_count}/{len(records)})")
                else:
                    print(f"  ⚠️  部分记录未对齐 ({aligned_count}/{len(records)})")

                # 4. 延迟分布统计
                print("\n4. 延迟分布统计（最近15分钟）:")
                print("-" * 70)

                cur.execute("""
                    SELECT
                        MIN(analysis_delay_seconds) as min_delay,
                        AVG(analysis_delay_seconds) as avg_delay,
                        MAX(analysis_delay_seconds) as max_delay,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p50,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p95,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p99
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '15 minutes'
                    AND analysis_delay_seconds IS NOT NULL;
                """)

                result = cur.fetchone()
                if result:
                    min_delay, avg_delay, max_delay, p50, p95, p99 = result

                    print(f"  最小延迟: {min_delay:.2f}s")
                    print(f"  平均延迟: {avg_delay:.2f}s")
                    print(f"  最大延迟: {max_delay:.2f}s")
                    print(f"  P50 延迟: {p50:.2f}s")
                    print(f"  P95 延迟: {p95:.2f}s")
                    print(f"  P99 延迟: {p99:.2f}s")

                    # 延迟评估
                    if avg_delay < 10:
                        print(f"  ✓ 平均延迟正常（< 10秒）")
                    elif avg_delay < 15:
                        print(f"  ⚠️  平均延迟偏高（10-15秒）")
                    else:
                        print(f"  ✗ 平均延迟异常（> 15秒）")

                # 5. 去重验证
                print("\n5. 去重逻辑验证（最近1小时）:")
                print("-" * 70)

                cur.execute("""
                    SELECT
                        DATE_TRUNC('minute', analysis_time) as minute,
                        symbol,
                        COUNT(*) as count
                    FROM analysis_results
                    WHERE analysis_time > NOW() - INTERVAL '1 hour'
                    GROUP BY minute, symbol
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                    LIMIT 10;
                """)

                duplicates = cur.fetchall()
                if duplicates:
                    print(f"  ✗ 发现重复记录:")
                    for minute, symbol, count in duplicates:
                        print(f"    {minute} | {symbol} | {count} 条")
                else:
                    print(f"  ✓ 无重复记录（去重正常）")

        print("\n" + "=" * 70)
        print("✓ 运行时验证完成")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n✗ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = verify_runtime()
    exit(0 if success else 1)
