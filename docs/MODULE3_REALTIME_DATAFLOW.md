# 模块3: 实时分析引擎 (Real-time Analysis Engine)

## 📋 模块概述

⭐ **核心模块**：优先级为P0，这是系统的主分析引擎，完全替代multi_coins.py的批量分析模式。

负责WebSocket实时K线数据流接收、每根K线闭合后的即时分析、Z-score异常检测、飞书告警，以及动态币种订阅管理。

### 模块职责
- ✅ WebSocket连接管理（自动重连，仅订阅5m/1h/4h周期）
- ✅ 实时K线数据接收和解析
- ✅ **每根K线闭合后立即分析**（<1分钟延迟）
- ✅ 调用utils/analysis_core.py公共分析模块
- ✅ Z-score异常检测与飞书实时告警
- ✅ 批量写入TimescaleDB（异步队列）
- ✅ 动态币种订阅（200+币种 × 3周期 = 600订阅）
- ✅ 新币种监控（每小时检测）
- ✅ **Phase 1.5 性能优化**:
  - 5个可配置分析工作线程 (环境变量: ANALYSIS_WORKERS)
  - 异步分析队列 (Queue.maxsize=5000, 支持25秒缓冲)
  - 差异化去重窗口 (5m:60s, 1h:300s, 4h:900s)
  - CPU占用降低30% (30-45% → 20-30%)
  - 容量余量提升140% (100% → 240%)
  - 节省70-80%不必要的重复分析

### 依赖关系
- **上游依赖**: 模块1（数据库）、模块2（访问层）
- **下游依赖**: 无（独立服务）

## 🏗️ 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│         Hyperliquid WebSocket API (600个订阅)                 │
│  (200币种 × 3周期: 5m, 1h, 4h)                                │
└────────────────┬─────────────────────────────────────────────┘
                 │ 实时K线数据（≈7.4次/秒）
                 ↓
┌─────────────────────────────────────────────────────────────┐
│      EnhancedWebSocketManager                               │
│  • 双重健康检测（底层连接+应用层心跳）                       │
│  • 假活检测（30秒无数据自动重连）                            │
│  • 指数退避重连策略（1s→2s→4s→...→60s）                     │
│  • 线程安全设计（RLock）                                     │
└────────────┬──────────────────┬────────────────────────────────┘
             │                  │
             ↓                  ↓
        [on_message]        [on_state_change]
             │                  │
    ┌────────┴──────────────────┴────────┐
    ↓                                    ↓
[kline_buffer]                   [分析异步队列] 【Phase 1.5】
(Queue, 最大10000条)           (Queue, 最大5000任务)
    │                                    │
    ↓                                    ↓
[_batch_writer线程]           [5个_analysis_worker线程]
│                             (可配置，默认5)
├─ 去重（按time+symbol+tf）  │
├─ 批量写入（1000条或5秒）   ├─ 差异化去重:
└─ COPY高性能插入             │  • 5m: 60秒冷却
                              │  • 1h: 300秒冷却 (-80%分析)
                              │  • 4h: 900秒冷却 (-93%分析)
                              │
                              └─ _analyze_and_alert()
                                 ├─ 数据库查询
                                 ├─ 统计分析
                                 ├─ 异常检测
                                 └─ 飞书告警

        TimescaleDB
        (K线存储+分析结果)
```

**关键数据流**：
- 每根K线闭合 → 同时触发"写入DB"和"分析队列"
- 实际消息速率：7.4次/秒（600订阅）
- 分析吞吐能力：2.5次/秒（5线程×0.5次/秒）
- 容量余量：240%（峰值应对能力）

## 📦 核心类设计

### 类: RealtimeKlineService

```python
class RealtimeKlineService:
    """实时K线分析服务（主分析引擎）"""

    def __init__(self, base_symbol: str = 'BTC/USDC:USDC'):
        """
        初始化实时分析服务

        Args:
            base_symbol: 基础币种（用于配对分析），默认BTC/USDC:USDC
        """
        self.base_symbol = base_symbol

        # 分析配置：5m(7天), 1h(30天), 4h(60天)
        self.ANALYSIS_CONFIGS = [
            ('5m', '7d'),
            ('1h', '30d'),
            ('4h', '60d')
        ]

        # 订阅周期（仅5m/1h/4h，不含1m）
        self.timeframes = ['5m', '1h', '4h']

        # 动态获取币种列表
        self.symbols = self._get_all_symbols_from_exchange()

        # 初始化数据库客户端
        self.db_client = TimescaleDBClient(...)
        self.kline_repo = KlineRepository(self.db_client)
        self.analysis_repo = AnalysisResultRepository(self.db_client)
        self.symbol_metadata_repo = SymbolMetadataRepository(self.db_client)

        # 缓冲队列（线程安全）
        self.kline_buffer = queue.Queue(maxsize=10000)

        # 分析任务队列（Phase 1.5 新增）
        self.analysis_queue = queue.Queue(maxsize=5000)

        # 统计信息
        self.stats = {
            'analyses_completed': 0,
            'analyses_failed': 0,
            'analysis_queue_drops': 0
        }

        # 停止事件
        self.stop_event = threading.Event()

        # 分析工作线程（可配置化，默认5个）
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
            daemon=True
        )

        # 新币种监控线程
        self.symbol_monitor_thread = threading.Thread(
            target=self._monitor_new_symbols,
            daemon=True
        )

        # WebSocket管理器
        self.ws_manager = None
