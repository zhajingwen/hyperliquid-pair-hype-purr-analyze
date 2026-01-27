#!/usr/bin/env python3
"""
K线数据校验脚本

校验数据库中各级别K线数据的完整性和正确性。

校验项目：
- 连续性：时间序列是否存在缺口
- 完整性：OHLCV字段是否为空或无效
- 一致性：聚合K线(1h/4h)与源数据(5m)是否匹配
- 数据质量：价格为0、volume为负、high<low等异常
- 覆盖率：各时间级别的数据覆盖情况统计

使用示例：
    # 校验所有活跃币种，最近7天数据
    python scripts/validate_kline_data.py --days 7

    # 指定币种和时间级别
    python scripts/validate_kline_data.py --symbols BTC/USDC:USDC,ETH/USDC:USDC --timeframes 5m,1h

    # 导出JSON报告
    python scripts/validate_kline_data.py --days 7 --output json --output-dir ./reports/

    # 详细模式
    python scripts/validate_kline_data.py --days 7 --verbose

Author: Claude Code
Date: 2026-01-25
"""

import argparse
import json
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.timescaledb import (
    TimescaleDBClient,
    KlineRepository,
    SymbolMetadataRepository
)

from utils.logging_config import logger


# =====================================================
# 常量定义
# =====================================================

# 周期到分钟的映射（复用 KlineDataFiller 的定义）
TIMEFRAME_MINUTES = {
    '1m': 1,
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '4h': 240,
    '1d': 1440,
}

# 默认校验的时间级别
DEFAULT_TIMEFRAMES = ['5m', '1h', '4h']

# 聚合关系：目标周期 -> (源周期, 源K线数量)
AGGREGATION_RULES = {
    '1h': ('5m', 12),   # 1h = 12个5m
    '4h': ('5m', 48),   # 4h = 48个5m
}


# =====================================================
# 数据结构定义
# =====================================================

@dataclass
class ContinuityResult:
    """连续性校验结果"""
    is_continuous: bool
    total_klines: int
    expected_klines: int
    missing_count: int
    gap_details: List[Dict] = field(default_factory=list)  # [{start, end, missing_count}]


@dataclass
class CompletenessResult:
    """完整性校验结果"""
    total_checked: int
    null_open: int
    null_high: int
    null_low: int
    null_close: int
    null_volume: int
    incomplete_records: List[Dict] = field(default_factory=list)


@dataclass
class QualityResult:
    """数据质量校验结果"""
    total_checked: int
    quality_score: float  # 0.0 ~ 1.0
    zero_price_count: int
    negative_volume_count: int
    high_lt_low_count: int
    high_lt_open_close_count: int
    low_gt_open_close_count: int
    issues: List[Dict] = field(default_factory=list)


@dataclass
class AggregationResult:
    """聚合一致性校验结果"""
    target_timeframe: str
    source_timeframe: str
    total_checked: int
    mismatch_count: int
    open_mismatches: int
    high_mismatches: int
    low_mismatches: int
    close_mismatches: int
    volume_mismatches: int
    details: List[Dict] = field(default_factory=list)


@dataclass
class CoverageResult:
    """覆盖率统计结果"""
    timeframe: str
    expected_klines: int
    actual_klines: int
    coverage_rate: float
    first_time: Optional[datetime]
    last_time: Optional[datetime]


@dataclass
class SymbolValidationResult:
    """单个币种的校验结果"""
    symbol: str
    validation_time: datetime
    time_range_start: datetime
    time_range_end: datetime
    coverage: Dict[str, CoverageResult] = field(default_factory=dict)
    continuity: Dict[str, ContinuityResult] = field(default_factory=dict)
    completeness: Dict[str, CompletenessResult] = field(default_factory=dict)
    quality: Dict[str, QualityResult] = field(default_factory=dict)
    aggregation: Dict[str, AggregationResult] = field(default_factory=dict)


@dataclass
class ValidationSummary:
    """校验汇总统计"""
    total_symbols: int
    total_klines_checked: int
    continuity_issues: int
    completeness_issues: int
    quality_issues: int
    aggregation_issues: int


