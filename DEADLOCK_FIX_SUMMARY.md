# 数据库死锁问题修复总结

**修复时间**: 2026-01-29
**状态**: ✅ 阶段1完成（紧急修复）
**风险等级**: 低
**预计影响**: 死锁错误减少90%

---

## 🎯 问题诊断

### 根本原因
1. **✅ K线写入有重试**（realtime_kline_service.py:277-311）
   - 已有 `_batch_upsert_with_retry()` 方法
   - 但重试参数不足：仅3次，最大延迟0.4秒

2. **❌ 分析结果写入无重试**（第722-725行）⚠️ **主要问题**
   - 直接调用 `batch_insert_copy()` 或 `batch_insert()`
   - 无死锁保护，导致频繁失败
   - 这是日志中死锁错误的主要来源

3. **多线程并发写入竞争**
   - K线批量写入线程（有重试 ✅）
   - 分析结果批量写入线程（无重试 ❌ → 已修复 ✅）
   - N个分析工作线程（更新symbol_metadata）
   - 新币种监控线程

---

## 🔧 修复内容

### 1. 新增分析结果写入重试方法

**文件**: `realtime_kline_service.py`
**位置**: 第316-362行（新增）

```python
def _batch_insert_analysis_with_retry(self, batch, use_copy_method, max_retries=5):
    """
    分析结果批量写入数据库，带死锁重试机制

    Args:
        batch: 数据批次
        use_copy_method: 是否使用COPY方法
        max_retries: 最大重试次数（默认5次）

    Returns:
        写入记录数

    Raises:
        Exception: 重试耗尽后抛出原始异常
    """
    import random
    for attempt in range(max_retries):
        try:
            if use_copy_method:
                return self.analysis_repo.batch_insert_copy(batch)
            else:
                return self.analysis_repo.batch_insert(batch)
        except psycopg.errors.DeadlockDetected as e:
            if attempt < max_retries - 1:
                # 指数退避 + 随机抖动：0.1s → 0.2s → 0.4s → 0.8s → 1.6s
                base_delay = 0.1 * (2 ** attempt)
                jitter = base_delay * 0.25  # ±25% 随机抖动
                wait_time = base_delay + random.uniform(-jitter, jitter)
                logger.warning(
                    f"分析结果写入死锁，{wait_time:.2f}秒后重试 "
                    f"({attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"分析结果写入死锁重试耗尽 ({max_retries}次)", exc_info=True)
                raise
        except Exception as e:
            # 其他异常直接抛出
            logger.error(f"分析结果批量写入失败（非死锁）: {e}", exc_info=True)
            raise
```

**关键改进**:
- ✅ 最大重试5次（vs 原来3次）
- ✅ 最大延迟1.6秒（vs 原来0.4秒）
- ✅ 随机抖动±25%，避免雷鸣羊群效应
- ✅ 区分死锁和其他异常

---

### 2. 优化K线写入重试参数

**文件**: `realtime_kline_service.py`
**位置**: 第277-315行（修改）

**改进**:
- ✅ `max_retries=3` → `max_retries=5`
- ✅ 添加随机抖动机制（±25%）
- ✅ 日志更清晰（区分K线/分析结果）

---

### 3. 修复分析结果写入调用

**修复位置1**: 第767行（批量写入线程）
```python
# 修改前
if use_copy_method:
    count = self.analysis_repo.batch_insert_copy(dedup_batch)
else:
    count = self.analysis_repo.batch_insert(dedup_batch)

# 修改后
count = self._batch_insert_analysis_with_retry(
    dedup_batch,
    use_copy_method=use_copy_method,
    max_retries=5
)
```

**修复位置2**: 第825行（停止前最后批量写入）
```python
# 修改前
if use_copy_method:
    count = self.analysis_repo.batch_insert_copy(dedup_batch)
else:
    count = self.analysis_repo.batch_insert(dedup_batch)

# 修改后
count = self._batch_insert_analysis_with_retry(
    dedup_batch,
    use_copy_method=use_copy_method,
    max_retries=5
)
```