```

---

### 方法1: on_message() - WebSocket消息回调 【Phase 1.5 异步队列版】

```python
def on_message(self, msg: Dict):
    """
    WebSocket消息回调处理 (Phase 1.5 异步队列版)

    核心逻辑:
    1. 写入DB（异步批量队列）
    2. 触发实时分析（异步队列 + 工作线程）

    Phase 1.5 优化:
    - 分析改为异步队列模式,避免阻塞消息接收
    - 5个工作线程并行处理分析任务
    - 差异化去重机制减少70-80%不必要分析

    性能对比:
    - Phase 1: 同步调用 _analyze_and_alert()，可能阻塞消息接收
    - Phase 1.5: 异步队列 + 工作线程，消息处理时间 <0.1ms

    Hyperliquid数据格式:
    {
      "channel": "candle",
      "data": {
        "t": 1704067260000,  # 开盘时间（毫秒）
        "s": "ETH",          # 币种符号
        "i": "5m",           # 时间周期 (仅5m/1h/4h)
        "o": "2295.5",       # 开盘价
        "h": "2296.8",       # 最高价
        "l": "2295.2",       # 最低价
        "c": "2296.3",       # 收盘价
        "v": "1234.56"       # 成交量
      }
    }
    """
    try:
        if msg.get("channel") != "candle":
            return

        data = msg.get("data", {})
        kline = self._parse_kline_data(data)

        if not kline:
            return

        # 1. 写入DB（异步批量队列）
        try:
            self.kline_buffer.put_nowait(kline)
        except queue.Full:
            logger.warning(f"缓冲队列已满，丢弃K线 | {kline['symbol']}")

        # 2. 触发实时分析（异步队列）【Phase 1.5 核心优化】
        analysis_task = {
            'symbol': kline['symbol'],
            'timeframe': kline['timeframe']
        }
        try:
            self.analysis_queue.put_nowait(analysis_task)
        except queue.Full:
            logger.warning(f"分析队列已满，跳过分析: {kline['symbol']} @ {kline['timeframe']}")
            self.stats['analysis_queue_drops'] += 1

    except Exception as e:
        logger.error(f"消息处理失败: {e}", exc_info=True)
```

---

### 方法2: _batch_writer() - 异步批量写入线程

```python
def _batch_writer(self):
    """
    异步批量写入线程 (与 Phase 1 一致)

    策略:
    - 累积1000-2000条记录后批量写入
    - 或者5秒超时后强制写入（避免数据积压）
    - 使用 psycopg 3.x ConnectionPool + COPY 命令
    - 写入性能: >40000条/秒

    Phase 1.5 说明:
    - 此方法与 Phase 1 保持一致,无需修改
    - 与分析队列解耦,独立运行
    """
    BATCH_SIZE = 1000
    MAX_BATCH_SIZE = 2000
    TIMEOUT_SECONDS = 5

    batch = {}  # {(symbol, timeframe): [records]}
    last_flush_time = time.time()

    logger.info("批量写入线程已启动")

    while not self.stop_event.is_set():
        try:
            # 从队列获取K线（阻塞5秒超时）
            kline = self.kline_buffer.get(timeout=TIMEOUT_SECONDS)
        except queue.Empty:
            kline = None

        if kline:
            # 按币种+周期分组
            key = (kline['symbol'], kline['timeframe'])
            if key not in batch:
                batch[key] = []

            # 转换为tuple格式
            tuple_data = (
                kline['timestamp'],
                kline['open'],
                kline['high'],
                kline['low'],
                kline['close'],
                kline['volume'],
                kline['volume_usd'],
                kline['return_pct']
            )
            batch[key].append(tuple_data)

        # 计算总记录数
        total_size = sum(len(records) for records in batch.values())

        # 判断是否需要刷新
        should_flush = (
            total_size >= BATCH_SIZE or  # 达到批次大小
            total_size >= MAX_BATCH_SIZE or  # 达到最大批次
            (time.time() - last_flush_time >= TIMEOUT_SECONDS and total_size > 0)  # 超时且有数据
        )

        if should_flush:
            # 批量写入数据库
            for (symbol, timeframe), records in batch.items():
                try:
                    self.kline_repo.batch_upsert_copy(records, symbol, timeframe)
                    logger.info(f"✅ 批量写入 | {symbol} | {timeframe} | {len(records)}条")
                except Exception as e:
                    logger.error(f"批量写入失败 | {symbol} | {timeframe} | {e}")

            # 清空批次
            batch.clear()
            last_flush_time = time.time()

    logger.info("批量写入线程已停止")
