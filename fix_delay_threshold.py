#!/usr/bin/env python3
"""
快速修复：调整延迟验证阈值

问题：
- 延迟计算包含K线周期（5m = 300秒）
- 当前阈值60秒必然触发告警
- 导致100%误报率

解决：
- 调整阈值至360秒（300秒K线周期 + 60秒处理余量）
- 在报告中区分"总延迟"和"真实延迟"
- 添加延迟计算说明
"""

from utils.timescaledb import TimescaleDBClient

# K线周期（秒）
KLINE_PERIODS = {
    '5m': 300,
    '1h': 3600,
    '4h': 14400
}

# 默认使用5m周期
DEFAULT_PERIOD = '5m'
KLINE_PERIOD_SECONDS = KLINE_PERIODS[DEFAULT_PERIOD]

# 新的延迟阈值：K线周期 + 合理处理时间
NEW_THRESHOLD = KLINE_PERIOD_SECONDS + 60  # 360秒


def test_delay_calculation():
    """
    测试延迟计算的正确性

    对比：
    1. 当前延迟（包含K线周期）
    2. 真实延迟（减去K线周期）
    """
    client = TimescaleDBClient()

    query = """
        SELECT
            COUNT(*) as total_records,
            AVG(analysis_delay_seconds) as avg_current_delay,
            MAX(analysis_delay_seconds) as max_current_delay,
            MIN(analysis_delay_seconds) as min_current_delay,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p95_current_delay
        FROM analysis_results
        WHERE created_at > NOW() - INTERVAL '1 hour'
            AND analysis_delay_seconds IS NOT NULL
    """

    result = client.execute_query(query, fetch_one=True)

    if result and result['total_records'] > 0:
        print("=" * 80)
        print("延迟分析报告（包含修正）")
        print("=" * 80)
        print()

        print("📊 样本统计")
        print(f"  记录数量: {result['total_records']} 条")
        print()

        print("⏱️  总延迟（包含K线周期）")
        print(f"  平均: {result['avg_current_delay']:.2f}秒")
        print(f"  最小: {result['min_current_delay']:.2f}秒")
        print(f"  P95:  {result['p95_current_delay']:.2f}秒")
        print(f"  最大: {result['max_current_delay']:.2f}秒")
        print()

        # 计算真实延迟
        real_avg = result['avg_current_delay'] - KLINE_PERIOD_SECONDS
        real_max = result['max_current_delay'] - KLINE_PERIOD_SECONDS
        real_min = result['min_current_delay'] - KLINE_PERIOD_SECONDS
        real_p95 = result['p95_current_delay'] - KLINE_PERIOD_SECONDS

        print(f"✅ 真实延迟（减去{DEFAULT_PERIOD}周期 {KLINE_PERIOD_SECONDS}秒）")
        print(f"  平均: {real_avg:.2f}秒")
        print(f"  最小: {real_min:.2f}秒")
        print(f"  P95:  {real_p95:.2f}秒")
        print(f"  最大: {real_max:.2f}秒")
        print()

        # 阈值对比
        print("🚨 告警阈值评估")
        print(f"  旧阈值: 60秒")
        print(f"  新阈值: {NEW_THRESHOLD}秒（{KLINE_PERIOD_SECONDS}秒周期 + 60秒余量）")
        print()

        # 告警判断
        old_threshold = 60
        if result['avg_current_delay'] > old_threshold:
            print(f"  ❌ 旧阈值下告警: 平均延迟{result['avg_current_delay']:.1f}秒 > {old_threshold}秒")
        else:
            print(f"  ✅ 旧阈值下正常: 平均延迟{result['avg_current_delay']:.1f}秒 ≤ {old_threshold}秒")

        if result['avg_current_delay'] > NEW_THRESHOLD:
            print(f"  ⚠️  新阈值下告警: 平均延迟{result['avg_current_delay']:.1f}秒 > {NEW_THRESHOLD}秒")
        else:
            print(f"  ✅ 新阈值下正常: 平均延迟{result['avg_current_delay']:.1f}秒 ≤ {NEW_THRESHOLD}秒")
        print()

        # 修复建议
        print("💡 修复建议")
        if real_avg < 60:
            print(f"  • 真实延迟{real_avg:.1f}秒良好（<60秒），系统性能优秀")
            print("  • 建议：调整验证脚本阈值至360秒")
            print("  • 长期：修改延迟计算使用K线闭合时间")
        elif real_avg < 180:
            print(f"  • 真实延迟{real_avg:.1f}秒可接受（60-180秒）")
            print("  • 建议：优化数据采集流程")
        else:
            print(f"  • 真实延迟{real_avg:.1f}秒偏高（>180秒）")
            print("  • 建议：深入排查延迟原因")

    else:
        print("❌ 无有效数据")

    client.close()


def suggest_fixes():
    """
    生成修复代码片段
    """
    print()
    print("=" * 80)
    print("推荐修复方案")
    print("=" * 80)
    print()

    print("方案1：快速修复 - 调整validate_data_consistency.py阈值")
    print("-" * 80)
    print("""
# 文件: validate_data_consistency.py
# 位置: calculate_lag_statistics 方法中的告警逻辑

# 修改前：
if stats['avg_lag'] > 60:
    self.warnings.append(f"⚠️ 平均延迟过高: {stats['avg_lag']:.1f}秒")

# 修改后：
KLINE_PERIOD = 300  # 5m K线周期
THRESHOLD = 360     # 周期 + 60秒余量

real_delay = stats['avg_lag'] - KLINE_PERIOD

if stats['avg_lag'] > THRESHOLD:
    self.warnings.append(
        f"⚠️ 平均延迟过高: {stats['avg_lag']:.1f}秒 "
        f"(包含{KLINE_PERIOD}秒K线周期, 真实延迟约{real_delay:.1f}秒)"
    )
elif real_delay < 60:
    # 真实延迟良好
    logger.info(f"✅ 延迟正常: 真实延迟{real_delay:.1f}秒")
""")

    print()
    print("方案2：长期优化 - 修改realtime_kline_service.py延迟计算")
    print("-" * 80)
    print("""
# 文件: realtime_kline_service.py
# 位置: _analyze_and_alert 方法中的延迟计算（第1274行）

# 修改前：
delay_seconds = (analysis_now - kline_time).total_seconds() if kline_time else 0

# 修改后：
from datetime import timedelta

# 计算K线闭合时间
timeframe_minutes = {
    '5m': 5,
    '1h': 60,
    '4h': 240
}.get(timeframe, 5)

kline_close_time = (
    kline_time + timedelta(minutes=timeframe_minutes)
    if kline_time else analysis_now
)
delay_seconds = (analysis_now - kline_close_time).total_seconds()

# 注释说明
# delay_seconds 现在表示：分析完成时间 - K线闭合时间
# 这才是真正的"数据新鲜度"指标
""")


if __name__ == '__main__':
    test_delay_calculation()
    suggest_fixes()
