#!/usr/bin/env python3
"""
K线数据连续性诊断工具

验证指定币种的K线数据是否存在时间断点，并输出详细信息。
使用与主程序相同的判断逻辑（间隔 > 预期 + 1分钟容差）。

使用方法：
    python debug_continuity.py [symbol] [timeframe] [days]

示例：
    python debug_continuity.py                           # 默认检查 ARK, TNSR, HYPE
    python debug_continuity.py ARK/USDC:USDC 5m 7       # 检查特定币种
"""

import sys
from datetime import datetime, timezone, timedelta
from utils.timescaledb import TimescaleDBClient, KlineRepository


def check_continuity(
    kline_repo: KlineRepository,
    symbol: str,
    timeframe: str = '5m',
    days: int = 7
):
    """检查指定币种的K线数据连续性"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    klines = kline_repo.query_range(symbol, timeframe, start_time, end_time, limit=10000)

    print(f"\n{'='*60}")
    print(f"  {symbol} @ {timeframe} 连续性检查")
    print(f"{'='*60}")
    print(f"查询范围: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"数据条数: {len(klines)}")

    if len(klines) < 2:
        print("  数据不足，无法检查连续性")
        return None

    # 按时间升序排序（query_range 返回的是降序）
    sorted_klines = sorted(klines, key=lambda x: x['time'])

    # 计算预期间隔
    interval_map = {'5m': 5, '15m': 15, '1h': 60, '4h': 240}
    interval_minutes = interval_map.get(timeframe, 5)
    expected = timedelta(minutes=interval_minutes)
    tolerance = timedelta(minutes=1)

    print(f"预期间隔: {interval_minutes} 分钟 (容差: 1 分钟)")

    gaps = []
    for i in range(1, len(sorted_klines)):
        curr_time = sorted_klines[i]['time']
        prev_time = sorted_klines[i-1]['time']

        actual = curr_time - prev_time
        if actual > expected + tolerance:
            gap_count = int(actual / expected) - 1
            gaps.append({
                'prev_time': prev_time,
                'curr_time': curr_time,
                'actual_gap': actual,
                'missing_count': gap_count,
                'gap_minutes': actual.total_seconds() / 60
            })

    if gaps:
        total_missing = sum(g['missing_count'] for g in gaps)
        print(f"\n[!] 发现 {len(gaps)} 处时间断点，共缺失约 {total_missing} 条数据：\n")

        # 显示所有断点（按间隔大小排序）
        gaps_sorted = sorted(gaps, key=lambda x: x['gap_minutes'], reverse=True)

        for i, gap in enumerate(gaps_sorted[:15], 1):
            print(f"  {i:2d}. {gap['prev_time'].strftime('%m-%d %H:%M')} -> "
                  f"{gap['curr_time'].strftime('%m-%d %H:%M')}")
            print(f"      间隔: {gap['gap_minutes']:.0f} 分钟 | 缺失约 {gap['missing_count']} 条")

        if len(gaps) > 15:
            print(f"\n  ... 还有 {len(gaps) - 15} 处较小断点未显示")

        # 汇总统计
        print(f"\n断点统计：")
        print(f"   最大间隔: {max(g['gap_minutes'] for g in gaps):.0f} 分钟")
        print(f"   最小间隔: {min(g['gap_minutes'] for g in gaps):.0f} 分钟")
        print(f"   平均间隔: {sum(g['gap_minutes'] for g in gaps) / len(gaps):.1f} 分钟")

        return False
    else:
        print(f"\n[OK] 数据完全连续，无断点")
        return True


def compare_with_base(
    kline_repo: KlineRepository,
    alt_symbol: str,
    base_symbol: str = 'HYPE/USDC:USDC',
    timeframe: str = '5m',
    days: int = 7
):
    """对比目标币种与基准币种在同一时间的数据情况"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    alt_klines = kline_repo.query_range(alt_symbol, timeframe, start_time, end_time, limit=10000)
    base_klines = kline_repo.query_range(base_symbol, timeframe, start_time, end_time, limit=10000)

    alt_times = set(k['time'] for k in alt_klines)
    base_times = set(k['time'] for k in base_klines)

    # 基准有但目标没有的时间点
    missing_in_alt = base_times - alt_times

    print(f"\n{'='*60}")
    print(f"  对比分析: {alt_symbol} vs {base_symbol}")
    print(f"{'='*60}")
    print(f"基准币种数据点: {len(base_times)}")
    print(f"目标币种数据点: {len(alt_times)}")
    print(f"目标缺失时间点: {len(missing_in_alt)}")

    if missing_in_alt:
        missing_sorted = sorted(missing_in_alt)[:10]
        print(f"\n目标币种缺失的时间点（显示前10个）：")
        for t in missing_sorted:
            print(f"  - {t.strftime('%Y-%m-%d %H:%M')}")


def main():
    # 初始化数据库连接
    db_client = TimescaleDBClient()
    kline_repo = KlineRepository(db_client)

    # 解析命令行参数
    if len(sys.argv) >= 2:
        symbol = sys.argv[1]
        timeframe = sys.argv[2] if len(sys.argv) >= 3 else '5m'
        days = int(sys.argv[3]) if len(sys.argv) >= 4 else 7
        check_continuity(kline_repo, symbol, timeframe, days)
    else:
        # 默认检查日志中的问题币种
        print("\n" + "="*60)
        print("  K线数据连续性诊断工具")
        print("="*60)

        # 1. 检查问题币种
        check_continuity(kline_repo, 'ARK/USDC:USDC', '5m', 7)
        check_continuity(kline_repo, 'TNSR/USDC:USDC', '5m', 7)

        # 2. 检查基准币种作为对照
        check_continuity(kline_repo, 'HYPE/USDC:USDC', '5m', 7)

        # 3. 对比分析
        compare_with_base(kline_repo, 'ARK/USDC:USDC')
        compare_with_base(kline_repo, 'TNSR/USDC:USDC')


if __name__ == '__main__':
    main()