```

---

### 方法3: _analysis_worker() - 分析工作线程主循环 【Phase 1.5 核心优化】

```python
def _analysis_worker(self):
    """
    分析工作线程主循环（Phase 1.5 核心优化）

    功能:
    1. 从队列取出分析任务 (analysis_queue.get())
    2. 执行差异化去重检查
    3. 调用 _analyze_and_alert() 进行实时分析
    4. 记录统计信息和分析结果

    差异化去重策略:
    ┌─────────┬──────────┬────────────┬────────────┐
    │ 周期    │ 冷却时间 │ K线更新频率│ 节省分析   │
    ├─────────┼──────────┼────────────┼────────────┤
    │ 5m      │ 60秒     │ 每5分钟    │ 0%         │
    │ 1h      │ 300秒    │ 每60分钟   │ 80%        │
    │ 4h      │ 900秒    │ 每240分钟  │ 93%        │
    └─────────┴──────────┴────────────┴────────────┘
    总体节省: 70-80% CPU资源

    去重算法:
    - 维护字典 recent_tasks: {(symbol, timeframe): timestamp}
    - 检查 current_time - last_analysis_time < dedup_window
    - 超过1000条记录时清理过期数据（保留最近15分钟）

    性能指标:
    - 单线程处理能力: ~0.5次/秒
    - 5线程总吞吐: 2.5次/秒
    - 实际需求: 0.74次/秒
    - 容量余量: 240%

    线程配置:
    - 默认: 5个工作线程 (ANALYSIS_WORKERS=5)
    - 推荐公式: CPU核心数 × 1.5 - 2
    - 动态调整: 通过环境变量配置
    """
    logger.info(f"[{threading.current_thread().name}] 分析工作线程已启动")

    # 去重字典
    recent_tasks = {}  # {(symbol, timeframe): timestamp}

    # 差异化去重窗口
    DEDUP_WINDOWS = {
        '5m': 60,    # 60秒冷却
        '1h': 300,   # 5分钟冷却（减少80%分析）
        '4h': 900,   # 15分钟冷却（减少93%分析）
    }

    while not self.stop_event.is_set():
        try:
            # 获取任务（阻塞1秒超时）
            try:
                task = self.analysis_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            symbol = task['symbol']
            timeframe = task['timeframe']

            # 根据周期获取去重窗口
            dedup_window = DEDUP_WINDOWS.get(timeframe, 60)

            # 去重检查：根据周期设定的时间内已分析过则跳过
            current_time = time.time()
            last_analysis_time = recent_tasks.get((symbol, timeframe), 0)
            time_since_last = current_time - last_analysis_time if last_analysis_time > 0 else 0

            if last_analysis_time > 0 and time_since_last < dedup_window:
                logger.debug(
                    f"跳过重复分析: {symbol} @ {timeframe} "
                    f"(距上次 {time_since_last:.0f}秒，窗口 {dedup_window}秒)"
                )
                self.analysis_queue.task_done()
                continue

            # 执行分析
            try:
                self._analyze_and_alert(symbol, timeframe)
                self.stats['analyses_completed'] += 1
                recent_tasks[(symbol, timeframe)] = current_time

                logger.debug(
                    f"分析完成: {symbol} @ {timeframe} | "
                    f"去重窗口: {dedup_window}秒 | 距上次: {time_since_last:.0f}秒"
                )
            except Exception as e:
                logger.error(f"分析失败: {symbol} @ {timeframe} | {e}", exc_info=True)
                self.stats['analyses_failed'] += 1

            self.analysis_queue.task_done()

            # 定期清理过期记录
            if len(recent_tasks) > 1000:
                max_window = max(DEDUP_WINDOWS.values())
                cutoff_time = current_time - max_window
                recent_tasks = {k: v for k, v in recent_tasks.items() if v > cutoff_time}

        except Exception as e:
            logger.error(f"工作线程异常: {e}", exc_info=True)
            time.sleep(1)

    logger.info(f"[{threading.current_thread().name}] 分析工作线程已停止")
