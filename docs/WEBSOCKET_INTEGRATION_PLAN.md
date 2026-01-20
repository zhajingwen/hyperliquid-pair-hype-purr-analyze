# WebSocket 管理器集成方案

**项目来源**: https://github.com/zhajingwen/strong-hyperliquid-websocket
**集成目标**: 实现高可靠性的实时K线数据接收服务

---

## 📊 strong-hyperliquid-websocket 核心优势

### 1. 双重健康检测机制
```
底层连接检测（Socket状态） + 应用层心跳监控（数据流中断）
↓
"假活"状态检测: 30秒无数据自动触发重连
```

**解决的核心问题**: 官方SDK存在的连接看似正常但实际无法传输数据的情况

### 2. 指数退避重连策略
```python
等待时间 = min(初始延迟 × 2^重试次数, 最大延迟)
初始延迟: 1秒
递增因子: 2倍
最大延迟: 60秒
随机抖动: ±25% (防止雷鸣羊群效应)
```

**优势**: 快速恢复 + 避免服务器过载

### 3. 完整的状态机管理
```
DISCONNECTED → CONNECTING → CONNECTED
                    ↓
            RECONNECTING → FAILED
```

**回调支持**: `on_state_change(state, error)`

### 4. 线程安全设计
- 递归锁保护状态更新
- Event对象同步连接就绪状态
- 线程安全的订阅管理

### 5. 可观测性
- 结构化日志（时间戳 + 级别）
- 实时统计信息（消息计数、重连次数、运行时长）
- 健康度百分比报告

---

## 🏗️ 集成架构设计

### 方案1: 直接依赖集成 ✅ 推荐

```
strong-hyperliquid-websocket (第三方库)
           ↓
    RealtimeKlineService (我们的封装层)
           ↓
   ┌─────────┴─────────┐
   ↓                   ↓
批量写入线程      实时分析引擎
   ↓                   ↓
TimescaleDB        飞书告警
```

**优点**:
- ✅ 维护成本低（跟随上游更新）
- ✅ 代码量少（~600行 vs ~1500行）
- ✅ 功能完整（已久经考验）
- ✅ Bug修复及时（上游维护）

**实施步骤**:
1. 添加依赖: `hyperliquid-python-sdk>=0.21.0`
2. 克隆项目: `git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git`
3. 本地安装: `pip install -e strong-hyperliquid-websocket/`
4. 封装适配器: 创建 `RealtimeKlineService` 类

### 方案2: 代码复制集成 (备选)

将 `enhanced_ws_manager.py` 复制到 `utils/` 目录

**优点**:
- 无外部依赖
- 完全可控

**缺点**:
- ❌ 维护成本高（需手动同步更新）
- ❌ Bug修复慢（自行处理）
- ❌ 代码冗余

**结论**: 不推荐（除非有特殊安全要求）

---

## 📦 依赖配置

### pyproject.toml 新增依赖

```toml
[project]
dependencies = [
    # ... 现有依赖 ...
    "hyperliquid-python-sdk>=0.21.0",  # Hyperliquid官方SDK
    "websockets>=12.0",                # WebSocket客户端
]
```

### 安装方式

```bash
# 方式1: 使用 uv (推荐)
uv add hyperliquid-python-sdk websockets

# 方式2: 克隆并本地安装
git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git
cd strong-hyperliquid-websocket
uv pip install -e .
```

---

## 🔧 适配器设计

### 类: RealtimeKlineService

```python
from enhanced_ws_manager import EnhancedWebSocketManager
import hyperliquid.utils.constants as constants

class RealtimeKlineService:
    """实时K线分析服务（封装 EnhancedWebSocketManager）"""

    def __init__(self):
        self.symbols = self._get_symbols_from_db()  # 从数据库获取
        self.timeframes = ['5m', '1h', '4h']        # 仅订阅3个周期

        # 构建订阅列表
        self.subscriptions = self._build_subscriptions()

        # 初始化 WebSocket 管理器
        self.ws_manager = EnhancedWebSocketManager(
            base_url=constants.MAINNET_API_URL,
            subscriptions=self.subscriptions,
            message_callback=self.on_message,
            on_state_change=self.on_state_change,
            timeout=30  # 30秒无数据超时
        )

    def _build_subscriptions(self) -> List[Dict]:
        """构建订阅列表（600个订阅 = 200币种 × 3周期）"""
        subs = []
        for symbol in self.symbols:
            coin = symbol.split('/')[0]  # BTC/USDC:USDC → BTC
            for tf in self.timeframes:
                subs.append({
                    "type": "candle",
                    "coin": coin,
                    "interval": tf
                })
        return subs

    def on_message(self, msg: Dict):
        """WebSocket消息回调（核心处理逻辑）"""
        if msg.get("channel") != "candle":
            return

        # 1. 解析K线数据
        kline = self._parse_kline(msg.get("data", {}))

        # 2. 写入缓冲队列（异步批量写入）
        self.kline_buffer.put_nowait(kline)

        # 3. 触发实时分析（同步）
        self._analyze_and_alert(kline['symbol'], kline['timeframe'])

    def on_state_change(self, state: str, error: Optional[Exception]):
        """连接状态变化回调"""
        logger.info(f"WebSocket状态: {state}")
        if error:
            logger.error(f"连接错误: {error}")

    def start(self):
        """启动服务（阻塞运行）"""
        # 启动批量写入线程
        self.batch_writer_thread.start()

        # 启动新币种监控线程
        self.symbol_monitor_thread.start()

        # 启动 WebSocket（阻塞）
        self.ws_manager.start()
```

