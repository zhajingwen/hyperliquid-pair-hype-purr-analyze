"""
实时K线分析服务 (Realtime Kline Analysis Service)

核心功能：
- WebSocket 实时数据接收（600订阅: 200币种 × 3周期）
- 异步批量写入数据库（1000-2000条或5秒触发）
- 每根K线闭合后立即分析
- Z-score 异常检测 + 飞书告警
- 新币种自动监控

性能目标：
- 分析延迟: <5秒
- 告警延迟: <10秒
- 内存占用: <512MB
- CPU占用: <50%

Author: Claude Code
Date: 2026-01-19
"""

import os
import time
import queue
import logging
import threading
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from hyperliquid.info import Info
import hyperliquid.utils.constants as constants

from utils.enhanced_ws_manager import EnhancedWebSocketManager, ConnectionState
from utils.timescaledb import (
    TimescaleDBClient,
    KlineRepository,
    SymbolMetadataRepository,
    AnalysisResultRepository
)
from utils.analysis_core import analyze_pair
from utils.lark_bot import sender_colourful
from utils.config import lark_bot_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================================================
# 实时K线分析服务
# =====================================================

class RealtimeKlineService:
    """
    实时K线分析服务（主分析引擎）

    架构：
    ┌─────────────────────────────────────────────────┐
    │ Hyperliquid WebSocket API                       │
    └──────────────────┬──────────────────────────────┘
                       ↓
    ┌─────────────────────────────────────────────────┐
    │ EnhancedWebSocketManager                        │
    │ (假活检测 + 自动重连)                            │
    └──────────────────┬──────────────────────────────┘
                       ↓
              on_message() 回调
                       ↓
         ┌─────────────┴─────────────┐
         ↓                           ↓
    kline_buffer              _analyze_and_alert()
    (Queue队列)               (实时分析引擎)
         ↓                           ↓
    _batch_writer()           飞书告警
    (批量写入线程)
         ↓
    TimescaleDB
    """

    def __init__(
        self,
        base_symbol: str = 'BTC/USDC:USDC',
        timeframes: List[str] = None,
        batch_size: int = 1000,
        batch_timeout: float = 5.0
    ):
        """
        初始化实时K线分析服务

        Args:
            base_symbol: 基准币种（用于配对分析）
            timeframes: 订阅周期列表（默认 ['5m', '1h', '4h']）
            batch_size: 批量写入大小（默认1000条）
            batch_timeout: 批量写入超时（默认5秒）
        """
        # 基础配置
        self.base_symbol = base_symbol
        self.timeframes = timeframes or ['5m', '1h', '4h']
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        # 数据库客户端
        self.db_client = TimescaleDBClient()
        self.kline_repo = KlineRepository(self.db_client)
        self.symbol_repo = SymbolMetadataRepository(self.db_client)
        self.analysis_repo = AnalysisResultRepository(self.db_client)

        # 飞书告警配置
        # 从config导入webhook URL（已经在config中构建好）
        from utils.config import lark_webhook_url
        self.lark_webhook_url = lark_webhook_url

        if not self.lark_webhook_url:
            logger.warning("未配置飞书告警，LARK_WEBHOOK_URL 或 LARKBOT_ID 环境变量未设置")

        # 获取活跃币种列表
        self.symbols = self._get_active_symbols()
        logger.info(f"活跃币种数量: {len(self.symbols)}")

        # 修复竞态条件: 添加线程锁保护symbols列表
        self.symbols_lock = threading.RLock()

        # 构建订阅列表（600个订阅 = 200币种 × 3周期）
        self.subscriptions = self._build_subscriptions()
        logger.info(f"订阅数量: {len(self.subscriptions)}")

        # K线缓冲队列（线程安全，最大10000条）
        self.kline_buffer = queue.Queue(maxsize=10000)

        # 分析任务队列（支持25秒缓冲: 200消息/秒 × 25秒）
        self.analysis_queue = queue.Queue(maxsize=5000)

        # 分析结果缓冲队列（支持峰值: 200条/秒 × 25秒）
        self.analysis_result_buffer = queue.Queue(maxsize=5000)

        # 停止事件
        self.stop_event = threading.Event()

        # 分析工作线程（可配置化，默认5个）
        # Phase 1.5 优化: 从环境变量读取线程数，提供200%+容量余量
        num_workers = int(os.getenv('ANALYSIS_WORKERS', '5'))
        self.analysis_workers = []
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._analysis_worker,
                daemon=True,
                name=f"analysis-worker-{i}"
            )
            worker.start()
            self.analysis_workers.append(worker)

        logger.info(f"✅ 启动{num_workers}个分析工作线程（ANALYSIS_WORKERS={num_workers}）")

        # 批量写入线程
        self.batch_writer_thread = threading.Thread(
            target=self._batch_writer,
            daemon=True,
            name="batch-writer"
        )

        # 新币种监控线程
        self.symbol_monitor_thread = threading.Thread(
            target=self._monitor_new_symbols,
            daemon=True,
            name="symbol-monitor"
        )

        # 分析结果批量写入线程
        self.analysis_result_writer_thread = threading.Thread(
            target=self._analysis_result_batch_writer,
            daemon=True,
            name="analysis-result-writer"
        )

        # WebSocket 管理器
        self.ws_manager = EnhancedWebSocketManager(
            subscriptions=self.subscriptions,
            message_callback=self.on_message,
            on_state_change=self.on_state_change,
            timeout=30  # 30秒无数据触发重连
        )

        # 统计信息
        self.stats = {
            'messages_received': 0,
            'klines_written': 0,
            'analyses_performed': 0,
            'analyses_completed': 0,  # 新增：分析成功次数
            'analyses_failed': 0,     # 新增：分析失败次数
            'analysis_queue_drops': 0, # 新增：分析队列丢弃次数
            'alerts_sent': 0,
            'analysis_results_written': 0,      # 新增：分析结果成功写入数
            'analysis_results_deduped': 0,      # 新增：分析结果去重数
            'analysis_result_buffer_drops': 0,  # 新增：分析结果缓冲队列丢弃数
            'start_time': time.time()
        }

        logger.info("✅ 实时K线分析服务初始化完成")

    def _get_active_symbols(self) -> List[str]:
        """
        获取活跃币种列表

        Returns:
            活跃币种列表（格式: BTC/USDC:USDC）
        """
        try:
            # 从数据库获取活跃币种
            active_symbols = self.symbol_repo.get_active_symbols()

            if active_symbols:
                logger.info(f"从数据库加载 {len(active_symbols)} 个活跃币种")
                return active_symbols

            # 如果数据库为空，从交易所获取
            logger.info("数据库无币种数据，从交易所获取...")
            info = Info(constants.MAINNET_API_URL, skip_ws=True)
            meta = info.meta()

            symbols = []
            for asset_info in meta.get('universe', []):
                name = asset_info.get('name')
                if name:
                    # Hyperliquid 格式转换: BTC → BTC/USDC:USDC
                    symbol = f"{name}/USDC:USDC"
                    symbols.append(symbol)

                    # 注册币种到数据库
                    self.symbol_repo.upsert_symbol(
                        symbol=symbol,
                        base_asset=name,
                        quote_asset='USDC',
                        is_active=True
                    )

            logger.info(f"从交易所获取 {len(symbols)} 个币种")
            return symbols

        except Exception as e:
            logger.error(f"获取币种列表失败: {e}", exc_info=True)
            # 返回默认币种
            return ['BTC/USDC:USDC', 'ETH/USDC:USDC']

    def _build_subscriptions(self) -> List[Dict]:
        """
        构建 WebSocket 订阅列表

        Returns:
            订阅列表 [{\"type\": \"candle\", \"coin\": \"BTC\", \"interval\": \"5m\"}, ...]
        """
        subscriptions = []

        # 修复竞态条件: 使用锁保护symbols访问
        with self.symbols_lock:
            symbols_copy = list(self.symbols)

        for symbol in symbols_copy:
            # 提取基础币种: BTC/USDC:USDC → BTC
            coin = symbol.split('/')[0]

            for timeframe in self.timeframes:
                subscriptions.append({
                    "type": "candle",
                    "coin": coin,
                    "interval": timeframe
                })

        return subscriptions

    def _parse_kline(self, msg: Dict) -> Optional[Dict]:
        """
        解析 Hyperliquid K线数据为标准格式

        Args:
            msg: WebSocket 消息
                {
                    "channel": "candle",
                    "data": {
                        "t": 1704067260000,  // 开盘时间（毫秒时间戳）
                        "s": "ETH",          // 币种符号
                        "i": "5m",           // 时间周期
                        "o": "2295.5",       // 开盘价
                        "h": "2296.8",       // 最高价
                        "l": "2295.2",       // 最低价
                        "c": "2296.3",       // 收盘价
                        "v": "1234.56"       // 成交量
                    }
                }

        Returns:
            标准K线数据 或 None（解析失败）
        """
        try:
            if msg.get("channel") != "candle":
                return None

            data = msg.get("data", {})

            # 提取字段
            coin = data.get('s')  # ETH
            timeframe = data.get('i')  # 5m
            timestamp_ms = data.get('t')  # 1704067260000
            open_price = float(data.get('o', 0))
            high_price = float(data.get('h', 0))
            low_price = float(data.get('l', 0))
            close_price = float(data.get('c', 0))
            volume = float(data.get('v', 0))

            # 构建币种符号: ETH → ETH/USDC:USDC
            symbol = f"{coin}/USDC:USDC"

            # 转换时间戳
            kline_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            # 计算收益率
            return_pct = (close_price - open_price) / open_price if open_price > 0 else 0.0

            # 计算成交额（USD）
            volume_usd = close_price * volume

            return {
                'time': kline_time,
                'symbol': symbol,
                'timeframe': timeframe,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
                'volume_usd': volume_usd,
                'return_pct': return_pct
            }

        except Exception as e:
            logger.error(f"K线解析失败: {e} | 原始数据: {msg}", exc_info=True)
            return None

    def on_message(self, msg: Dict):
        """
        WebSocket 消息回调（核心处理逻辑）

        流程:
        1. 解析K线数据
        2. 放入缓冲队列（异步批量写入）
        3. 【已禁用】触发实时分析（阻塞问题）

        Args:
            msg: WebSocket 消息
        """
        try:
            # 统计
            self.stats['messages_received'] += 1

            # 解析K线
            kline = self._parse_kline(msg)
            if not kline:
                return

            # 放入缓冲队列（异步批量写入）
            try:
                self.kline_buffer.put_nowait(kline)
            except queue.Full:
                logger.warning(f"缓冲队列已满，丢弃K线: {kline['symbol']} @ {kline['timeframe']}")

            # 【异步分析】放入分析队列（非阻塞，<0.1ms）
            analysis_task = {
                'symbol': kline['symbol'],
                'timeframe': kline['timeframe'],
                'timestamp': kline['time']
            }
            try:
                self.analysis_queue.put_nowait(analysis_task)
            except queue.Full:
                logger.warning(f"分析队列已满，跳过分析: {kline['symbol']} @ {kline['timeframe']}")
                self.stats.setdefault('analysis_queue_drops', 0)
                self.stats['analysis_queue_drops'] += 1

        except Exception as e:
            logger.error(f"消息处理失败: {e}", exc_info=True)

    def _batch_writer(self):
        """
        批量写入线程

        策略:
        - 达到 batch_size（1000条） 或 超时 batch_timeout（5秒） 触发写入
        - 使用 COPY 命令高性能批量插入

        修复: 正确跟踪从队列获取的元素数量，避免task_done计数不匹配
        """
        logger.info("批量写入线程已启动")

        batch = []
        items_to_mark_done = 0  # 跟踪需要标记完成的项数
        last_write_time = time.time()

        while not self.stop_event.is_set():
            try:
                # 获取K线数据（超时1秒）
                kline_fetched = False
                try:
                    kline = self.kline_buffer.get(timeout=1.0)
                    batch.append(kline)
                    items_to_mark_done += 1  # 每次成功获取，计数+1
                    kline_fetched = True
                except queue.Empty:
                    pass

                # 判断是否触发写入（修复：停机时强制写入）
                should_write = (
                    len(batch) >= self.batch_size or  # 达到批量大小
                    (batch and time.time() - last_write_time >= self.batch_timeout) or  # 超时
                    (batch and self.stop_event.is_set())  # 停机时立即写入剩余批次
                )

                if should_write and batch:
                    # 去重：按主键 (time, symbol, timeframe) 去重，保留最新记录
                    dedup_dict = {}
                    batch_count = len(batch)
                    for kline in batch:
                        key = (kline['time'], kline['symbol'], kline['timeframe'])
                        dedup_dict[key] = kline  # 后来的覆盖之前的，保留最新

                    dedup_batch = list(dedup_dict.values())

                    # 批量写入数据库
                    try:
                        count = self.kline_repo.batch_upsert_copy(dedup_batch, on_conflict='update')
                        self.stats['klines_written'] += count

                        logger.info(
                            f"批量写入: {count} 条K线 (去重前: {batch_count}) | "
                            f"缓冲队列: {self.kline_buffer.qsize()} | "
                            f"总写入: {self.stats['klines_written']}"
                        )

                        # 标记实际从队列获取的任务完成
                        for _ in range(items_to_mark_done):
                            self.kline_buffer.task_done()

                        # 重置批次和计数器
                        batch = []
                        items_to_mark_done = 0
                        last_write_time = time.time()

                    except Exception as e:
                        logger.error(f"批量写入失败: {e}", exc_info=True)
                        # 标记实际从队列获取的任务完成（即使失败）
                        for _ in range(items_to_mark_done):
                            self.kline_buffer.task_done()
                        # 清空批次和计数器，避免重复错误
                        batch = []
                        items_to_mark_done = 0
                        last_write_time = time.time()
                elif kline_fetched and not should_write:
                    # 已获取数据但不需要写入，等待批量写入时统一标记
                    pass

            except Exception as e:
                logger.error(f"批量写入线程异常: {e}", exc_info=True)

        # 停止前处理剩余批次
        if batch:
            try:
                dedup_dict = {}
                batch_count = len(batch)
                for kline in batch:
                    key = (kline['time'], kline['symbol'], kline['timeframe'])
                    dedup_dict[key] = kline

                dedup_batch = list(dedup_dict.values())
                count = self.kline_repo.batch_upsert_copy(dedup_batch, on_conflict='update')
                self.stats['klines_written'] += count

                logger.info(f"停止前最后批量写入: {count} 条K线")

                # 标记实际从队列获取的任务完成
                for _ in range(items_to_mark_done):
                    self.kline_buffer.task_done()
            except Exception as e:
                logger.error(f"停止前批量写入失败: {e}", exc_info=True)
                # 标记实际从队列获取的任务完成（即使失败）
                for _ in range(items_to_mark_done):
                    self.kline_buffer.task_done()

        logger.info("批量写入线程已停止")

    def _analysis_result_batch_writer(self):
        """
        分析结果批量写入线程

        策略:
        - 达到 batch_size（100条） 或 超时 batch_timeout（2秒） 触发写入
        - 去重策略：分钟级时间 + symbol + base_symbol
        - 环境变量可配置批量大小和超时时间
        """
        logger.info("分析结果批量写入线程已启动")

        # 从环境变量读取配置（可配置化）
        batch_size = int(os.getenv('ANALYSIS_RESULT_BATCH_SIZE', '100'))
        batch_timeout = float(os.getenv('ANALYSIS_RESULT_BATCH_TIMEOUT', '2.0'))
        use_copy_method = os.getenv('ANALYSIS_USE_COPY_METHOD', 'false').lower() in ('true', '1', 'yes')

        batch = []
        items_to_mark_done = 0  # 跟踪需要标记完成的项数
        last_write_time = time.time()

        while not self.stop_event.is_set():
            try:
                # 获取分析结果（超时1秒）
                result_fetched = False
                try:
                    analysis_record = self.analysis_result_buffer.get(timeout=1.0)
                    batch.append(analysis_record)
                    items_to_mark_done += 1  # 每次成功获取，计数+1
                    result_fetched = True
                except queue.Empty:
                    pass

                # 判断是否触发写入（修复：停机时强制写入）
                should_write = (
                    len(batch) >= batch_size or  # 达到批量大小
                    (batch and time.time() - last_write_time >= batch_timeout) or  # 超时
                    (batch and self.stop_event.is_set())  # 停机时立即写入剩余批次
                )

                if should_write and batch:
                    # 去重：按 (分钟级时间, symbol, base_symbol) 去重
                    dedup_dict = {}
                    batch_count = len(batch)
                    for record in batch:
                        # 将时间精确到分钟
                        minute_time = record['analysis_time'].replace(
                            second=0, microsecond=0
                        )
                        key = (minute_time, record['symbol'], record['base_symbol'])
                        dedup_dict[key] = record  # 后来的覆盖之前的，保留最新

                    dedup_batch = list(dedup_dict.values())
                    dedup_count = batch_count - len(dedup_batch)

                    # 批量写入数据库（根据配置选择写入方法）
                    try:
                        if use_copy_method:
                            count = self.analysis_repo.batch_insert_copy(dedup_batch)
                        else:
                            count = self.analysis_repo.batch_insert(dedup_batch)
                        self.stats['analysis_results_written'] += count
                        self.stats['analysis_results_deduped'] += dedup_count

                        logger.info(
                            f"批量写入分析结果: {count} 条 (去重前: {batch_count}, 去重: {dedup_count}) | "
                            f"缓冲队列: {self.analysis_result_buffer.qsize()}"
                        )

                        # 标记实际从队列获取的任务完成
                        for _ in range(items_to_mark_done):
                            self.analysis_result_buffer.task_done()

                        # 重置批次和计数器
                        batch = []
                        items_to_mark_done = 0
                        last_write_time = time.time()

                    except Exception as e:
                        logger.error(f"分析结果批量写入失败: {e}", exc_info=True)
                        # 标记实际从队列获取的任务完成（即使失败）
                        for _ in range(items_to_mark_done):
                            self.analysis_result_buffer.task_done()
                        # 清空批次和计数器，避免重复错误
                        batch = []
                        items_to_mark_done = 0
                        last_write_time = time.time()
                elif result_fetched and not should_write:
                    # 已获取数据但不需要写入，等待批量写入时统一标记
                    pass

            except Exception as e:
                logger.error(f"分析结果批量写入线程异常: {e}", exc_info=True)

        # 停止前处理剩余批次
        if batch:
            try:
                # 去重
                dedup_dict = {}
                batch_count = len(batch)
                for record in batch:
                    minute_time = record['analysis_time'].replace(
                        second=0, microsecond=0
                    )
                    key = (minute_time, record['symbol'], record['base_symbol'])
                    dedup_dict[key] = record

                dedup_batch = list(dedup_dict.values())
                dedup_count = batch_count - len(dedup_batch)

                # 根据配置选择写入方法
                if use_copy_method:
                    count = self.analysis_repo.batch_insert_copy(dedup_batch)
                else:
                    count = self.analysis_repo.batch_insert(dedup_batch)
                self.stats['analysis_results_written'] += count
                self.stats['analysis_results_deduped'] += dedup_count

                logger.info(f"停止前最后批量写入分析结果: {count} 条 (去重前: {batch_count}, 去重: {dedup_count})")

                # 标记实际从队列获取的任务完成
                for _ in range(items_to_mark_done):
                    self.analysis_result_buffer.task_done()
            except Exception as e:
                logger.error(f"停止前分析结果批量写入失败: {e}", exc_info=True)
                # 标记实际从队列获取的任务完成（即使失败）
                for _ in range(items_to_mark_done):
                    self.analysis_result_buffer.task_done()

        logger.info("分析结果批量写入线程已停止")

    def _analysis_worker(self):
        """
        分析工作线程主循环（Phase 1.5 优化版）

        功能:
        1. 从队列取出分析任务
        2. 执行数据库查询 + 统计分析
        3. 检测异常并发送飞书告警
        4. 持久化分析结果到数据库

        去重策略（Phase 1.5 差异化优化）:
        - 5m周期: 60秒冷却（每5分钟更新一次K线）
        - 1h周期: 300秒冷却（每60分钟更新一次K线，减少80%不必要分析）
        - 4h周期: 900秒冷却（每240分钟更新一次K线，减少93%不必要分析）
        - 预期节省: 70-80%总体CPU资源
        """
        logger.info(f"[{threading.current_thread().name}] 分析工作线程已启动")

        # 任务去重字典（避免重复分析相同币种+周期）
        recent_tasks = {}  # {(symbol, timeframe): timestamp}

        # 按周期差异化去重窗口（单位：秒）
        # 5m周期: 每5分钟更新一次，60秒冷却避免重复分析同一根K线
        # 1h周期: 每60分钟更新一次，5分钟冷却减少不必要分析
        # 4h周期: 每240分钟更新一次，15分钟冷却大幅减少重复分析
        DEDUP_WINDOWS = {
            '5m': 60,    # 5分钟周期：60秒冷却
            '1h': 300,   # 1小时周期：5分钟冷却（减少80%分析）
            '4h': 900,   # 4小时周期：15分钟冷却（减少93%分析）
        }

        # 内存泄漏修复: 定时清理配置
        CLEANUP_INTERVAL = 300  # 5分钟定时清理
        MAX_RECENT_TASKS = 5000  # 硬性上限
        last_cleanup_time = time.time()

        while not self.stop_event.is_set():
            try:
                # 阻塞获取任务（1秒超时，允许检查stop_event）
                try:
                    task = self.analysis_queue.get(timeout=1.0)
                except queue.Empty:
                    # 修复CPU占用: 队列为空时使用wait等待，避免CPU空转
                    if self.stop_event.wait(0.1):  # 100ms检查一次
                        break
                    continue

                symbol = task['symbol']
                timeframe = task['timeframe']
                task_key = (symbol, timeframe)

                # 根据周期获取去重窗口
                dedup_window = DEDUP_WINDOWS.get(timeframe, 60)

                # 去重检查：根据周期设定的时间内已分析过则跳过
                current_time = time.time()
                last_analysis_time = recent_tasks.get(task_key, 0)
                time_since_last = current_time - last_analysis_time if last_analysis_time > 0 else 0

                if last_analysis_time > 0 and time_since_last < dedup_window:
                    logger.debug(
                        f"跳过重复分析: {symbol} @ {timeframe} "
                        f"(距上次 {time_since_last:.0f}秒，窗口 {dedup_window}秒)"
                    )
                    self.analysis_queue.task_done()
                    continue

                # 执行分析（原 _analyze_and_alert 逻辑）
                try:
                    self._analyze_and_alert(symbol, timeframe)
                    self.stats['analyses_completed'] += 1

                    # 记录分析时间戳（分析成功后才更新）
                    recent_tasks[task_key] = current_time

                    # Phase 1.5: 记录分析完成信息，用于监控
                    logger.debug(
                        f"分析完成: {symbol} @ {timeframe} | "
                        f"去重窗口: {dedup_window}秒 | "
                        f"距上次: {time_since_last:.0f}秒"
                    )
                except Exception as e:
                    logger.error(f"分析失败: {symbol} @ {timeframe} | {e}", exc_info=True)
                    self.stats['analyses_failed'] += 1

                # 标记任务完成
                self.analysis_queue.task_done()

                # 内存泄漏修复: 定时清理过期记录（优先级高于长度检查）
                if current_time - last_cleanup_time > CLEANUP_INTERVAL:
                    max_window = max(DEDUP_WINDOWS.values())
                    cutoff_time = current_time - max_window * 2  # 保留2倍窗口时间的记录
                    old_count = len(recent_tasks)
                    recent_tasks = {k: v for k, v in recent_tasks.items() if v > cutoff_time}
                    last_cleanup_time = current_time
                    logger.debug(
                        f"定时清理任务缓存: {old_count} → {len(recent_tasks)} "
                        f"(清理了 {old_count - len(recent_tasks)} 条过期记录)"
                    )

                # 内存泄漏修复: 硬性上限检查，防止无限增长
                if len(recent_tasks) > MAX_RECENT_TASKS:
                    # 移除最旧的50%记录
                    sorted_tasks = sorted(recent_tasks.items(), key=lambda x: x[1])
                    keep_count = MAX_RECENT_TASKS // 2
                    recent_tasks = dict(sorted_tasks[-keep_count:])
                    logger.warning(
                        f"任务缓存超限 ({MAX_RECENT_TASKS})，强制清理至 {len(recent_tasks)}"
                    )

            except Exception as e:
                logger.error(f"[{threading.current_thread().name}] 工作线程异常: {e}", exc_info=True)
                time.sleep(1)  # 避免异常循环

        logger.info(f"[{threading.current_thread().name}] 分析工作线程已停止")

    def _analyze_and_alert(self, symbol: str, timeframe: str):
        """
        实时分析 + 飞书告警

        流程:
        1. 查询数据库获取基准币种和目标币种的K线数据
        2. 调用 analysis_core.analyze_pair() 进行分析
        3. 保存分析结果到数据库
        4. 如果检测到异常，发送飞书告警

        Args:
            symbol: 目标币种（如 ETH/USDC:USDC）
            timeframe: 时间周期（如 5m）
        """
        # 开始计时（用于监控分析延迟）
        start_time = time.time()

        try:
            # 跳过基准币种自身
            if symbol == self.base_symbol:
                return

            # 确定分析窗口（根据周期）
            window_map = {
                '5m': timedelta(days=7),   # 5分钟周期: 7天数据
                '1h': timedelta(days=30),  # 1小时周期: 30天数据
                '4h': timedelta(days=60)   # 4小时周期: 60天数据
            }
            window = window_map.get(timeframe, timedelta(days=30))

            # 查询基准币种K线
            end_time = datetime.now(timezone.utc)
            query_start_time = end_time - window

            base_klines = self.kline_repo.query_range(
                self.base_symbol,
                timeframe,
                query_start_time,
                end_time,
                limit=10000
            )

            # 查询目标币种K线
            alt_klines = self.kline_repo.query_range(
                symbol,
                timeframe,
                query_start_time,
                end_time,
                limit=10000
            )

            # 数据点不足，跳过分析
            if len(base_klines) < 30 or len(alt_klines) < 30:
                logger.debug(f"数据点不足，跳过分析: {symbol} @ {timeframe}")
                return

            # 执行配对分析
            analysis_result = analyze_pair(
                base_klines=base_klines,
                alt_klines=alt_klines,
                corr_threshold=0.5,      # 相关性阈值
                coint_significance=0.05,  # 协整检验显著性
                zscore_threshold=2.0      # Z-score 异常阈值
            )

            # 统计
            self.stats['analyses_performed'] += 1

            # 保存分析结果到数据库
            analysis_record = {
                'analysis_time': datetime.now(timezone.utc),
                'symbol': symbol,
                'base_symbol': self.base_symbol,
                f'corr_{timeframe}_{int(window.days)}d': analysis_result['correlation'],
                f'zscore_{timeframe}': analysis_result['zscore'],
                'cointegration_passed': analysis_result['cointegration_passed'],
                'adf_pvalue': analysis_result['adf_pvalue'],
                'is_anomaly': analysis_result['is_anomaly'],
                'trading_direction': analysis_result['trading_direction'],
                'signal_strength': analysis_result['signal_strength']
            }

            # 批量缓冲写入（非阻塞）
            try:
                self.analysis_result_buffer.put_nowait(analysis_record)
            except queue.Full:
                logger.warning(f"分析结果缓冲队列已满，丢弃: {symbol}")
                self.stats['analysis_result_buffer_drops'] += 1

            # 如果检测到异常，发送飞书告警
            if analysis_result['is_anomaly']:
                self._send_alert(symbol, timeframe, analysis_result)

            # 输出延迟日志（如果超过5秒则警告）
            elapsed = time.time() - start_time
            if elapsed > 5.0:
                logger.warning(f"⚠️ 分析延迟过高: {symbol} @ {timeframe} | {elapsed:.2f}秒")
            else:
                logger.debug(f"分析完成: {symbol} @ {timeframe} | {elapsed:.2f}秒")

        except Exception as e:
            logger.error(f"分析失败: {symbol} @ {timeframe} | {e}", exc_info=True)

    def _send_alert(self, symbol: str, timeframe: str, analysis_result: Dict):
        """
        发送飞书告警

        Args:
            symbol: 币种
            timeframe: 周期
            analysis_result: 分析结果
        """
        try:
            # 构建告警标题
            direction_emoji = "📈" if analysis_result['trading_direction'] == 'long' else "📉"
            strength_emoji = {
                'strong': '🔥',
                'medium': '⚡',
                'weak': '💡'
            }.get(analysis_result['signal_strength'], '💡')

            title = f"{direction_emoji} 配对交易信号 {strength_emoji}"

            # 构建告警内容（Markdown格式）
            content = f"""**币种**: {symbol}
**周期**: {timeframe}
**基准**: {self.base_symbol}

---

**分析结果**:
- 相关系数: {analysis_result['correlation']:.3f}
- Z-score: {analysis_result['zscore']:.2f}
- 协整检验: {'✅ 通过' if analysis_result['cointegration_passed'] else '❌ 未通过'}
- p-value: {analysis_result['adf_pvalue']:.4f}

**交易方向**: {analysis_result['trading_direction'].upper()}
**信号强度**: {analysis_result['signal_strength'].upper()}

**时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""

            # 发送飞书消息（彩色卡片）
            sender_colourful(
                url=self.lark_webhook_url,
                content=content,
                title=title
            )

            # 统计
            self.stats['alerts_sent'] += 1

            logger.info(
                f"📢 告警已发送: {symbol} @ {timeframe} | "
                f"{analysis_result['trading_direction']} | "
                f"{analysis_result['signal_strength']}"
            )

        except Exception as e:
            logger.error(f"飞书告警发送失败: {e}", exc_info=True)

    def _monitor_new_symbols(self):
        """
        新币种监控线程

        策略:
        - 每小时查询一次交易所
        - 发现新币种自动添加到数据库和订阅列表
        """
        logger.info("新币种监控线程已启动")

        while not self.stop_event.is_set():
            try:
                # 获取交易所币种列表
                info = Info(constants.MAINNET_API_URL, skip_ws=True)
                meta = info.meta()

                exchange_symbols = set()
                for asset_info in meta.get('universe', []):
                    name = asset_info.get('name')
                    if name:
                        symbol = f"{name}/USDC:USDC"
                        exchange_symbols.add(symbol)

                # 对比现有币种（修复竞态条件：使用锁保护）
                with self.symbols_lock:
                    current_symbols = set(self.symbols)
                    new_symbols = exchange_symbols - current_symbols

                    if new_symbols:
                        logger.info(f"🆕 发现新币种: {len(new_symbols)} 个")

                        registered_symbols = []
                        new_subscriptions = []  # 新增：构建动态订阅列表

                        for symbol in new_symbols:
                            # 注册到数据库
                            base_asset = symbol.split('/')[0]
                            self.symbol_repo.upsert_symbol(
                                symbol=symbol,
                                base_asset=base_asset,
                                quote_asset='USDC',
                                is_active=True
                            )

                            # 添加到内存列表
                            self.symbols.append(symbol)
                            registered_symbols.append(symbol)

                            # 构建新订阅（修复：动态订阅支持）
                            coin = symbol.split('/')[0]
                            for timeframe in self.timeframes:
                                new_subscriptions.append({
                                    "type": "candle",
                                    "coin": coin,
                                    "interval": timeframe
                                })

                        logger.info(f"✅ 新币种已注册: {len(registered_symbols)} 个币种: {', '.join(registered_symbols)}")

                        # 动态添加订阅（修复：新币种监控失效）
                        if new_subscriptions:
                            success = self.ws_manager.add_subscriptions(new_subscriptions)
                            if success:
                                logger.info(f"🔄 动态订阅已添加: {len(new_subscriptions)} 个订阅（无需重启）")
                            else:
                                logger.warning("⚠️ 动态订阅失败，建议重启服务以更新订阅列表")

            except Exception as e:
                logger.error(f"新币种监控异常: {e}", exc_info=True)

            # 每小时检查一次
            self.stop_event.wait(3600)

        logger.info("新币种监控线程已停止")

    def on_state_change(self, state: ConnectionState, error: Optional[Exception] = None):
        """
        WebSocket 状态变化回调

        Args:
            state: 连接状态
            error: 错误信息（如果有）
        """
        logger.info(f"WebSocket 状态: {state.value}")

        if error:
            logger.error(f"WebSocket 错误: {error}")

    def get_stats(self) -> Dict:
        """
        获取服务统计信息

        Returns:
            统计信息字典
        """
        uptime = time.time() - self.stats['start_time']

        return {
            **self.stats,
            'uptime_seconds': uptime,
            'buffer_size': self.kline_buffer.qsize(),
            'analysis_queue_size': self.analysis_queue.qsize(),  # 新增：分析队列大小
            'analysis_result_buffer_size': self.analysis_result_buffer.qsize(),  # 新增：分析结果缓冲队列大小
            'ws_stats': self.ws_manager.get_stats()
        }

    def start(self):
        """
        启动服务（阻塞运行）

        流程:
        1. 启动批量写入线程
        2. 启动新币种监控线程
        3. 启动 WebSocket 服务（阻塞）
        """
        logger.info("🚀 启动实时K线分析服务...")

        try:
            # 启动批量写入线程
            self.batch_writer_thread.start()
            logger.info("✅ 批量写入线程已启动")

            # 启动新币种监控线程
            self.symbol_monitor_thread.start()
            logger.info("✅ 新币种监控线程已启动")

            # 启动分析结果批量写入线程
            self.analysis_result_writer_thread.start()
            logger.info("✅ 分析结果批量写入线程已启动")

            # 启动 WebSocket（阻塞）
            self.ws_manager.start()

        except KeyboardInterrupt:
            logger.info("接收到中断信号，停止服务...")
        except Exception as e:
            logger.error(f"服务异常: {e}", exc_info=True)
        finally:
            self.stop()

    def stop(self):
        """
        停止服务（优雅关闭）

        流程:
        1. 停止接收新消息
        2. 等待kline_buffer清空（新增！）
        3. 等待分析队列清空
        4. 等待分析结果缓冲队列清空
        5. 设置停止信号并等待线程退出
        """
        logger.info("停止实时K线分析服务...")

        # 1. 停止接收新消息
        self.ws_manager.stop()

        # 2. 等待kline_buffer清空（修复：新增kline_buffer等待）
        if not self.kline_buffer.empty():
            buffer_size = self.kline_buffer.qsize()
            logger.info(f"等待kline_buffer清空: {buffer_size} 条K线")
            try:
                self.kline_buffer.join()
                logger.info("✅ kline_buffer已清空")
            except Exception as e:
                remaining = self.kline_buffer.qsize()
                logger.warning(f"⚠️ kline_buffer未完全清空（剩余 {remaining} 条），强制退出: {e}")

        # 3. 等待分析队列清空
        if not self.analysis_queue.empty():
            queue_size = self.analysis_queue.qsize()
            logger.info(f"等待分析队列清空: {queue_size} 个任务")
            try:
                self.analysis_queue.join()
                logger.info("✅ 分析队列已清空")
            except Exception as e:
                remaining = self.analysis_queue.qsize()
                logger.warning(f"⚠️ 分析队列未完全清空（剩余 {remaining} 个任务），强制退出: {e}")

        # 4. 等待分析结果缓冲队列清空
        if not self.analysis_result_buffer.empty():
            buffer_size = self.analysis_result_buffer.qsize()
            logger.info(f"等待分析结果缓冲队列清空: {buffer_size} 条记录")
            try:
                self.analysis_result_buffer.join()
                logger.info("✅ 分析结果缓冲队列已清空")
            except Exception as e:
                remaining = self.analysis_result_buffer.qsize()
                logger.warning(f"⚠️ 分析结果缓冲队列未完全清空（剩余 {remaining} 条），强制退出: {e}")

        # 5. 设置停止信号（工作线程将退出）
        self.stop_event.set()

        # 4. 等待工作线程退出
        for worker in self.analysis_workers:
            if worker.is_alive():
                worker.join(timeout=5)
                if worker.is_alive():
                    logger.warning(f"⚠️ 工作线程 {worker.name} 未能在5秒内退出")

        # 等待批量写入线程结束
        if self.batch_writer_thread.is_alive():
            self.batch_writer_thread.join(timeout=10)

        # 等待新币种监控线程结束
        if self.symbol_monitor_thread.is_alive():
            self.symbol_monitor_thread.join(timeout=10)

        # 等待分析结果写入线程结束
        if self.analysis_result_writer_thread.is_alive():
            self.analysis_result_writer_thread.join(timeout=10)

        # 输出统计信息
        stats = self.get_stats()
        logger.info(f"📊 服务统计:")
        logger.info(f"   - 消息接收: {stats['messages_received']}")
        logger.info(f"   - K线写入: {stats['klines_written']}")
        logger.info(f"   - 分析完成: {stats['analyses_completed']}")
        logger.info(f"   - 分析失败: {stats['analyses_failed']}")
        logger.info(f"   - 分析队列丢弃: {stats.get('analysis_queue_drops', 0)}")
        logger.info(f"   - 分析结果写入: {stats.get('analysis_results_written', 0)}")
        logger.info(f"   - 分析结果去重: {stats.get('analysis_results_deduped', 0)}")
        logger.info(f"   - 分析结果丢弃: {stats.get('analysis_result_buffer_drops', 0)}")
        logger.info(f"   - 告警发送: {stats['alerts_sent']}")
        logger.info(f"   - 运行时长: {stats['uptime_seconds']:.0f}秒")

        logger.info("✅ 服务已停止")


# =====================================================
# 主程序入口
# =====================================================

def main():
    """主程序入口"""
    # 创建服务实例
    service = RealtimeKlineService(
        base_symbol='BTC/USDC:USDC',
        timeframes=['5m', '1h', '4h'],
        batch_size=1000,
        batch_timeout=5.0
    )

    # 启动服务
    service.start()


if __name__ == '__main__':
    main()