```

**关键设计点**:
- 差异化去重窗口设计（5m/1h/4h不同策略）
- 内存管理（定期清理超过1000条记录）
- 统计信息记录（成功/失败次数）
- 调试日志（记录去重窗口和分析间隔）

---

### 方法4: _monitor_new_symbols() - 新币种监控线程

```python
def _monitor_new_symbols(self):
    """
    新币种监控线程（每小时检测一次）

    检测逻辑:
    1. 从交易所API获取所有USDC永续合约
    2. 与数据库中的symbol_metadata对比
    3. 发现新币种后自动订阅WebSocket
    """
    CHECK_INTERVAL = 3600  # 1小时

    logger.info("新币种监控线程已启动")

    while not self.stop_event.is_set():
        try:
            # 获取交易所所有币种
            exchange_symbols = self._get_all_symbols_from_exchange()

            # 获取数据库已知币种
            known_symbols = set(self.symbol_metadata_repo.get_active_symbols())

            # 找出新币种
            new_symbols = [s for s in exchange_symbols if s not in known_symbols]

            if new_symbols:
                logger.info(f"🆕 发现 {len(new_symbols)} 个新币种: {new_symbols}")

                # 更新symbol_metadata表
                for symbol in new_symbols:
                    self.symbol_metadata_repo.upsert_symbol(
                        symbol=symbol,
                        base_asset=symbol.split('/')[0],
                        quote_asset='USDC',
                        listing_time=datetime.now(timezone.utc)
                    )

                # 更新WebSocket订阅
                self._update_websocket_subscriptions(new_symbols)

        except Exception as e:
            logger.error(f"新币种监控失败: {e}", exc_info=True)

        # 等待1小时
        self.stop_event.wait(CHECK_INTERVAL)

    logger.info("新币种监控线程已停止")
```

---

### 方法5: _analyze_and_alert() - 实时分析与告警 【被工作线程调用】

```python
def _analyze_and_alert(self, symbol: str, timeframe: str):
    """
    单币种实时分析（被工作线程调用）

    调用链路:
    - Phase 1: on_message() → _analyze_and_alert() (同步)
    - Phase 1.5: on_message() → analysis_queue → _analysis_worker() → _analyze_and_alert() (异步)

    核心流程:
    1. 查询历史数据（TimescaleDB）
       - 5m周期: 7天数据
       - 1h周期: 30天数据
       - 4h周期: 60天数据
    2. 调用 utils/analysis_core.py 分析
       - calculate_correlation() 相关性检测
       - check_cointegration() 协整检验
       - calculate_zscore() Z-score计算
       - detect_anomaly() 异常检测
    3. 异常检测 → 飞书告警
    4. 保存分析结果到 analysis_results 表

    性能优化 (Phase 1.5):
    - 异步调用,不阻塞消息接收
    - 差异化去重减少调用频率70-80%
    - 5个线程并行处理,吞吐量提升67%
    """
    try:
        # 查找匹配的分析配置
        period = None
        for tf, pd in self.ANALYSIS_CONFIGS:
            if tf == timeframe:
                period = pd
                break

        if not period:
            return  # 不分析1m等非配置周期

        # 1. 查询历史数据
        now = datetime.now(timezone.utc)
        period_delta = self._parse_period_to_timedelta(period)
        start_time = now - period_delta

        # 查询当前币种和基础币种的历史K线
        alt_history = self.kline_repo.query_range(symbol, timeframe, start_time, now)
        base_history = self.kline_repo.query_range(self.base_symbol, timeframe, start_time, now)

        if len(alt_history) < 20 or len(base_history) < 20:
            logger.debug(f"历史数据不足 | {symbol} | {timeframe}")
            return

        # 2. 调用 utils/analysis_core.py 进行分析
        from utils.analysis_core import (
            calculate_correlation,
            check_cointegration,
            calculate_zscore,
            detect_anomaly
        )

        # 相关性检测
        correlation = calculate_correlation(base_history, alt_history)
        if correlation < 0.5:
            logger.debug(f"相关性不足 | {symbol} | corr={correlation:.3f}")
            return

        # 协整检验
        is_cointegrated, pvalue = check_cointegration(base_history, alt_history)
        if not is_cointegrated:
            logger.debug(f"协整检验失败 | {symbol} | p={pvalue:.4f}")
            return

        # 计算Z-score
        zscore = calculate_zscore(base_history, alt_history)

        # 异常检测
        is_anomaly, direction = detect_anomaly(zscore, threshold=2.0)

        # 3. 如果异常，发送飞书告警
        if is_anomaly:
            self._send_feishu_alert(
                symbol=symbol,
                timeframe=timeframe,
                zscore=zscore,
                correlation=correlation,
                direction=direction
            )

            # 4. 保存分析结果
            result_data = {
                'symbol': symbol,
                'base_symbol': self.base_symbol,
                f'corr_{timeframe}_{period}': correlation,
                f'zscore_{timeframe}': zscore,
                'cointegration_passed': True,
                'adf_pvalue': pvalue,
                'is_anomaly': True,
                'trading_direction': direction,
                'signal_strength': 'strong' if abs(zscore) > 2.5 else 'medium'
            }
            self.analysis_repo.save_result(result_data)

            logger.info(
                f"⚠️ 异常信号 | {symbol} | {timeframe} | "
                f"zscore={zscore:.2f} | corr={correlation:.3f} | {direction}"
            )

    except Exception as e:
        logger.error(f"实时分析失败 | {symbol} | {timeframe} | {e}", exc_info=True)

