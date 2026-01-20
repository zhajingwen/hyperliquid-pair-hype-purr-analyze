# Phase 1.5 快速启动指南

**版本**: v1.0
**实施日期**: 2026-01-20

---

## 🚀 快速开始

Phase 1.5 性能优化已实施完成，以下是验证步骤：

### 步骤1: 配置环境变量（可选）

编辑 `.env` 文件，添加或修改：

```bash
# 分析工作线程数（默认5个）
ANALYSIS_WORKERS=5
```

**推荐值**:
- 4核CPU: `ANALYSIS_WORKERS=4`
- 6核CPU: `ANALYSIS_WORKERS=6`
- 8核CPU: `ANALYSIS_WORKERS=8`

---

### 步骤2: 启动服务

```bash
cd /Users/test/Downloads/hyperliquid-pair-hype-purr-analyze
uv run python realtime_kline_service.py
```

**预期日志输出**:
```
INFO - ✅ 启动5个分析工作线程（ANALYSIS_WORKERS=5）
INFO - [analysis-worker-0] 分析工作线程已启动
INFO - [analysis-worker-1] 分析工作线程已启动
INFO - [analysis-worker-2] 分析工作线程已启动
INFO - [analysis-worker-3] 分析工作线程已启动
INFO - [analysis-worker-4] 分析工作线程已启动
INFO - ✅ 批量写入线程已启动
INFO - ✅ 新币种监控线程已启动
INFO - WebSocket 状态: connecting
INFO - WebSocket 状态: connected
```

---

### 步骤3: 验证差异化去重策略（可选）

在另一个终端窗口，观察分析日志：

```bash
# 实时查看分析日志
tail -f logs/service.log | grep -E "(分析完成|跳过重复分析)"
```

**预期输出示例**:
```
# 5m周期（约每60-120秒）
DEBUG - 分析完成: ETH/USDC:USDC @ 5m | 去重窗口: 60秒 | 距上次: 0秒
DEBUG - 跳过重复分析: ETH/USDC:USDC @ 5m (距上次 35秒，窗口 60秒)
DEBUG - 分析完成: ETH/USDC:USDC @ 5m | 去重窗口: 60秒 | 距上次: 95秒

# 1h周期（约每5-10分钟）
DEBUG - 分析完成: BTC/USDC:USDC @ 1h | 去重窗口: 300秒 | 距上次: 0秒
DEBUG - 跳过重复分析: BTC/USDC:USDC @ 1h (距上次 120秒，窗口 300秒)
DEBUG - 分析完成: BTC/USDC:USDC @ 1h | 去重窗口: 300秒 | 距上次: 420秒

# 4h周期（约每15-30分钟）
DEBUG - 分析完成: SOL/USDC:USDC @ 4h | 去重窗口: 900秒 | 距上次: 0秒
DEBUG - 跳过重复分析: SOL/USDC:USDC @ 4h (距上次 600秒，窗口 900秒)
DEBUG - 分析完成: SOL/USDC:USDC @ 4h | 去重窗口: 900秒 | 距上次: 1050秒
```

**验证指标**:
- ✅ 5m周期去重窗口: **60秒**
- ✅ 1h周期去重窗口: **300秒**（5分钟）
- ✅ 4h周期去重窗口: **900秒**（15分钟）

---

### 步骤4: 性能监控（可选）

启动性能监控脚本，观察CPU和内存占用：

```bash
uv run python scripts/monitor_performance.py
```

**预期输出**（每10秒）:
```
INFO - 📊 性能监控 | 消息: 74/10s (7.4/s) | 分析: 12/10s (1.2/s) | CPU: 25.3% | 内存: 256.8MB
INFO - 📊 性能监控 | 消息: 68/10s (6.8/s) | 分析: 15/10s (1.5/s) | CPU: 23.7% | 内存: 248.5MB
```

**目标性能**:
- CPU占用: **20-30%**（相比Phase 1的30-45%降低）
- 内存占用: **<512MB**
- 分析速率: **0.5-2.0次/秒**

---

## 📊 预期性能改善

| 指标 | Phase 1 | Phase 1.5 | 改善 |
|------|---------|-----------|------|
| 工作线程数 | 3个 | 5-6个 | 67-100%↑ |
| CPU占用 | 30-45% | 20-30% | 30%↓ |
| 容量余量 | 100% | 240% | 140%↑ |
| 不必要分析 | 基准 | 减少70-80% | 70-80%↓ |

---

## 🐛 常见问题

### Q1: 如何确认工作线程数生效？

查看启动日志：
```bash
grep "启动.*个分析工作线程" logs/service.log
```

应看到类似输出：
```
INFO - ✅ 启动5个分析工作线程（ANALYSIS_WORKERS=5）
```

---

### Q2: 如何调整工作线程数？

方法1（推荐）- 修改 `.env` 文件：
```bash
echo "ANALYSIS_WORKERS=6" >> .env
```

方法2 - 临时设置环境变量：
```bash
ANALYSIS_WORKERS=6 uv run python realtime_kline_service.py
```

---

### Q3: 如何验证差异化去重生效？

观察日志中不同周期的去重窗口：
```bash
grep "去重窗口" logs/service.log | tail -20
```

应看到：
- 5m周期显示 `去重窗口: 60秒`
- 1h周期显示 `去重窗口: 300秒`
- 4h周期显示 `去重窗口: 900秒`

---

## 📚 详细文档

更多信息请参考：
- [Phase 1.5实施报告](docs/PHASE_1.5_IMPLEMENTATION_REPORT.md) - 完整的技术细节和验收标准
- [性能优化计划](README.md) - Phase 1-3完整路线图

---

## ✅ 验收清单

运行1小时后，验证以下指标：

- [ ] 工作线程数: 5-6个（查看启动日志）
- [ ] CPU占用: 20-30%（运行监控脚本）
- [ ] 内存占用: <512MB（运行监控脚本）
- [ ] 5m周期分析间隔: 60-120秒（查看分析日志）
- [ ] 1h周期分析间隔: 5-10分钟（查看分析日志）
- [ ] 4h周期分析间隔: 15-30分钟（查看分析日志）
- [ ] 无异常崩溃或错误（查看服务日志）

---

**祝使用愉快！如有问题，请参考详细实施报告。**