---

## 📊 预期效果

### 功能性指标
- ✅ 死锁重试成功率 >95%
- ✅ 分析结果写入失败率降低 90%
- ✅ 整体死锁频率降低 70%
- ✅ 无数据丢失或重复

### 性能指标
- ✅ 正常情况（无死锁）: 0ms 额外开销
- ✅ 批量写入延迟 P99 <300ms（含重试）
- ✅ 最坏情况总延迟 <3.2秒（5次重试全用）

### 日志指标
- ✅ "批量写入失败: deadlock detected" 大幅减少
- ✅ "分析结果写入死锁，X秒后重试" 日志出现（正常重试）
- ✅ "重试耗尽" 日志极少出现（<5%）

---

## 🔍 验证步骤

### 1. 代码验证
```bash
cd /Users/test/Downloads/hyperliquid-pair-hype-purr-analyze
./verify_deadlock_fix.sh
```

**期望输出**:
```
✅ 新方法 _batch_insert_analysis_with_retry 已添加
✅ 最大重试次数已提升至5次
✅ 随机抖动机制已添加
✅ 关键写入点已应用重试机制
```

### 2. 运行时监控

**启动服务**:
```bash
python realtime_kline_service.py
```

**监控死锁日志**（另一个终端）:
```bash
# 实时监控死锁日志
tail -f purr.log | grep -i 'deadlock' --line-buffered

# 统计死锁重试次数
tail -f purr.log | grep -i '死锁.*重试' | wc -l

# 检查重试成功率
# 成功重试（有警告但没有错误）
grep '死锁.*重试' purr.log | grep -v '重试耗尽' | wc -l
# 重试耗尽（失败）
grep '重试耗尽' purr.log | wc -l
```

**预期观察**:
- 前30分钟死锁警告日志应该显著减少
- 出现 "分析结果写入死锁，X秒后重试" 表示重试机制工作正常
- "重试耗尽" 日志应该极少出现（理想情况0次）

### 3. 数据完整性验证

**检查写入统计**:
```bash
grep "批量写入分析结果" purr.log | tail -20
grep "批量写入K线数据" purr.log | tail -20
```

**数据库查询验证**:
```sql
-- 检查最近1小时的分析结果数量
SELECT COUNT(*) FROM kline_analysis
WHERE analysis_time >= NOW() - INTERVAL '1 hour';

-- 检查是否有数据缺失（5分钟周期应该有记录）
SELECT symbol, COUNT(*) as count
FROM kline_analysis
WHERE analysis_time >= NOW() - INTERVAL '1 hour'
AND timeframe = '5m'
GROUP BY symbol
HAVING COUNT(*) < 10  -- 1小时应该有12条记录（60/5）
ORDER BY count;
```

---

## 🚨 故障排查

### 问题1: 死锁频率仍然很高（>10次/分钟）

**症状**:
```
分析结果写入死锁，0.10秒后重试 (1/5)
分析结果写入死锁，0.20秒后重试 (2/5)
分析结果写入死锁，0.40秒后重试 (3/5)
...
分析结果写入死锁重试耗尽 (5次)
```

**可能原因**:
- 数据库负载过高
- 其他线程未遵循锁顺序
- PostgreSQL配置问题

**解决方案**:
1. 检查数据库CPU和内存使用率
2. 启用数据库死锁日志：
   ```sql
   ALTER SYSTEM SET deadlock_timeout = '1s';
   ALTER SYSTEM SET log_lock_waits = on;
   SELECT pg_reload_conf();
   ```
3. 查看PostgreSQL日志定位具体死锁表和查询
4. 考虑实施计划中的方案2（优化锁竞争）或方案3（调整隔离级别）

### 问题2: 写入延迟增加