def _send_feishu_alert(self, symbol: str, timeframe: str, zscore: float,
                       correlation: float, direction: str):
    """发送飞书告警"""
    from utils.lark_bot import send_lark_msg_with_card

    message = f"""
**实时套利信号检测**

**币种**: {symbol}
**周期**: {timeframe}
**基准**: {self.base_symbol}

**指标**:
- Z-score: {zscore:.2f}
- 相关系数: {correlation:.3f}
- 交易方向: {direction}

**时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    """

    try:
        send_lark_msg_with_card("实时套利信号", message)
    except Exception as e:
        logger.error(f"飞书告警发送失败: {e}")

def _parse_period_to_timedelta(self, period: str) -> timedelta:
    """解析周期字符串为timedelta"""
    unit = period[-1]
    value = int(period[:-1])

    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    else:
        raise ValueError(f"不支持的周期单位: {unit}")
```

---

### 方法6: _get_all_symbols_from_exchange() - 动态币种发现

```python
def _get_all_symbols_from_exchange(self) -> List[str]:
    """
    从交易所API动态获取所有USDC永续合约

    Returns:
        ['BTC/USDC:USDC', 'ETH/USDC:USDC', ...]
    """
    markets = self.exchange.load_markets()
    symbols = []

    for symbol in markets:
        market = markets[symbol]
        # 筛选USDC永续合约
        if (market.get('quote') == 'USDC' and
            market.get('settle') == 'USDC' and
            market.get('type') == 'swap'):
            symbols.append(symbol)

    logger.info(f"交易所USDC永续合约数量: {len(symbols)}")
    return sorted(symbols)
```

---

### 方法7: start() - 启动服务

```python
def start(self):
    """启动实时K线服务（阻塞运行）"""
    logger.info("🚀 启动实时K线服务...")

    # 启动批量写入线程
    self.batch_writer_thread.start()

    # 启动新币种监控线程
    self.symbol_monitor_thread.start()

    # 构建WebSocket订阅列表
    subscriptions = []
    for symbol in self.symbols:
        for timeframe in self.timeframes:
            subscriptions.append({
                "type": "candle",
                "coin": symbol,  # 仅基础币种名（如"BTC"）
                "interval": timeframe
            })

    logger.info(f"订阅数量: {len(subscriptions)} ({len(self.symbols)}币种 × {len(self.timeframes)}周期)")

    # 创建WebSocket管理器
    self.ws_manager = EnhancedWebSocketManager(
        base_url=constants.MAINNET_API_URL,
        subscriptions=subscriptions,
        message_callback=self.on_message,
        on_state_change=self.on_state_change,
        timeout=30  # 30秒无数据超时
    )

    # 启动WebSocket（阻塞运行）
    try:
        self.ws_manager.start()
    except KeyboardInterrupt:
        logger.info("接收到中断信号，停止服务...")
        self.stop()
    except Exception as e:
        logger.error(f"服务运行异常: {e}", exc_info=True)
        self.stop()
```

## 🐳 Docker容器配置

### 文件: Dockerfile.realtime

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml ./
COPY requirements_websocket.txt ./

# 安装Python依赖
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r requirements_websocket.txt

# 克隆并安装strong-hyperliquid-websocket
RUN git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git && \
    cd strong-hyperliquid-websocket && \
    pip install --no-cache-dir -e .

# 复制应用代码
COPY . .

CMD ["python", "realtime_kline_service.py"]
```

### 文件: requirements_websocket.txt

```txt
# strong-hyperliquid-websocket依赖
hyperliquid-python-sdk>=0.21.0
websockets>=12.0
```

### Docker Compose集成

在现有 `docker-compose.yml` 中添加：

```yaml
services:
  # ... timescaledb服务 ...

  # 新增：实时K线数据服务
  realtime-kline:
    build:
      context: .
      dockerfile: Dockerfile.realtime
    container_name: crypto_realtime_kline
    restart: unless-stopped
    depends_on:
      timescaledb:
        condition: service_healthy
    environment:
      TIMESCALEDB_HOST: timescaledb
      TIMESCALEDB_PORT: 5432
      TIMESCALEDB_NAME: crypto_data
      TIMESCALEDB_USER: postgres
      TIMESCALEDB_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      LARKBOT_ID: ${LARKBOT_ID}
      # Phase 1.5 性能优化配置
      ANALYSIS_WORKERS: ${ANALYSIS_WORKERS:-5}  # 分析工作线程数（默认5个）
    volumes:
      - ./realtime_kline_service.py:/app/realtime_kline_service.py
      - ./utils:/app/utils
    networks:
      - crypto_network
    command: python realtime_kline_service.py
    # 资源限制
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

## 🚀 部署步骤

### 步骤1: 确保模块1、2已完成

```bash
# 验证数据库正常运行
docker ps | grep timescaledb

