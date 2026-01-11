# 模块3: 实时数据流 (Real-time Data Flow)

## 📋 模块概述

⚠️ **注意**: 这是一个**可选的增强功能模块**，优先级为P1。基础功能（模块1、2、4、5）完成后可选实施。

负责WebSocket实时K线数据流的接收、缓冲、批量写入，以及动态币种订阅管理和新币种监控。

### 模块职责
- ✅ WebSocket连接管理（自动重连）
- ✅ 实时K线数据接收和解析
- ✅ 缓冲队列和异步批量写入线程
- ✅ 动态币种订阅（200+币种）
- ✅ 新币种监控（每小时检测）
- ✅ 可选的实时套利信号检测

### 依赖关系
- **上游依赖**: 模块1（数据库）、模块2（访问层）
- **下游依赖**: 无（独立服务）

## 🏗️ 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│         Hyperliquid Exchange WebSocket API                   │
│         (wss://api.hyperliquid.xyz/ws)                       │
└────────────────────────┬─────────────────────────────────────┘
                         │ 推送K线数据 (1m, 5m, 1h, 4h...)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│           realtime_kline_service.py                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  EnhancedWebSocketManager                              │  │
│  │  - 600+ 订阅 (200币种 × 3周期)                         │  │
│  │  - 自动重连 + 心跳检测                                  │  │
│  │  - "假活"检测（30秒无数据超时）                         │  │
│  └────────────────┬───────────────────────────────────────┘  │
│                   │ on_message()                             │
│                   ▼                                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Data Parser (解析Hyperliquid格式)                     │  │
│  │  - 时间戳转换 (ms → datetime)                          │  │
│  │  - 币种格式化 (ETH → ETH/USDC:USDC)                    │  │
│  │  - 数据验证                                            │  │
│  └────────────────┬───────────────────────────────────────┘  │
│                   │                                          │
│                   ▼                                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Buffer Queue (缓冲队列)                                │  │
│  │  - Queue.Queue (线程安全)                               │  │
│  │  - 最大容量: 10000条                                    │  │
│  └────────────────┬───────────────────────────────────────┘  │
│                   │                                          │
│                   ▼                                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Batch Writer Thread (异步批量写入线程)                 │  │
│  │  - 批次大小: 1000-2000条                                │  │
│  │  - 超时时间: 5秒                                        │  │
│  │  - COPY命令批量写入                                     │  │
│  └────────────────┬───────────────────────────────────────┘  │
└────────────────────┼──────────────────────────────────────────┘
                     │
                     ▼
          ┌─────────────────────────┐
          │   TimescaleDB (klines表) │
          └─────────────────────────┘
```

## 📦 核心类设计

### 类: RealtimeKlineService

```python
class RealtimeKlineService:
    """实时K线数据服务"""

    def __init__(self, symbols: List[str], timeframes: List[str],
                 enable_realtime_analysis: bool = False):
        """
        初始化实时K线服务

        Args:
            symbols: 订阅的币种列表，如 ["BTC", "ETH", "SOL"]
            timeframes: 订阅的时间周期，如 ["1m", "5m", "1h"]
            enable_realtime_analysis: 是否启用实时分析（Z-score检测）
        """
        self.symbols = symbols
        self.timeframes = timeframes
        self.enable_realtime_analysis = enable_realtime_analysis

        # 初始化数据库客户端
        self.db_client = TimescaleDBClient(...)
        self.kline_repo = KlineRepository(self.db_client)

        # 缓冲队列（线程安全）
        self.kline_buffer = queue.Queue(maxsize=10000)

        # 停止事件
        self.stop_event = threading.Event()

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

### 方法1: on_message() - WebSocket消息回调

```python
def on_message(self, msg: Dict):
    """
    WebSocket消息回调处理

    Hyperliquid数据格式:
    {
      "channel": "candle",
      "data": {
        "t": 1704067260000,  # 开盘时间（毫秒）
        "s": "ETH",          # 币种符号
        "i": "1m",           # 时间周期
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

        # 放入缓冲队列（非阻塞）
        try:
            self.kline_buffer.put_nowait(kline)
        except queue.Full:
            logger.warning(f"缓冲队列已满，丢弃K线 | {kline['symbol']}")

    except Exception as e:
        logger.error(f"消息处理失败: {e}", exc_info=True)
```

---

### 方法2: _batch_writer() - 异步批量写入线程

```python
def _batch_writer(self):
    """
    异步批量写入线程

    策略:
    - 累积1000-2000条记录后批量写入
    - 或者5秒超时后强制写入（避免数据积压）
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

### 方法3: _monitor_new_symbols() - 新币种监控线程

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

### 方法4: _get_all_symbols_from_exchange() - 动态币种发现

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

### 方法5: start() - 启动服务

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

## 📊 性能预期

| 指标 | 目标值 | 说明 |
|------|--------|------|
| **WebSocket延迟** | <500ms | K线闭合后推送延迟 |
| **写入吞吐量** | >1000条/秒 | COPY命令批量写入 |
| **数据完整性** | >95% | 无丢失K线 |
| **内存占用** | <512MB | 实时服务进程 |
| **CPU占用** | <50% | 单核利用率 |
| **连续运行时间** | >24小时 | 无崩溃 |

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

## ✅ 验收标准

- [ ] WebSocket成功连接Hyperliquid
- [ ] 订阅的所有币种都能接收到K线推送
- [ ] K线数据正确写入TimescaleDB
- [ ] 批量写入性能>500条/次
- [ ] 断线后自动重连成功
- [ ] 数据库中的K线时间戳连续（覆盖率>95%）
- [ ] 服务运行24小时无崩溃
- [ ] 内存占用稳定在512MB以内
- [ ] 新币种监控线程正常工作

## 📝 下一步

模块3为可选增强功能，完成后可以：
- 实现实时套利信号检测（enable_realtime_analysis=True）
- 添加飞书实时告警
- 集成到模块4的分析引擎中

---

**版本**: v1.0
**日期**: 2025-01-11
**优先级**: P1（可选）
**作者**: Claude Sonnet 4.5