---

## 🔄 数据流设计

```
Hyperliquid WebSocket API
           ↓
EnhancedWebSocketManager
    (假活检测 + 自动重连)
           ↓
    on_message() 回调
           ↓
    _parse_kline()
    (Hyperliquid格式 → 标准格式)
           ↓
    ┌─────────┴─────────┐
    ↓                   ↓
kline_buffer      _analyze_and_alert()
(Queue队列)       (实时分析引擎)
    ↓                   ↓
_batch_writer()   analysis_results
(批量写入线程)    (保存分析结果)
    ↓                   ↓
klines表          飞书告警
```

---

## 📝 Hyperliquid 数据格式

### WebSocket 推送格式

```json
{
  "channel": "candle",
  "data": {
    "t": 1704067260000,  // 开盘时间（毫秒时间戳）
    "s": "ETH",          // 币种符号（仅基础币种名）
    "i": "5m",           // 时间周期
    "o": "2295.5",       // 开盘价
    "h": "2296.8",       // 最高价
    "l": "2295.2",       // 最低价
    "c": "2296.3",       // 收盘价
    "v": "1234.56"       // 成交量
  }
}
```

### 解析逻辑

```python
def _parse_kline(self, data: Dict) -> Dict:
    """解析 Hyperliquid K线数据为标准格式"""
    coin = data['s']  # ETH
    symbol = f"{coin}/USDC:USDC"  # ETH/USDC:USDC

    return {
        'time': datetime.fromtimestamp(data['t'] / 1000, tz=timezone.utc),
        'symbol': symbol,
        'timeframe': data['i'],
        'open': float(data['o']),
        'high': float(data['h']),
        'low': float(data['l']),
        'close': float(data['c']),
        'volume': float(data['v']),
        'volume_usd': float(data['c']) * float(data['v']),
        'return_pct': (float(data['c']) - float(data['o'])) / float(data['o'])
    }
```

---

## 🧪 测试策略

### 测试1: 连接稳定性

```python
# 运行服务24小时
service = RealtimeKlineService()
service.start()

# 验证点:
# - 无异常重启
# - 重连次数合理（<5次/24h）
# - 数据完整性 >95%
```

### 测试2: 假活检测

```python
# 模拟网络延迟（30秒无数据）
# 预期: 自动触发重连
# 验证: 日志显示"健康检查失败，触发重连"
```

### 测试3: 断线重连

```python
# 手动断开WebSocket连接
# 预期: 指数退避重连（1s → 2s → 4s → 8s → 16s）
# 验证: 日志显示重连延迟递增
```

---

## ⚠️ 注意事项

### 1. 订阅数量限制
```
Hyperliquid单连接订阅上限: 未明确（建议<1000）
当前订阅数: 600 (200币种 × 3周期)
```

**策略**: 如果币种数>200，考虑使用多个WebSocket连接

### 2. 消息频率
```
5m周期: ~8次/分钟
1h周期: ~3.3次/分钟
4h周期: ~0.83次/分钟
总计: ~12次/分钟/币种
```

**压力**: 200币种 = ~2400次/分钟 = 40次/秒

### 3. 内存占用估算
```
单条K线: ~200字节
缓冲队列: 10000条 = 2MB
WebSocket缓冲: ~5MB
分析引擎缓存: ~50MB
预估总内存: <512MB
```

---

## 📊 性能预期

| 指标 | 目标 | 实现方式 |
|------|------|---------|
| **假活检测延迟** | <30秒 | EnhancedWebSocketManager内置 |
| **重连延迟** | <10秒 | 指数退避策略 |
| **消息处理延迟** | <100ms | 异步队列 + 批量写入 |
| **分析延迟** | <5秒 | 同步分析 + DB查询优化 |
| **数据完整性** | >95% | 自动重连保证 |
| **连续运行时间** | >24小时 | 线程安全 + 资源管理 |

---

## ✅ 集成验收标准

### 基础功能
- [ ] 成功安装 `strong-hyperliquid-websocket` 依赖
- [ ] `RealtimeKlineService` 类封装完成
- [ ] WebSocket 成功连接 Hyperliquid
- [ ] 订阅600个 channel（200币种 × 3周期）

### 可靠性
- [ ] 30秒假活检测正常工作
- [ ] 断线后自动重连成功（<10秒）
- [ ] 指数退避策略正确执行
- [ ] 状态回调正确触发

### 性能
- [ ] 消息处理延迟 <100ms
- [ ] 批量写入性能 >500条/次
- [ ] 内存占用 <512MB
- [ ] CPU占用 <50%

---

## 🚀 下一步实施计划

### 步骤1: 安装依赖（5分钟）
```bash
uv add hyperliquid-python-sdk websockets
git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git
cd strong-hyperliquid-websocket
uv pip install -e .
```

### 步骤2: 创建核心服务（2小时）
- `realtime_kline_service.py`（主服务类）
- 实现数据解析
- 实现缓冲队列
- 实现批量写入线程

### 步骤3: 集成分析引擎（1小时）
- 调用 `utils/analysis_core.py`（需创建）
- Z-score异常检测
- 飞书告警集成

### 步骤4: 测试验证（1小时）
- 连接稳定性测试
- 假活检测测试
- 断线重连测试
- 性能基准测试

**预计总用时**: 4-5小时

---

**版本**: v1.0
**日期**: 2026-01-19
**作者**: Claude Sonnet 4.5