# 验证数据访问层已实现
ls utils/timescaledb.py
```

### 步骤1.5: 配置分析工作线程数（可选，Phase 1.5）

```bash
# 方式A: 修改 .env 文件（推荐）
echo "ANALYSIS_WORKERS=5" >> .env

# 方式B: 临时设置环境变量
export ANALYSIS_WORKERS=6

# 方式C: Docker Compose 环境变量
docker-compose up -d -e ANALYSIS_WORKERS=6 realtime-kline

# 推荐配置（根据CPU核心数）:
# 4核CPU: ANALYSIS_WORKERS=4
# 6核CPU: ANALYSIS_WORKERS=6
# 8核CPU: ANALYSIS_WORKERS=8
# 12核CPU: ANALYSIS_WORKERS=10
#
# 计算公式: CPU核心数 × 1.5 - 2（预留资源给批量写入线程等）
```

### 步骤2: 启动实时数据流服务

```bash
# 使用Docker Compose启动
docker-compose up -d realtime-kline

# 查看实时日志
docker-compose logs -f realtime-kline

# 预期输出:
# 🚀 启动实时K线服务...
# 批量写入线程已启动
# 新币种监控线程已启动
# 订阅数量: 600 (200币种 × 3周期)
# ✅ WebSocket已连接，开始接收实时数据
```

### 步骤3: 验证数据写入

```bash
# 连接数据库查询最新K线
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

# 查询最近1小时的K线数量（按币种分组）
SELECT symbol, timeframe, COUNT(*) as count, MAX(time) as latest_time
FROM klines
WHERE time >= NOW() - INTERVAL '1 hour'
GROUP BY symbol, timeframe
ORDER BY symbol, timeframe;

# 预期输出: 每个币种每个周期都有最新数据
#   symbol         | timeframe | count | latest_time
# -----------------+-----------+-------+-------------
#  BTC/USDC:USDC  | 1m        |    60 | 2025-01-11 ...
#  BTC/USDC:USDC  | 5m        |    12 | 2025-01-11 ...
#  ETH/USDC:USDC  | 1m        |    60 | 2025-01-11 ...
```

## 🧪 测试策略

### 测试1: WebSocket连接稳定性

```bash
# 运行服务24小时
docker-compose up -d realtime-kline

# 24小时后检查容器状态
docker ps | grep realtime-kline

# 检查日志中是否有异常
docker-compose logs realtime-kline | grep -i "error\|exception"

# 验证: 容器仍在运行，无重启记录
docker inspect crypto_realtime_kline | grep RestartCount
```

**验收标准**: RestartCount = 0（无重启）

---

### 测试2: 数据完整性验证

```sql
-- 检查K线数据连续性（以BTC 1m周期为例）
WITH time_series AS (
    SELECT generate_series(
        NOW() - INTERVAL '1 hour',
        NOW(),
        INTERVAL '1 minute'
    ) AS expected_time
),
actual_data AS (
    SELECT time FROM klines
    WHERE symbol = 'BTC/USDC:USDC' AND timeframe = '1m'
        AND time >= NOW() - INTERVAL '1 hour'
)
SELECT
    COUNT(*) AS expected_count,
    (SELECT COUNT(*) FROM actual_data) AS actual_count,
    ROUND(100.0 * (SELECT COUNT(*) FROM actual_data) / COUNT(*), 2) AS coverage_rate
FROM time_series;

-- 预期: coverage_rate > 95%
```

---

### 测试3: 断线重连测试

```bash
# 模拟网络断开（杀死WebSocket连接）
docker exec -it crypto_realtime_kline pkill -9 python

# 等待10秒，容器应自动重启
sleep 10

# 检查容器状态
docker ps | grep realtime-kline

# 查看日志，应显示重连成功
docker-compose logs --tail=50 realtime-kline | grep -i "reconnect\|connected"

# 预期输出:
# ⚠️ WebSocket已断开，等待重连...
# ✅ WebSocket重连成功
```

---

### 测试4: 批量写入性能测试

```bash
# 监控批量写入日志
docker-compose logs -f realtime-kline | grep "批量写入"

# 预期输出（每5秒或累积1000条后）:
# ✅ 批量写入 | BTC/USDC:USDC | 1m | 1234条
# ✅ 批量写入 | ETH/USDC:USDC | 5m | 456条
```

**验收标准**: 平均批量大小 >500条/次

---

### 测试5: Phase 1.5 性能验证

**测试目标**: 验证多线程优化和差异化去重效果

#### 子测试1: 验证工作线程数

```bash
# 查看启动日志
docker-compose logs realtime-kline | grep "启动.*个分析工作线程"

