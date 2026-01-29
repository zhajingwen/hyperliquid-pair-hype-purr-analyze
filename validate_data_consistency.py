#!/usr/bin/env python3
"""
数据一致性验证脚本

验证K线数据和分析结果之间的时间一致性，确保分析使用的是最新的K线数据。

功能：
1. 多周期K线时间差验证（5m/1h/4h）
2. 数据缺失检测
3. 时间延迟统计（平均值、最大值、P95）
4. K线数据覆盖率检查

Author: Claude
Date: 2026-01-29
"""

import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import defaultdict

from utils.timescaledb import TimescaleDBClient
from utils.logging_config import logger


class DataConsistencyValidator:
    """数据一致性验证器"""

    def __init__(self, client: Optional[TimescaleDBClient] = None):
        self.client = client or TimescaleDBClient()
        self.timeframes = ['5m', '1h', '4h']
        self.warnings: List[str] = []

    def validate_multiperiod_lags(
        self,
        hours: int = 1,
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        验证多周期K线时间差

        Args:
            hours: 查询最近N小时的数据
            symbol: 指定币种（可选）
            limit: 每个周期最多返回记录数

        Returns:
            字典，键为时间周期，值为时间差记录列表
        """
        logger.info(f"开始验证多周期K线时间差（最近{hours}小时）...")
        results = {}

        for timeframe in self.timeframes:
            query = """
                SELECT 
                    a.symbol,
                    a.analysis_time,
                    k.time as kline_time,
                    EXTRACT(EPOCH FROM (a.analysis_time - k.time)) as lag_seconds
                FROM analysis_results a
                LEFT JOIN LATERAL (
                    SELECT time FROM klines 
                    WHERE symbol = a.symbol 
                    AND timeframe = %s
                    AND time <= a.analysis_time
                    ORDER BY time DESC LIMIT 1
                ) k ON true
                WHERE a.analysis_time > NOW() - INTERVAL '%s hours'
            """

            params = [timeframe, hours]

            if symbol:
                query += " AND a.symbol = %s"
                params.append(symbol)

            query += f" ORDER BY a.analysis_time DESC LIMIT {limit};"

            try:
                records = self.client.execute_query(query, tuple(params))
                results[timeframe] = records or []
                logger.info(f"  {timeframe}: 查询到 {len(results[timeframe])} 条记录")
            except Exception as e:
                logger.error(f"  {timeframe}: 查询失败 - {e}")
                results[timeframe] = []

        return results

    def detect_missing_data(
        self,
        hours: int = 24,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检测数据缺失

        查找存在分析结果但缺少对应K线数据的情况。

        Args:
            hours: 查询最近N小时的数据
            symbol: 指定币种（可选）

        Returns:
            缺失数据记录列表
        """
        logger.info(f"开始检测数据缺失（最近{hours}小时）...")

        query = """
            SELECT 
                a.symbol,
                a.analysis_time,
                COUNT(DISTINCT k.timeframe) as available_timeframes,
                ARRAY_AGG(DISTINCT k.timeframe) as found_timeframes
            FROM analysis_results a
            LEFT JOIN klines k ON 
                k.symbol = a.symbol 
                AND k.timeframe IN ('5m', '1h', '4h')
                AND k.time BETWEEN a.analysis_time - INTERVAL '1 hour' AND a.analysis_time
            WHERE a.analysis_time > NOW() - INTERVAL '%s hours'
        """

        params = [hours]

        if symbol:
            query += " AND a.symbol = %s"
            params.append(symbol)

        query += """
            GROUP BY a.symbol, a.analysis_time
            HAVING COUNT(DISTINCT k.timeframe) < 3
            ORDER BY a.analysis_time DESC;
        """

        try:
            records = self.client.execute_query(query, tuple(params))
            if records:
                logger.warning(f"  发现 {len(records)} 条数据缺失记录")
                for record in records:
                    self.warnings.append(
                        f"数据缺失: {record['symbol']} 在 {record['analysis_time']} "
                        f"只有 {record['available_timeframes']} 个周期的数据"
                    )
            else:
                logger.info("  ✅ 无数据缺失")
            return records or []
        except Exception as e:
            logger.error(f"  数据缺失检测失败 - {e}")
            return []

    def calculate_lag_statistics(
        self,
        hours: int = 1,
        symbol: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        计算时间延迟统计

        Args:
            hours: 查询最近N小时的数据
            symbol: 指定币种（可选）

        Returns:
            延迟统计字典，键为时间周期
        """
        logger.info(f"开始计算时间延迟统计（最近{hours}小时）...")
        stats = {}

        for timeframe in self.timeframes:
            query = """
                WITH lag_data AS (
                    SELECT 
                        a.symbol,
                        a.analysis_time,
                        EXTRACT(EPOCH FROM (a.analysis_time - MAX(k.time))) as lag_seconds
                    FROM analysis_results a
                    JOIN klines k ON k.symbol = a.symbol AND k.timeframe = %s
                    WHERE a.analysis_time > NOW() - INTERVAL '%s hours'
                        AND k.time <= a.analysis_time
            """

            params = [timeframe, hours]

            if symbol:
                query += " AND a.symbol = %s"
                params.append(symbol)

            query += """
                    GROUP BY a.symbol, a.analysis_time
                )
                SELECT 
                    COUNT(*) as total_records,
                    AVG(lag_seconds) as avg_lag,
                    MAX(lag_seconds) as max_lag,
                    MIN(lag_seconds) as min_lag,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY lag_seconds) as p95_lag,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY lag_seconds) as median_lag
                FROM lag_data
                WHERE lag_seconds IS NOT NULL;
            """

            try:
                result = self.client.execute_query(query, tuple(params), fetch_one=True)
                if result and result['total_records'] > 0:
                    stats[timeframe] = {
                        'total_records': result['total_records'],
                        'avg_lag': result['avg_lag'],
                        'max_lag': result['max_lag'],
                        'min_lag': result['min_lag'],
                        'p95_lag': result['p95_lag'],
                        'median_lag': result['median_lag']
                    }
                    logger.info(f"  {timeframe}: {result['total_records']} 条记录")

                    # 检查是否超过阈值
                    if result['max_lag'] > 60:
                        self.warnings.append(
                            f"延迟过大: {timeframe} 周期最大延迟达到 {result['max_lag']:.1f} 秒"
                        )
                else:
                    stats[timeframe] = None
                    logger.warning(f"  {timeframe}: 无统计数据")
            except Exception as e:
                logger.error(f"  {timeframe}: 统计计算失败 - {e}")
                stats[timeframe] = None

        return stats

    def check_data_coverage(
        self,
        days: int = 7,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检查K线数据覆盖率

        Args:
            days: 查询最近N天的数据
            symbol: 指定币种（可选）

        Returns:
            覆盖率记录列表
        """
        logger.info(f"开始检查K线数据覆盖率（最近{days}天）...")

        query = """
            SELECT 
                symbol,
                timeframe,
                MIN(time) as first_kline,
                MAX(time) as last_kline,
                COUNT(*) as total_klines,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 
                    CASE timeframe
                        WHEN '5m' THEN 300
                        WHEN '1h' THEN 3600
                        WHEN '4h' THEN 14400
                    END as expected_count,
                ROUND(
                    COUNT(*) * 100.0 / 
                    NULLIF(
                        EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 
                        CASE timeframe
                            WHEN '5m' THEN 300
                            WHEN '1h' THEN 3600
                            WHEN '4h' THEN 14400
                        END,
                        0
                    ),
                    2
                ) as coverage_pct
            FROM klines
            WHERE time > NOW() - INTERVAL '%s days'
        """

        params = [days]

        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)

        query += """
            GROUP BY symbol, timeframe
            ORDER BY coverage_pct ASC NULLS LAST;
        """

        try:
            records = self.client.execute_query(query, tuple(params))
            logger.info(f"  查询到 {len(records) if records else 0} 条覆盖率记录")

            # 检查低覆盖率
            if records:
                for record in records:
                    if record['coverage_pct'] and record['coverage_pct'] < 95.0:
                        self.warnings.append(
                            f"低覆盖率: {record['symbol']} ({record['timeframe']}) "
                            f"覆盖率仅 {record['coverage_pct']:.2f}%"
                        )

            return records or []
        except Exception as e:
            logger.error(f"  覆盖率检查失败 - {e}")
            return []

    def generate_report(
        self,
        hours: int = 1,
        days: int = 7,
        symbol: Optional[str] = None
    ) -> str:
        """
        生成完整的数据一致性验证报告

        Args:
            hours: 延迟统计时间窗口（小时）
            days: 覆盖率检查时间窗口（天）
            symbol: 指定币种（可选）

        Returns:
            格式化的报告字符串
        """
        self.warnings = []  # 重置告警列表
        report_lines = []

        report_lines.append("=" * 60)
        report_lines.append("数据一致性验证报告")
        report_lines.append("=" * 60)
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if symbol:
            report_lines.append(f"币种筛选: {symbol}")
        report_lines.append("")

        # 1. 多周期时间延迟统计
        report_lines.append(f"1. 多周期时间延迟统计（最近{hours}小时）")
        report_lines.append("-" * 60)
        lag_stats = self.calculate_lag_statistics(hours=hours, symbol=symbol)

        if any(lag_stats.values()):
            for timeframe in self.timeframes:
                stat = lag_stats.get(timeframe)
                if stat:
                    report_lines.append(
                        f"   {timeframe:3s}: "
                        f"平均 {stat['avg_lag']:.2f}秒, "
                        f"中位数 {stat['median_lag']:.2f}秒, "
                        f"P95 {stat['p95_lag']:.2f}秒, "
                        f"最大 {stat['max_lag']:.2f}秒 "
                        f"({stat['total_records']} 条记录)"
                    )
                else:
                    report_lines.append(f"   {timeframe:3s}: 无数据")
        else:
            report_lines.append("   ⚠️  无延迟统计数据")

        report_lines.append("")

        # 2. 数据缺失检测
        report_lines.append(f"2. 数据缺失检测（最近{hours}小时）")
        report_lines.append("-" * 60)
        missing_data = self.detect_missing_data(hours=hours, symbol=symbol)

        if missing_data:
            report_lines.append(f"   ⚠️  发现 {len(missing_data)} 条数据缺失记录:")
            for record in missing_data[:10]:  # 只显示前10条
                report_lines.append(
                    f"      - {record['symbol']} @ {record['analysis_time']}: "
                    f"只有 {record['available_timeframes']} 个周期"
                )
            if len(missing_data) > 10:
                report_lines.append(f"      ... 还有 {len(missing_data) - 10} 条记录")
        else:
            report_lines.append("   ✅ 无数据缺失")

        report_lines.append("")

        # 3. K线数据覆盖率
        report_lines.append(f"3. K线数据覆盖率（最近{days}天）")
        report_lines.append("-" * 60)
        coverage_data = self.check_data_coverage(days=days, symbol=symbol)

        if coverage_data:
            # 按币种和周期分组显示
            coverage_by_symbol = defaultdict(dict)
            for record in coverage_data:
                coverage_by_symbol[record['symbol']][record['timeframe']] = record

            for sym in sorted(coverage_by_symbol.keys()):
                report_lines.append(f"   {sym}:")
                for tf in self.timeframes:
                    if tf in coverage_by_symbol[sym]:
                        rec = coverage_by_symbol[sym][tf]
                        coverage = rec['coverage_pct'] if rec['coverage_pct'] else 0
                        status = "✅" if coverage >= 95 else "⚠️"
                        report_lines.append(
                            f"      {tf:3s}: {status} {coverage:6.2f}% "
                            f"({rec['total_klines']:,} / {int(rec['expected_count']) if rec['expected_count'] else 0:,})"
                        )
        else:
            report_lines.append("   ⚠️  无覆盖率数据")

        report_lines.append("")

        # 4. 告警汇总
        if self.warnings:
            report_lines.append("⚠️  告警汇总")
            report_lines.append("-" * 60)
            for warning in self.warnings:
                report_lines.append(f"   - {warning}")
            report_lines.append("")
        else:
            report_lines.append("✅ 无告警")
            report_lines.append("")

        report_lines.append("=" * 60)

        return "\n".join(report_lines)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='数据一致性验证工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证最近1小时的数据
  python validate_data_consistency.py

  # 验证最近24小时的数据
  python validate_data_consistency.py --hours 24

  # 验证指定币种
  python validate_data_consistency.py --symbol "HYPE/USDC:USDC"

  # 验证指定币种最近24小时的数据，检查最近30天的覆盖率
  python validate_data_consistency.py --hours 24 --days 30 --symbol "PURR/USDC:USDC"
        """
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=1,
        help='延迟统计和数据缺失检测的时间窗口（小时），默认1小时'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='覆盖率检查的时间窗口（天），默认7天'
    )
    parser.add_argument(
        '--symbol',
        type=str,
        default=None,
        help='指定要验证的币种（可选），例如: "HYPE/USDC:USDC"'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='输出报告到文件（可选）'
    )

    args = parser.parse_args()

    # 验证参数
    if args.hours < 1:
        print("错误: --hours 必须大于等于 1")
        return 1

    if args.days < 1:
        print("错误: --days 必须大于等于 1")
        return 1

    try:
        # 创建验证器
        validator = DataConsistencyValidator()

        # 测试数据库连接
        if not validator.client.health_check():
            logger.error("数据库连接失败，请检查配置")
            return 1

        logger.info("数据库连接正常")

        # 生成报告
        report = validator.generate_report(
            hours=args.hours,
            days=args.days,
            symbol=args.symbol
        )

        # 输出报告
        print(report)

        # 保存到文件
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存到: {args.output}")

        return 0

    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