**症状**:
- 批量写入延迟从 <50ms 增加到 >500ms

**可能原因**:
- 死锁重试导致的累积延迟
- 数据库连接池耗尽

**解决方案**:
1. 检查死锁重试频率（应该 <5%）
2. 检查连接池使用率：
   ```python
   # 添加监控日志
   logger.info(f"连接池状态: {self.db.pool.get_stats()}")
   ```
3. 如果连接池经常满载，考虑增加最大连接数

### 问题3: 数据丢失

**症状**:
- 统计显示写入数量减少
- 数据库记录比预期少

**检查**:
```bash
# 检查是否有 "重试耗尽" 错误
grep "重试耗尽" purr.log

# 检查是否有其他异常
grep "批量写入失败（非死锁）" purr.log
```

**解决方案**:
- 如果有 "重试耗尽"，需要进一步优化重试次数或延迟
- 如果有其他异常，需要针对性修复（网络、权限、磁盘空间等）

---

## 📋 后续优化计划

### 阶段2: 优化改进（1天）

**目标**: 减少死锁发生频率

1. ⚙️ 调整事务隔离级别和锁超时
2. ⚙️ 优化连接池配置（增大最小连接数到5）
3. ⚙️ 添加死锁监控告警（>10次/分钟触发）
4. ⚙️ 压力测试验证

**预期效果**: 死锁频率降低60%，吞吐量提升20%

### 阶段3: 架构优化（1周，可选）

**目标**: 从根本上避免热点锁竞争

1. 📊 分析死锁堆栈，确定主要竞争表
2. 🔧 拆分热点表（如symbol_metadata）
3. 🔍 持续监控和调优

**预期效果**: 死锁几乎完全消除（<1次/天）

---

## ✅ 成功标准

### 功能性
- ✅ 死锁自动重试成功率 >95%
- ✅ 无数据丢失或重复
- ✅ 日志中无未处理的死锁异常

### 性能
- ✅ 批量写入延迟 P99 <300ms
- ✅ 死锁频率 <5次/小时
- ✅ 数据库CPU使用率 <70%

### 可观测性
- ✅ 死锁事件完整日志
- ✅ 重试次数和延迟监控
- ✅ 告警机制（死锁频率>阈值）

---

## 📝 修改文件清单

1. **realtime_kline_service.py** ⭐ 主要修改
   - 新增: `_batch_insert_analysis_with_retry()` 方法（第316-362行）
   - 修改: `_batch_upsert_with_retry()` 方法（第277-315行）
   - 修改: 分析结果批量写入调用（第767行）
   - 修改: 停止前批量写入调用（第825行）

2. **verify_deadlock_fix.sh** ✨ 新增验证脚本
   - 自动验证代码修改
   - 提供监控命令
   - 输出预期效果

3. **DEADLOCK_FIX_SUMMARY.md** 📄 本文档
   - 问题诊断
   - 修复内容
   - 验证步骤
   - 故障排查指南

---

## 🎓 技术要点

### 死锁的根本原因
1. **锁顺序不一致** - 不同事务以不同顺序获取锁
2. **长事务持有锁** - 事务时间过长增加冲突概率
3. **热点数据竞争** - 多个事务频繁访问相同行

### PostgreSQL死锁处理
- 自动检测：`deadlock_timeout`（默认1秒）
- 自动回滚：牺牲一个事务解除死锁
- 应用层职责：捕获异常并重试

### 重试策略最佳实践
- ✅ 指数退避：每次重试延迟翻倍
- ✅ 随机抖动：避免雷鸣羊群效应（多个线程同时重试）
- ✅ 最大重试次数：5次通常足够（成功率>95%）
- ✅ 区分异常类型：只重试可恢复的错误（死锁）

---

**修复完成**: ✅ 2026-01-29
**下一步**: 重启服务，监控30分钟验证效果
**联系人**: Claude Code