# 预期输出:
# INFO - ✅ 启动5个分析工作线程（ANALYSIS_WORKERS=5）
# INFO - [analysis-worker-0] 分析工作线程已启动
# ...
# INFO - [analysis-worker-4] 分析工作线程已启动
```

#### 子测试2: 验证差异化去重窗口

```bash
# 观察分析完成日志
docker-compose logs realtime-kline | grep "分析完成" | tail -20

# 预期输出示例:
# DEBUG - 分析完成: ETH/USDC:USDC @ 5m | 去重窗口: 60秒 | 距上次: 95秒
# DEBUG - 分析完成: BTC/USDC:USDC @ 1h | 去重窗口: 300秒 | 距上次: 420秒
# DEBUG - 分析完成: SOL/USDC:USDC @ 4h | 去重窗口: 900秒 | 距上次: 1050秒
```

#### 子测试3: 验证性能提升

```bash
# 监控CPU占用（运行1小时后）
docker stats crypto_realtime_kline --no-stream

# 预期输出:
# CONTAINER           CPU %    MEM USAGE / LIMIT    MEM %
# crypto_realtime... 22.5%    348.2MB / 512MB      68%
```

**验收标准**:
- ✅ 工作线程数正确 (5个)
- ✅ 去重窗口正确 (5m:60s, 1h:300s, 4h:900s)
- ✅ CPU占用降低至20-30%
- ✅ 分析队列深度稳定在50-200

## 📊 性能预期 (Phase 1.5 优化版)

| 指标 | Phase 1 | Phase 1.5 | 改善幅度 | 说明 |
|------|---------|-----------|----------|------|
| **分析延迟** | <5秒 | <5秒 | 持平 | 从K线闭合到飞书告警完成 |
| **分析频率** | 12次/分钟 | 0.74次/秒 | 优化调度 | 差异化去重后的实际频率 |
| **工作线程数** | 3个(固定) | 5个(可配置) | 67%↑ | 环境变量 ANALYSIS_WORKERS |
| **吞吐能力** | 1.5次/秒 | 2.5次/秒 | 67%↑ | 单线程0.5次/秒 × 5线程 |
| **容量余量** | 100% | 240% | 140%↑ | (2.5-0.74)/0.74 ≈ 240% |
| **CPU占用** | 30-45% | 20-30% | 30%↓ | 差异化去重节省资源 |
| **内存占用** | <512MB | <512MB | 持平 | 实时服务进程 |
| **分析队列深度** | 100-500 | 50-200 | 更稳定 | 波动范围缩小 |
| **不必要分析** | 基准 | 减少70-80% | 70-80%↓ | 差异化去重效果 |
| **WebSocket延迟** | <500ms | <500ms | 持平 | K线闭合后推送延迟 |
| **写入吞吐量** | >1000条/秒 | >40000条/秒 | 40倍↑ | psycopg 3.x COPY命令 |
| **DB查询耗时** | <100ms | <100ms | 持平 | 单次查询60天历史数据 |
| **数据完整性** | >95% | >95% | 持平 | 无丢失K线 |
| **连续运行时间** | >24小时 | >24小时 | 持平 | 无崩溃 |

**Phase 1.5 核心优化总结**:
1. **多线程并行**: 3线程 → 5线程,吞吐能力提升67%
2. **差异化去重**: 按周期设置冷却时间,节省70-80%CPU资源
3. **异步队列**: 消息接收与分析解耦,避免阻塞
4. **容量余量**: 从100%提升至240%,应对峰值流量更从容
5. **可配置化**: 环境变量控制线程数,灵活调整
6. **COPY命令**: 批量写入性能提升40倍

**关键技术**:
- psycopg 3.x ConnectionPool（连接池管理）
- Queue.Queue（线程安全队列）
- threading.Thread（工作线程）
- COPY命令（高性能批量写入）
- 差异化去重算法（时间窗口检查）

## ⚠️ 常见问题排查

### 问题1: WebSocket连接失败

**症状**: 日志显示"WebSocket连接错误"

**排查步骤**:
```bash
# 检查网络连接
ping api.hyperliquid.xyz

