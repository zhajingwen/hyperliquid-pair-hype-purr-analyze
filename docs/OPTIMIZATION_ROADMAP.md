# 性能优化路线图 (Performance Optimization Roadmap)


## 🚀 Phase 2: 全异步架构（规划中）

### 目标

采用asyncio实现全异步数据流，突破线程模型的性能瓶颈，达到毫秒级告警延迟。

### 触发条件（满足任一即可触发）

- ✅ Phase 1.5后分析延迟仍 >2秒（P95）
- ✅ 需要支持 >500币种
- ✅ 需要毫秒级告警延迟
- ✅ 数据库查询成为明显瓶颈

### 核心技术栈

```python
# 核心依赖
asyncio           # Python内置异步框架
asyncpg >= 0.29.0 # PostgreSQL异步驱动（替代psycopg）
aiohttp >= 3.9.0  # 异步HTTP客户端（替代requests）
```

### 架构设计

#### 2.1 异步WebSocket处理

**改动前**（线程模型）:
```python
def on_message(self, msg: Dict):
    kline = self._parse_kline(msg)
    self.kline_buffer.put_nowait(kline)      # 入队
    self.analysis_queue.put_nowait(task)     # 入队
```

**改动后**（协程模型）:
```python
async def on_message(self, msg: Dict):
    kline = self._parse_kline(msg)

    # 并发写入和分析（asyncio.gather）
    await asyncio.gather(
        self._async_write_kline(kline),
        self._async_analyze(kline['symbol'], kline['timeframe'])
    )
```

#### 2.2 异步数据库查询

**改动前**（同步查询，200-500ms）:
```python
# 串行查询
base_klines = self.kline_repo.query_range(...)  # 100-200ms
alt_klines = self.kline_repo.query_range(...)   # 100-200ms
# 总耗时: 200-400ms
```

**改动后**（并发查询，50-100ms）:
```python
async with self.db_pool.acquire() as conn:
    # 并发查询（asyncio.gather）
    base_task = conn.fetch("SELECT * FROM klines WHERE ...")
    alt_task = conn.fetch("SELECT * FROM klines WHERE ...")
    base_klines, alt_klines = await asyncio.gather(base_task, alt_task)
# 总耗时: 50-100ms（3-5倍提升）
```

#### 2.3 协程池管理

```python
class AsyncRealtimeKlineService:
    def __init__(self):
        # 异步数据库连接池
        self.db_pool = await asyncpg.create_pool(
            dsn=DB_URL,
            min_size=10,
            max_size=50,
            command_timeout=10
        )

        # 协程任务池（100个并发分析）
        self.analysis_semaphore = asyncio.Semaphore(100)

    async def _async_analyze(self, symbol: str, timeframe: str):
        async with self.analysis_semaphore:
            # 限制并发数，避免资源耗尽
            result = await self._analyze_pair(symbol, timeframe)

            if result['is_anomaly']:
                # 并发告警和持久化
                await asyncio.gather(
                    self._async_send_alert(result),
                    self._async_save_result(result)
                )
```

#### 2.4 CPU密集计算处理

```python
# CPU密集的统计分析在线程池执行
loop = asyncio.get_event_loop()
analysis_result = await loop.run_in_executor(
    None,  # 使用默认线程池
    analyze_pair,  # CPU密集函数
    base_klines,
    alt_klines
)
```

### 性能预期

| 指标 | Phase 1.5 | Phase 2 | 改善 |
|------|-----------|---------|------|
| 分析延迟（P95） | <5秒 | <1秒 | 80%↓ |
| 数据库查询 | 200-500ms | 50-100ms | 3-5倍↑ |
| 吞吐量 | 2.5次/秒 | >5000次/秒 | >2000倍↑ |
| CPU占用 | 20-30% | 25-35% | 略升 |
| 内存占用 | <512MB | <1GB | 略升 |
| 并发分析任务 | 5-6个线程 | 100个协程 | 17倍↑ |

### 实施计划

#### 第1步: 异步数据库层（4小时）

**文件**: `utils/async_timescaledb.py`

**核心类**:
```python
class AsyncTimescaleDBClient:
    """异步数据库客户端（单例）"""

class AsyncKlineRepository:
    """异步K线数据仓库"""
    async def query_range(...) -> List[Dict]
    async def batch_upsert(...) -> int

class AsyncAnalysisResultRepository:
    """异步分析结果仓库"""
    async def batch_insert(...) -> int
```

**验收标准**:
- [ ] 所有数据库操作支持async/await
- [ ] 查询性能提升3-5倍（200ms → 50-100ms）
- [ ] 并发查询无死锁或连接泄漏

---

#### 第2步: 异步分析引擎（6小时）

**文件**: `async_realtime_kline_service.py`

**核心改动**:
- WebSocket消息处理改为async
- 分析流程全异步化
- 协程池管理（限制并发数）
- CPU密集计算在线程池执行

**验收标准**:
- [ ] 分析延迟 <1秒（P95）
- [ ] 吞吐量 >1000次/秒
- [ ] 内存占用稳定 <1GB
- [ ] 无协程泄漏或死锁

---

#### 第3步: 异步告警系统（2小时）

**文件**: `utils/async_lark_bot.py`

**核心功能**:
```python
async def async_send_alert(url: str, content: str, title: str):
    """异步发送飞书告警"""
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()
```

**验收标准**:
- [ ] 告警发送延迟 <100ms
- [ ] 支持批量并发告警
- [ ] 错误重试机制

---

#### 第4步: 集成测试与性能调优（2-4小时）

**测试场景**:
1. 单币种压测（1000次/秒）
2. 多币种压测（500币种 × 3周期）
3. 峰值负载测试（2倍正常流量）
4. 稳定性测试（连续24小时）

**调优重点**:
- asyncpg连接池大小
- 协程并发数
- 数据库查询超时
- 内存占用优化

### 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 大规模代码重构 | 高 | 保留原有线程版本，灰度切换 |
| asyncio学习曲线 | 中 | 参考成熟开源项目，充分测试 |
| 协程泄漏/死锁 | 中 | 使用asyncio.timeout，监控任务队列 |
| 第三方库兼容性 | 低 | asyncpg和aiohttp成熟稳定 |
| 性能不及预期 | 低 | 基于asyncpg的成功案例多 |

### 实施文档

- [Phase 2详细设计文档](./PHASE_2_ASYNC_ARCHITECTURE.md)（待创建）
- [asyncio最佳实践](./ASYNCIO_BEST_PRACTICES.md)（待创建）
- 预计实施时间: 12-16小时
- 风险等级: 中等