# =====================================================
# K线数据校验器
# =====================================================

class KlineDataValidator:
    """
    K线数据校验器

    提供多维度的K线数据校验功能：
    - 连续性校验：检测时间序列缺口
    - 完整性校验：检查OHLCV字段是否有效
    - 一致性校验：验证聚合K线与源数据的匹配
    - 数据质量校验：检测异常数据
    - 覆盖率统计：计算各时间级别的数据覆盖情况
    """

    # 聚合值比对的容差（处理浮点精度问题）
    AGGREGATION_TOLERANCE = 1e-8

    def __init__(self, kline_repo: Optional[KlineRepository] = None):
        """
        初始化校验器

        Args:
            kline_repo: K线数据仓库（可选，默认创建新实例）
        """
        self.client = TimescaleDBClient()
        self.kline_repo = kline_repo or KlineRepository(self.client)
        self.symbol_repo = SymbolMetadataRepository(self.client)
        logger.info("KlineDataValidator 初始化完成")

    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """将时间周期转换为分钟数"""
        if timeframe in TIMEFRAME_MINUTES:
            return TIMEFRAME_MINUTES[timeframe]

        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 1440

        return 5  # 默认

    def _get_period_start(self, dt: datetime, period_minutes: int) -> datetime:
        """计算周期起始时间（对齐到周期边界）"""
        total_minutes = dt.hour * 60 + dt.minute
        period_start_minutes = (total_minutes // period_minutes) * period_minutes
        return dt.replace(
            hour=period_start_minutes // 60,
            minute=period_start_minutes % 60,
            second=0,
            microsecond=0
        )

    def _query_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """查询K线数据"""
        return self.kline_repo.query_range(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time
        ) or []

    def validate_continuity(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> ContinuityResult:
        """
        校验K线数据时间连续性

        检查K线数据是否存在时间缺口，识别缺失的时间点。

        Args:
            symbol: 币种符号
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            ContinuityResult: 连续性校验结果
        """
        klines = self._query_klines(symbol, timeframe, start_time, end_time)

        interval_minutes = self._timeframe_to_minutes(timeframe)
        expected_interval = timedelta(minutes=interval_minutes)
        tolerance = timedelta(minutes=1)

        # 计算期望的K线数量
        total_minutes = (end_time - start_time).total_seconds() / 60
        expected_klines = int(total_minutes / interval_minutes)

        if len(klines) < 2:
            return ContinuityResult(
                is_continuous=len(klines) > 0,
                total_klines=len(klines),
                expected_klines=expected_klines,
                missing_count=max(0, expected_klines - len(klines)),
                gap_details=[]
            )

        # 按时间排序（升序）
        sorted_klines = sorted(klines, key=lambda x: x['time'])

        gap_details = []
        total_missing = 0

        for i in range(1, len(sorted_klines)):
            current_time = sorted_klines[i]['time']
            prev_time = sorted_klines[i - 1]['time']

            # 确保时间是 datetime 类型
            if isinstance(current_time, str):
                current_time = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
            if isinstance(prev_time, str):
                prev_time = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))

            actual_interval = current_time - prev_time

            # 检查是否有缺失（实际间隔 > 预期间隔 + 容差）
            if actual_interval > expected_interval + tolerance:
                gap_count = int(actual_interval / expected_interval) - 1
                total_missing += gap_count

                gap_details.append({
                    'start': prev_time.isoformat(),
                    'end': current_time.isoformat(),
                    'missing_count': gap_count
                })

        return ContinuityResult(
            is_continuous=len(gap_details) == 0,
            total_klines=len(klines),
            expected_klines=expected_klines,
            missing_count=total_missing,
            gap_details=gap_details
        )

    def validate_completeness(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> CompletenessResult:
        """
        校验K线数据完整性

        检查OHLCV字段是否为空或无效。

        Args:
            symbol: 币种符号
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            CompletenessResult: 完整性校验结果
        """
        klines = self._query_klines(symbol, timeframe, start_time, end_time)

        result = CompletenessResult(
            total_checked=len(klines),
            null_open=0,
            null_high=0,
            null_low=0,
            null_close=0,
            null_volume=0,
            incomplete_records=[]
        )

        for kline in klines:
            issues = []

            if kline.get('open') is None:
                result.null_open += 1
                issues.append('open')

            if kline.get('high') is None:
                result.null_high += 1
                issues.append('high')

            if kline.get('low') is None:
                result.null_low += 1
                issues.append('low')

            if kline.get('close') is None:
                result.null_close += 1
                issues.append('close')

            if kline.get('volume') is None:
                result.null_volume += 1
                issues.append('volume')

            if issues:
                result.incomplete_records.append({
                    'time': kline['time'].isoformat() if hasattr(kline['time'], 'isoformat') else str(kline['time']),
                    'missing_fields': issues
                })

        return result

    def validate_data_quality(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> QualityResult:
        """
        校验数据质量

        检查异常数据：price=0, volume<0, high<low 等。

        Args:
            symbol: 币种符号
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            QualityResult: 数据质量校验结果
        """
        klines = self._query_klines(symbol, timeframe, start_time, end_time)

        result = QualityResult(
            total_checked=len(klines),
            quality_score=1.0,
            zero_price_count=0,
            negative_volume_count=0,
            high_lt_low_count=0,
            high_lt_open_close_count=0,
            low_gt_open_close_count=0,
            issues=[]
        )

        if not klines:
            return result

        total_issues = 0

        for kline in klines:
            kline_issues = []

            open_price = kline.get('open', 0) or 0
            high_price = kline.get('high', 0) or 0
            low_price = kline.get('low', 0) or 0
            close_price = kline.get('close', 0) or 0
            volume = kline.get('volume', 0) or 0

            # 检查价格为0
            if open_price == 0 or high_price == 0 or low_price == 0 or close_price == 0:
                result.zero_price_count += 1
                kline_issues.append('zero_price')

            # 检查成交量为负
            if volume < 0:
                result.negative_volume_count += 1
                kline_issues.append('negative_volume')

            # 检查 high < low
            if high_price < low_price:
                result.high_lt_low_count += 1
                kline_issues.append('high_lt_low')

            # 检查 high < open 或 high < close
            if high_price < open_price or high_price < close_price:
                result.high_lt_open_close_count += 1
                kline_issues.append('high_lt_open_close')

            # 检查 low > open 或 low > close
            if low_price > open_price or low_price > close_price:
                result.low_gt_open_close_count += 1
                kline_issues.append('low_gt_open_close')

            if kline_issues:
                total_issues += 1
                result.issues.append({
                    'time': kline['time'].isoformat() if hasattr(kline['time'], 'isoformat') else str(kline['time']),
                    'issues': kline_issues,
                    'values': {
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume
                    }
                })

        # 计算质量评分
        if result.total_checked > 0:
            result.quality_score = 1.0 - (total_issues / result.total_checked)

        return result

    def validate_aggregation_consistency(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        target_timeframe: str = '1h'
    ) -> AggregationResult:
        """
        校验聚合一致性

        对比聚合K线与源数据是否一致。

        Args:
            symbol: 币种符号
            start_time: 开始时间
            end_time: 结束时间
            target_timeframe: 目标时间周期（1h 或 4h）

        Returns:
            AggregationResult: 聚合一致性校验结果
        """
        if target_timeframe not in AGGREGATION_RULES:
            return AggregationResult(
                target_timeframe=target_timeframe,
                source_timeframe='unknown',
                total_checked=0,
                mismatch_count=0,
                open_mismatches=0,
                high_mismatches=0,
                low_mismatches=0,
                close_mismatches=0,
                volume_mismatches=0,
                details=[]
            )

        source_timeframe, source_count = AGGREGATION_RULES[target_timeframe]
        target_minutes = self._timeframe_to_minutes(target_timeframe)

        # 获取目标周期的K线
        target_klines = self._query_klines(symbol, target_timeframe, start_time, end_time)

        # 获取源周期的K线
        source_klines = self._query_klines(symbol, source_timeframe, start_time, end_time)

        result = AggregationResult(
            target_timeframe=target_timeframe,
            source_timeframe=source_timeframe,
            total_checked=len(target_klines),
            mismatch_count=0,
            open_mismatches=0,
            high_mismatches=0,
            low_mismatches=0,
            close_mismatches=0,
            volume_mismatches=0,
            details=[]
        )

        if not target_klines or not source_klines:
            return result

        # 构建源K线的时间索引
        source_by_time = {}
        for kline in source_klines:
            kline_time = kline['time']
            if isinstance(kline_time, str):
                kline_time = datetime.fromisoformat(kline_time.replace('Z', '+00:00'))
            source_by_time[kline_time] = kline

        # 校验每个目标K线
        for target_kline in target_klines:
            target_time = target_kline['time']
            if isinstance(target_time, str):
                target_time = datetime.fromisoformat(target_time.replace('Z', '+00:00'))

            # 收集该周期内的源K线
            source_interval = timedelta(minutes=self._timeframe_to_minutes(source_timeframe))
            period_sources = []

            for i in range(source_count):
                source_time = target_time + source_interval * i
                if source_time in source_by_time:
                    period_sources.append(source_by_time[source_time])

            if not period_sources:
                continue

            # 按时间排序源K线
            period_sources.sort(key=lambda x: x['time'])

            # 计算期望的聚合值
            expected_open = period_sources[0]['open']
            expected_high = max(k['high'] for k in period_sources if k.get('high'))
            expected_low = min(k['low'] for k in period_sources if k.get('low'))
            expected_close = period_sources[-1]['close']
            expected_volume = sum(k.get('volume', 0) or 0 for k in period_sources)

            # 比对
            mismatches = []

            if abs((target_kline.get('open') or 0) - (expected_open or 0)) > self.AGGREGATION_TOLERANCE:
                result.open_mismatches += 1
                mismatches.append('open')

            if abs((target_kline.get('high') or 0) - (expected_high or 0)) > self.AGGREGATION_TOLERANCE:
                result.high_mismatches += 1
                mismatches.append('high')

            if abs((target_kline.get('low') or 0) - (expected_low or 0)) > self.AGGREGATION_TOLERANCE:
                result.low_mismatches += 1
                mismatches.append('low')

            if abs((target_kline.get('close') or 0) - (expected_close or 0)) > self.AGGREGATION_TOLERANCE:
                result.close_mismatches += 1
                mismatches.append('close')

            # volume 使用相对误差（因为数值可能很大）
            if expected_volume > 0:
                volume_diff = abs((target_kline.get('volume') or 0) - expected_volume) / expected_volume
                if volume_diff > 0.001:  # 0.1% 误差容忍
                    result.volume_mismatches += 1
                    mismatches.append('volume')

            if mismatches:
                result.mismatch_count += 1
                result.details.append({
                    'time': target_time.isoformat(),
                    'mismatches': mismatches,
                    'target_values': {
                        'open': target_kline.get('open'),
                        'high': target_kline.get('high'),
                        'low': target_kline.get('low'),
                        'close': target_kline.get('close'),
                        'volume': target_kline.get('volume')
                    },
                    'expected_values': {
                        'open': expected_open,
                        'high': expected_high,
                        'low': expected_low,
                        'close': expected_close,
                        'volume': expected_volume
                    },
                    'source_kline_count': len(period_sources)
                })

        return result

    def calculate_coverage(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> CoverageResult:
        """
        计算数据覆盖率

        Args:
            symbol: 币种符号
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            CoverageResult: 覆盖率统计结果
        """
        klines = self._query_klines(symbol, timeframe, start_time, end_time)

        interval_minutes = self._timeframe_to_minutes(timeframe)
        total_minutes = (end_time - start_time).total_seconds() / 60
        expected_klines = int(total_minutes / interval_minutes)

        actual_klines = len(klines)
        coverage_rate = actual_klines / expected_klines if expected_klines > 0 else 0

        first_time = None
        last_time = None

        if klines:
            sorted_klines = sorted(klines, key=lambda x: x['time'])
            first_time = sorted_klines[0]['time']
            last_time = sorted_klines[-1]['time']

        return CoverageResult(
            timeframe=timeframe,
            expected_klines=expected_klines,
            actual_klines=actual_klines,
            coverage_rate=coverage_rate,
            first_time=first_time,
            last_time=last_time
        )

    def validate_symbol(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        timeframes: List[str] = None
    ) -> SymbolValidationResult:
        """
        校验单个币种的所有数据

        Args:
            symbol: 币种符号
            start_time: 开始时间
            end_time: 结束时间
            timeframes: 要校验的时间级别列表

        Returns:
            SymbolValidationResult: 完整校验结果
        """
        if timeframes is None:
            timeframes = DEFAULT_TIMEFRAMES

        result = SymbolValidationResult(
            symbol=symbol,
            validation_time=datetime.now(timezone.utc),
            time_range_start=start_time,
            time_range_end=end_time
        )

        for tf in timeframes:
            logger.debug(f"校验 {symbol} @ {tf}")

            # 覆盖率
            result.coverage[tf] = self.calculate_coverage(symbol, tf, start_time, end_time)

            # 连续性
            result.continuity[tf] = self.validate_continuity(symbol, tf, start_time, end_time)

            # 完整性
            result.completeness[tf] = self.validate_completeness(symbol, tf, start_time, end_time)

            # 数据质量
            result.quality[tf] = self.validate_data_quality(symbol, tf, start_time, end_time)

        # 聚合一致性（只校验 1h 和 4h）
        for tf in ['1h', '4h']:
            if tf in timeframes:
                result.aggregation[tf] = self.validate_aggregation_consistency(
                    symbol, start_time, end_time, tf
                )

        return result


# =====================================================
# 报告生成器
# =====================================================

class ValidationReportGenerator:
    """
    校验报告生成器

    支持多种输出格式：控制台、JSON、CSV
    """

    def __init__(self, results: List[SymbolValidationResult], verbose: bool = False):
        """
        初始化报告生成器

        Args:
            results: 校验结果列表
            verbose: 是否输出详细信息
        """
        self.results = results
        self.verbose = verbose

    def _format_datetime(self, dt: Optional[datetime]) -> str:
        """格式化日期时间"""
        if dt is None:
            return "N/A"
        if isinstance(dt, str):
            return dt[:16]
        return dt.strftime("%m-%d %H:%M")

    def _format_percent(self, value: float) -> str:
        """格式化百分比"""
        return f"{value * 100:.1f}%"

    def generate_summary(self) -> ValidationSummary:
        """生成汇总统计"""
        total_klines = 0
        continuity_issues = 0
        completeness_issues = 0
        quality_issues = 0
        aggregation_issues = 0

        for result in self.results:
            for tf, cov in result.coverage.items():
                total_klines += cov.actual_klines

            for tf, cont in result.continuity.items():
                if not cont.is_continuous:
                    continuity_issues += cont.missing_count

            for tf, comp in result.completeness.items():
                completeness_issues += len(comp.incomplete_records)

            for tf, qual in result.quality.items():
                quality_issues += len(qual.issues)

            for tf, agg in result.aggregation.items():
                aggregation_issues += agg.mismatch_count

        return ValidationSummary(
            total_symbols=len(self.results),
            total_klines_checked=total_klines,
            continuity_issues=continuity_issues,
            completeness_issues=completeness_issues,
            quality_issues=quality_issues,
            aggregation_issues=aggregation_issues
        )

    def console_report(self):
        """输出控制台报告"""
        if not self.results:
            print("没有校验结果")
            return

        # 获取第一个结果的时间范围信息
        first_result = self.results[0]
        start_time = first_result.time_range_start
        end_time = first_result.time_range_end
        days = (end_time - start_time).days

        # 收集所有时间级别
        all_timeframes = set()
        for result in self.results:
            all_timeframes.update(result.coverage.keys())
        timeframes = sorted(all_timeframes, key=lambda x: TIMEFRAME_MINUTES.get(x, 0))

        print("=" * 80)
        print("  K线数据校验报告")
        print(f"  生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print("=" * 80)

        print("\n■ 校验范围")
        print(f"  币种: {', '.join(r.symbol for r in self.results)}")
        print(f"  时间级别: {', '.join(timeframes)}")
        print(f"  时间范围: {start_time.strftime('%Y-%m-%d')} ~ {end_time.strftime('%Y-%m-%d')} ({days}天)")

        # 每个币种的详细报告
        for result in self.results:
            print("\n" + "=" * 80)
            print(f"  [{self.results.index(result) + 1}] {result.symbol}")
            print("=" * 80)

            # 覆盖率统计
            print("\n┌─ 覆盖率统计 " + "─" * 55 + "┐")
            print(f"│ {'级别':<6} {'期望K线':<10} {'实际K线':<10} {'覆盖率':<10} {'首条时间':<14} {'最后时间':<14} │")

            for tf in timeframes:
                if tf in result.coverage:
                    cov = result.coverage[tf]
                    first_str = self._format_datetime(cov.first_time)
                    last_str = self._format_datetime(cov.last_time)
                    print(f"│ {tf:<6} {cov.expected_klines:<10} {cov.actual_klines:<10} "
                          f"{self._format_percent(cov.coverage_rate):<10} {first_str:<14} {last_str:<14} │")

            print("└" + "─" * 78 + "┘")

            # 连续性检查
            print("\n┌─ 连续性检查 " + "─" * 55 + "┐")
            for tf in timeframes:
                if tf in result.continuity:
                    cont = result.continuity[tf]
                    if cont.is_continuous:
                        print(f"│ ✅ {tf}: 连续 (无缺口)" + " " * 52 + "│")
                    else:
                        gap_count = len(cont.gap_details)
                        print(f"│ ❌ {tf}: 发现 {gap_count} 处缺口，共缺失 {cont.missing_count} 条K线" +
                              " " * max(0, 35 - len(str(gap_count)) - len(str(cont.missing_count))) + "│")
                        if self.verbose and cont.gap_details:
                            for gap in cont.gap_details[:5]:  # 最多显示5个
                                print(f"│    缺口: {gap['start'][:16]} ~ {gap['end'][:16]} "
                                      f"({gap['missing_count']}条)" + " " * 10 + "│")
            print("└" + "─" * 78 + "┘")

            # 数据质量
            print("\n┌─ 数据质量 " + "─" * 57 + "┐")
            for tf in timeframes:
                if tf in result.quality:
                    qual = result.quality[tf]
                    score_str = f"质量评分: {self._format_percent(qual.quality_score)}"
                    print(f"│ {tf}: {score_str}" + " " * (70 - len(tf) - len(score_str)) + "│")

                    issues_found = []
                    if qual.zero_price_count > 0:
                        issues_found.append(f"price=0: {qual.zero_price_count}条")
                    if qual.negative_volume_count > 0:
                        issues_found.append(f"volume<0: {qual.negative_volume_count}条")
                    if qual.high_lt_low_count > 0:
                        issues_found.append(f"high<low: {qual.high_lt_low_count}条")

                    if issues_found:
                        issue_str = "⚠️ " + ", ".join(issues_found)
                        print(f"│    {issue_str}" + " " * max(0, 72 - len(issue_str)) + "│")
            print("└" + "─" * 78 + "┘")

            # 聚合一致性
            if result.aggregation:
                print("\n┌─ 聚合一致性 " + "─" * 55 + "┐")
                for tf, agg in result.aggregation.items():
                    if agg.total_checked > 0:
                        if agg.mismatch_count == 0:
                            print(f"│ ✅ {tf}: 与{agg.source_timeframe}源数据一致 "
                                  f"(校验{agg.total_checked}条)" + " " * 30 + "│")
                        else:
                            print(f"│ ⚠️ {tf}: 发现 {agg.mismatch_count} 处不一致" +
                                  " " * max(0, 48 - len(str(agg.mismatch_count))) + "│")
                            if self.verbose:
                                detail_parts = []
                                if agg.open_mismatches:
                                    detail_parts.append(f"open:{agg.open_mismatches}")
                                if agg.high_mismatches:
                                    detail_parts.append(f"high:{agg.high_mismatches}")
                                if agg.low_mismatches:
                                    detail_parts.append(f"low:{agg.low_mismatches}")
                                if agg.close_mismatches:
                                    detail_parts.append(f"close:{agg.close_mismatches}")
                                if agg.volume_mismatches:
                                    detail_parts.append(f"volume:{agg.volume_mismatches}")
                                detail_str = "    " + ", ".join(detail_parts)
                                print(f"│{detail_str}" + " " * max(0, 77 - len(detail_str)) + "│")
                    else:
                        print(f"│ ℹ️ {tf}: 无数据可校验" + " " * 54 + "│")
                print("└" + "─" * 78 + "┘")

        # 汇总统计
        summary = self.generate_summary()
        print("\n" + "=" * 80)
        print("  汇总统计")
        print("=" * 80)
        print(f"  校验币种数: {summary.total_symbols}")
        print(f"  校验K线总数: {summary.total_klines_checked}")
        print(f"  连续性问题: {summary.continuity_issues} 处")
        print(f"  完整性问题: {summary.completeness_issues} 条")
        print(f"  质量问题: {summary.quality_issues} 条")
        print(f"  一致性问题: {summary.aggregation_issues} 处")
        print("=" * 80)

    def export_json(self, output_path: str):
        """
        导出JSON报告

        Args:
            output_path: 输出文件路径
        """
        def serialize(obj):
            """自定义序列化"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, '__dataclass_fields__'):
                return asdict(obj)
            return str(obj)

        report_data = {
            'report_time': datetime.now(timezone.utc).isoformat(),
            'summary': asdict(self.generate_summary()),
            'results': []
        }

        for result in self.results:
            result_dict = {
                'symbol': result.symbol,
                'validation_time': result.validation_time.isoformat(),
                'time_range': {
                    'start': result.time_range_start.isoformat(),
                    'end': result.time_range_end.isoformat()
                },
                'coverage': {},
                'continuity': {},
                'completeness': {},
                'quality': {},
                'aggregation': {}
            }

            for tf, cov in result.coverage.items():
                result_dict['coverage'][tf] = {
                    'expected_klines': cov.expected_klines,
                    'actual_klines': cov.actual_klines,
                    'coverage_rate': cov.coverage_rate,
                    'first_time': cov.first_time.isoformat() if cov.first_time else None,
                    'last_time': cov.last_time.isoformat() if cov.last_time else None
                }

            for tf, cont in result.continuity.items():
                result_dict['continuity'][tf] = asdict(cont)

            for tf, comp in result.completeness.items():
                result_dict['completeness'][tf] = asdict(comp)

            for tf, qual in result.quality.items():
                result_dict['quality'][tf] = asdict(qual)

            for tf, agg in result.aggregation.items():
                result_dict['aggregation'][tf] = asdict(agg)

            report_data['results'].append(result_dict)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=serialize)

        print(f"JSON报告已导出: {output_path}")

    def export_csv(self, output_dir: str):
        """
        导出CSV报告

        Args:
            output_dir: 输出目录
        """
        import csv

        os.makedirs(output_dir, exist_ok=True)

        # 导出覆盖率统计
        coverage_path = os.path.join(output_dir, 'coverage.csv')
        with open(coverage_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'timeframe', 'expected_klines', 'actual_klines',
                           'coverage_rate', 'first_time', 'last_time'])
            for result in self.results:
                for tf, cov in result.coverage.items():
                    writer.writerow([
                        result.symbol, tf, cov.expected_klines, cov.actual_klines,
                        f"{cov.coverage_rate:.4f}",
                        cov.first_time.isoformat() if cov.first_time else '',
                        cov.last_time.isoformat() if cov.last_time else ''
                    ])

        # 导出质量问题
        quality_path = os.path.join(output_dir, 'quality_issues.csv')
        with open(quality_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'timeframe', 'time', 'issues', 'open', 'high', 'low', 'close', 'volume'])
            for result in self.results:
                for tf, qual in result.quality.items():
                    for issue in qual.issues:
                        writer.writerow([
                            result.symbol, tf, issue['time'],
                            ','.join(issue['issues']),
                            issue['values']['open'],
                            issue['values']['high'],
                            issue['values']['low'],
                            issue['values']['close'],
                            issue['values']['volume']
                        ])

        # 导出连续性问题
        continuity_path = os.path.join(output_dir, 'continuity_gaps.csv')
        with open(continuity_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'timeframe', 'gap_start', 'gap_end', 'missing_count'])
            for result in self.results:
                for tf, cont in result.continuity.items():
                    for gap in cont.gap_details:
                        writer.writerow([
                            result.symbol, tf, gap['start'], gap['end'], gap['missing_count']
                        ])

        print(f"CSV报告已导出到目录: {output_dir}")


# =====================================================
# 命令行入口
# =====================================================

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='K线数据校验脚本 - 校验数据库中K线数据的完整性和正确性',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 校验所有活跃币种，最近7天数据
  python scripts/validate_kline_data.py --days 7

  # 指定币种和时间级别
  python scripts/validate_kline_data.py --symbols BTC/USDC:USDC,ETH/USDC:USDC --timeframes 5m,1h

  # 导出JSON报告
  python scripts/validate_kline_data.py --days 7 --output json --output-dir ./reports/

  # 详细模式
  python scripts/validate_kline_data.py --days 7 --verbose
        """
    )

    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='校验最近N天的数据 (默认: 7)'
    )

    parser.add_argument(
        '--symbols',
        type=str,
        help='指定校验的币种，逗号分隔 (默认: 所有活跃币种)'
    )

    parser.add_argument(
        '--timeframes',
        type=str,
        default='5m,1h,4h',
        help='指定校验的时间级别，逗号分隔 (默认: 5m,1h,4h)'
    )

    parser.add_argument(
        '--output',
        type=str,
        choices=['console', 'json', 'csv', 'all'],
        default='console',
        help='输出格式 (默认: console)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='./reports/',
        help='报告输出目录 (默认: ./reports/)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细模式，显示更多信息'
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 初始化校验器
    validator = KlineDataValidator()

    # 确定时间范围
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=args.days)

    # 确定要校验的币种
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    else:
        # 获取所有活跃币种
        symbols = validator.symbol_repo.get_active_symbols()
        if not symbols:
            print("未找到活跃币种，请检查数据库或使用 --symbols 指定币种")
            return 1

    # 确定要校验的时间级别
    timeframes = [tf.strip() for tf in args.timeframes.split(',')]

    print(f"开始校验...")
    print(f"  币种数: {len(symbols)}")
    print(f"  时间级别: {', '.join(timeframes)}")
    print(f"  时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}")
    print()

    # 执行校验
    results = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] 校验 {symbol}...")
        try:
            result = validator.validate_symbol(symbol, start_time, end_time, timeframes)
            results.append(result)
        except Exception as e:
            logger.error(f"校验 {symbol} 失败: {e}")

    if not results:
        print("没有校验结果")
        return 1

    # 生成报告
    reporter = ValidationReportGenerator(results, verbose=args.verbose)

    if args.output in ['console', 'all']:
        reporter.console_report()

    if args.output in ['json', 'all']:
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_path = os.path.join(args.output_dir, f'kline_validation_{timestamp}.json')
        reporter.export_json(json_path)

    if args.output in ['csv', 'all']:
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_dir = os.path.join(args.output_dir, f'kline_validation_{timestamp}')
        reporter.export_csv(csv_dir)

    # 返回状态码
    summary = reporter.generate_summary()
    total_issues = (summary.continuity_issues + summary.completeness_issues +
                    summary.quality_issues + summary.aggregation_issues)

    if total_issues > 0:
        print(f"\n⚠️ 发现 {total_issues} 个问题，请检查报告详情")
        return 1
    else:
        print("\n✅ 所有校验通过")
        return 0


if __name__ == '__main__':
    sys.exit(main())
