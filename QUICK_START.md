# 🚀 快速开始指南 - Phase 2.5 数据库兼容性修复

## ✅ 已完成工作

### Phase 2.5: 数据库兼容性修复 ✅
- ✅ 修复 `realtime_kline_service.py` 的 `analysis_record` 字段
- ✅ 删除不存在的字段：`trigger_timeframe`, `cointegration_count`
- ✅ 添加必需字段：`corr_5m_7d`, `corr_1h_30d`, `corr_4h_60d`, `cointegration_passed`, `adf_pvalue`
- ✅ 创建验证脚本：`scripts/validate_database_schema.sql`
- ✅ 创建总结文档：`PHASE_2_5_SUMMARY.md`

**修改文件**：
- `realtime_kline_service.py` (line 841-868)

---

## 🎯 立即执行步骤

### 步骤1: 启动实时服务（验证数据库写入）

```bash
# 激活虚拟环境（如果有）
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 启动实时服务
python realtime_kline_service.py
```

**观察日志**：
```
🔗 WebSocket连接成功
📊 订阅K线更新: ['BTCUSDT', 'ETHUSDT', ...]
✅ 多周期验证通过: BTCUSDT @ 5m | 2.34秒
📢 多周期告警已发送: BTCUSDT @ 5m | long | Z-score: 1.85/1.67/0.25
```

**注意事项**：
- ⏳ 信号触发可能需要几分钟到几小时（取决于市场行情）
- ⚠️ 如果长时间无信号，可以：
  - 检查飞书Webhook配置（`utils/config.py`）
  - 调低Z-score阈值（临时测试用）
  - 查看 `multi_coins.py` 批量分析结果（验证配对有效性）

---

### 步骤2: 验证数据库写入（信号触发后）

**方法A：使用验证脚本**（推荐）
```bash
# 进入数据库容器
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

# 执行验证脚本（在容器内）
\i /path/to/scripts/validate_database_schema.sql

# 或从宿主机执行
docker exec -i crypto_timescaledb psql -U postgres -d crypto_data < scripts/validate_database_schema.sql
```

**方法B：手动SQL查询**
```sql
-- 查看最近1小时的记录
SELECT
    analysis_time,
    symbol,
    corr_5m_7d, corr_1h_30d, corr_4h_60d,  -- 应为NULL
    zscore_5m, zscore_1h, zscore_4h,      -- 应有值
    cointegration_passed, adf_pvalue,     -- passed=布尔值, p_value=NULL
    is_anomaly, trading_direction, signal_strength
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 hour'
ORDER BY analysis_time DESC
LIMIT 5;
```

**预期结果**：
| 字段 | 预期值 | 说明 |
|------|--------|------|
| `corr_5m_7d` | `NULL` | 多周期验证不计算相关系数 |
| `corr_1h_30d` | `NULL` | 同上 |
| `corr_4h_60d` | `NULL` | 同上 |
| `zscore_5m` | 有值（如 `1.85`） | 短周期Z-score |
| `zscore_1h` | 有值（如 `1.67`） | 中周期Z-score |
| `zscore_4h` | 有值（如 `0.25`） | 长周期Z-score |
| `cointegration_passed` | `TRUE` / `FALSE` | 基于协整通过数 >= 2 |
| `adf_pvalue` | `NULL` | 多周期验证无单一p值 |
| `is_anomaly` | `TRUE` | 固定为TRUE（通过验证才写入） |
| `trading_direction` | `'long'` / `'short'` | 交易方向 |
| `signal_strength` | `'strong'` | 固定为strong |

---

### 步骤3: 检查飞书告警（验证业务逻辑）

**预期告警格式**：
```
📈 多周期配对交易信号 🔥

币种: BTCUSDT
触发周期: 5m
基准: ETHUSDT

---

多周期Z-score验证 ✅:
- 🕐 短周期 (5m): +1.85 ✅
- 🕑 中周期 (1h): +1.67 ✅
- 🕓 长周期 (4h): +0.25 ✅

协整检验统计:
- 通过数量: 5/6
- 符号一致性: ✅ 全正

交易方向: LONG
信号强度: STRONG（多周期确认）

时间: 2026-01-23 12:34:56 UTC

---
💡 说明: 此信号已通过3个周期的协整检验和Z-score验证，信号质量高。
```

**关键验证点**：
- ✅ 展示3个周期的Z-score（5m, 1h, 4h）
- ✅ 展示协整通过数量（x/6）
- ✅ 展示触发周期（但不持久化到数据库）

---

## ⚠️ 常见问题排查

### 问题1: 数据库写入失败

**症状**：
```
ERROR: column "trigger_timeframe" of relation "analysis_results" does not exist
```

**解决方案**：
- ✅ 已修复：确认 `realtime_kline_service.py` (line 841-868) 代码已更新
- 重启服务：`python realtime_kline_service.py`

### 问题2: 长时间无信号触发

**可能原因**：
1. 市场行情不满足多周期验证条件
2. Z-score阈值过高（长周期0.2, 中周期1.5, 短周期1.8）
3. 协整检验通过数量不足（需要 >= 2）

**临时解决方案**（仅测试用）：
```python
# realtime_kline_service.py (约 line 820)
# 临时调低阈值
multi_period_result = analyze_multi_period(
    price_data_cache=price_data_cache,
    beta_window=100,
    zscore_window=30,
    cointegration_threshold=1,  # 临时改为1（原为2）
    zscore_thresholds={
        'long': 0.1,    # 临时改为0.1（原为0.2）
        'middle': 1.0,  # 临时改为1.0（原为1.5）
        'short': 1.2    # 临时改为1.2（原为1.8）
    }
)
```

**⚠️ 警告**：调低阈值会增加假阳性信号，仅用于验证数据库写入功能，测试完成后恢复原值。

### 问题3: 性能延迟过高

**症状**：
```
⚠️ 多周期分析延迟过高: BTCUSDT | 18.50秒 > 15秒
```

**说明**：
- 多周期验证需要查询3个周期数据（5m/7d, 1h/30d, 4h/60d）
- 计算量约为单周期的3倍
- 允许延迟 <15秒

**优化方案**（如确实影响体验）：
1. 异步多周期验证（不阻塞WebSocket消息处理）
2. 缓存协整参数（避免重复计算相同币种）
3. 仅在特定周期（4h）启用健康监控

---

## 📋 后续任务清单

查看完整任务列表：
```bash
# 查看所有任务
/tasks
```

**任务优先级**：
1. ⏳ **Task #1**: Phase 2.5 数据库兼容性验证（立即执行）
2. 📝 **Task #2**: Phase 4 单元测试编写（建议完成）
3. 📊 **Task #3**: Phase 4 性能监控测试（建议完成）
4. 📚 **Task #4**: Phase 5 文档更新（可选）

---

## 📎 相关文档

- **修复总结**：`PHASE_2_5_SUMMARY.md`
- **验证脚本**：`scripts/validate_database_schema.sql`
- **实施计划**：`IMPLEMENTATION_SUMMARY.md`
- **数据库表定义**：`init_timescaledb.sql`

---

## 🎯 成功标准

- ✅ 实时服务正常启动，无错误日志
- ✅ 触发信号时，数据成功写入 `analysis_results` 表
- ✅ 所有字段值符合预期（参考上述表格）
- ✅ 飞书告警正常发送，展示3个周期Z-score
- ✅ 分析延迟 <15秒

---

**准备好了吗？开始执行步骤1！** 🚀