# 查看详细错误日志
docker-compose logs realtime-kline | grep -A 10 "error"
```

**解决方案**:
- 检查防火墙是否阻止WebSocket连接（WSS端口443）
- 验证Hyperliquid API是否可用

---

### 问题2: 缓冲队列满

**症状**: 日志显示"缓冲队列已满，丢弃K线"

**排查步骤**:
```bash
# 检查数据库写入速度
docker-compose logs realtime-kline | grep "批量写入"
```

**解决方案**:
- 增加批量写入频率（减少TIMEOUT_SECONDS）
- 增加队列大小（maxsize=20000）
- 检查数据库性能（是否有慢查询）

---

### 问题3: 新币种未自动订阅

**症状**: 交易所上线新币种但WebSocket未订阅

**排查步骤**:
```bash
# 查看新币种监控线程日志
docker-compose logs realtime-kline | grep "新币种"
```

**解决方案**:
- 手动触发监控（重启服务）
- 检查symbol_metadata表是否有新币种记录

---

### 问题4: 工作线程数未生效 【Phase 1.5】

**症状**: 日志显示仍是3个线程,而非配置的5个

**排查步骤**:
```bash
# 1. 检查环境变量
echo $ANALYSIS_WORKERS

# 2. 检查 .env 文件
cat .env | grep ANALYSIS_WORKERS

# 3. 确认服务读取配置
docker-compose logs realtime-kline | grep "启动.*个分析工作线程"
```

**解决方案**:
- 确保 `.env` 文件在项目根目录
- 确保 `ANALYSIS_WORKERS` 为整数值
- 重启服务: `docker-compose restart realtime-kline`

---

### 问题5: 分析频率异常 【Phase 1.5】

**症状**: 1h或4h周期的分析频率过高

**排查步骤**:
```bash
# 观察去重窗口日志
docker-compose logs realtime-kline | grep "跳过重复分析" | tail -20
docker-compose logs realtime-kline | grep "分析完成" | tail -20
```

**预期日志**:
```
跳过重复分析: BTC/USDC:USDC @ 1h (距上次 120秒，窗口 300秒)
分析完成: BTC/USDC:USDC @ 1h | 去重窗口: 300秒 | 距上次: 420秒
```

**解决方案**:
- 检查 `DEDUP_WINDOWS` 字典配置
- 确认去重逻辑正确实现
- 如窗口不正确,重新部署代码

---

### 问题6: CPU占用未降低 【Phase 1.5】

**症状**: CPU占用仍在30-45%

**可能原因**:
1. 服务刚启动,缓存数据较多
2. 市场波动大,消息速率高
3. 去重机制尚未生效

**排查步骤**:
```bash
# 1. 检查分析队列深度
docker-compose logs realtime-kline | grep "健康报告" | tail -10

# 2. 计算跳过分析比例
grep "跳过重复分析" logs/service.log | wc -l
grep "分析完成" logs/service.log | wc -l

# 3. 观察CPU趋势（运行1小时后）
docker stats crypto_realtime_kline --no-stream
```

**解决方案**:
- 运行1-2小时后观察趋势
- 预期CPU会逐步降低至20-30%
- 如长时间未降低,检查去重逻辑

## ✅ 验收标准

### 基础功能
- [ ] WebSocket成功连接Hyperliquid
- [ ] 仅订阅5m/1h/4h周期（600个订阅 = 200币种 × 3周期）
- [ ] K线数据正确写入TimescaleDB
- [ ] 批量写入性能>500条/次
- [ ] 断线后自动重连成功
- [ ] 数据库中的K线时间戳连续（覆盖率>95%）

### 实时分析功能
- [ ] 每根K线闭合后触发实时分析
- [ ] 分析延迟<5秒（查询DB + 计算 + 告警）
- [ ] utils/analysis_core.py正确调用
- [ ] Z-score异常检测正确（|zscore| > 2.0）
- [ ] 飞书告警及时到达（<10秒）
- [ ] 分析结果正确保存到analysis_results表

### 可靠性
- [ ] 服务连续运行24小时无崩溃
- [ ] 内存占用稳定在512MB以内
- [ ] CPU占用<50%
- [ ] 新币种监控线程正常工作

### Phase 1.5 性能优化验收 【新增】
- [ ] 工作线程数正确（默认5个,可配置）
- [ ] 环境变量 ANALYSIS_WORKERS 配置生效
- [ ] 差异化去重窗口正确（5m:60s, 1h:300s, 4h:900s）
- [ ] CPU占用降低至20-30%（相比Phase 1降低30%）
- [ ] 分析队列深度稳定在50-200
- [ ] 容量余量达到240%（吞吐2.5次/秒 vs 需求0.74次/秒）
- [ ] 不必要分析减少70-80%（观察"跳过重复分析"日志）
- [ ] 分析工作线程正常启动和运行
- [ ] 异步队列模式工作正常（消息接收不阻塞）
- [ ] 去重字典定期清理（无内存泄漏）

### 可观测性验收 【新增】
- [ ] 启动日志显示工作线程数配置
- [ ] 分析完成日志记录去重窗口和分析间隔
- [ ] 跳过重复分析日志符合预期频率
- [ ] 健康报告日志完整（队列深度、统计信息）
- [ ] 统计信息准确（analyses_completed, analyses_failed, analysis_queue_drops）
