# 🚀 数据库死锁修复 - 快速开始指南

**修复完成**: ✅ 2026-01-29
**文件**: `realtime_kline_service.py` + `realtime_kline_service_hype.py`

---

## ⚡ 30秒快速部署

```bash
# 进入项目目录
cd /Users/test/Downloads/hyperliquid-pair-hype-purr-analyze

# 验证修复
./verify_deadlock_fix.sh
./verify_deadlock_fix_hype.sh

# 重启服务
pkill -f "realtime_kline_service.py$"
pkill -f realtime_kline_service_hype.py
python realtime_kline_service.py &
python realtime_kline_service_hype.py &

# 监控效果（推荐运行30分钟）
./monitor_deadlock.sh        # 主服务
./monitor_deadlock_hype.sh    # HYPE服务
```

---

## 📊 快速检查

### 查看死锁日志
```bash
# 主服务
tail -f purr.log | grep -i 'deadlock'

# HYPE服务
tail -f purr_hype.log | grep -i 'deadlock'
```

### 统计重试成功率
```bash
# 主服务
成功=$(grep "死锁.*重试" purr.log | grep -v "重试耗尽" | wc -l)
失败=$(grep "重试耗尽" purr.log | wc -l)
echo "主服务重试成功率: $((成功 * 100 / (成功 + 失败)))%"

# HYPE服务
成功=$(grep "死锁.*重试" purr_hype.log | grep -v "重试耗尽" | wc -l)
失败=$(grep "重试耗尽" purr_hype.log | wc -l)
echo "HYPE服务重试成功率: $((成功 * 100 / (成功 + 失败)))%"
```

---

## ✅ 成功标准

运行30分钟后，应该看到：

- ✅ 死锁重试成功率 >95%
- ✅ 死锁频率 <5次/小时
- ✅ 日志中无 "批量写入失败: deadlock detected"
- ✅ 批量写入统计正常

---

## 🔍 详细文档

| 文档 | 说明 |
|------|------|
| `DEADLOCK_FIX_README.md` | 主服务快速指南 |
| `DEADLOCK_FIX_SUMMARY.md` | 主服务详细文档 |
| `DEADLOCK_FIX_HYPE_SUMMARY.md` | HYPE服务文档 |
| `DEADLOCK_FIX_SYNC_REPORT.md` | 同步报告 |

---

## 🚨 遇到问题？

### 死锁频率仍然很高
```bash
# 启用数据库死锁日志
psql -d your_db << 'EOFDB'
ALTER SYSTEM SET deadlock_timeout = '1s';
ALTER SYSTEM SET log_lock_waits = on;
SELECT pg_reload_conf();
EOFDB

# 查看PostgreSQL日志
tail -f /path/to/postgresql.log | grep -i deadlock
```

### 重试成功率低
- 检查数据库负载（CPU、内存）
- 检查连接池使用率
- 考虑增加 `max_retries` 到7次

### 数据丢失
```bash
# 检查是否有重试耗尽错误
grep "重试耗尽" purr.log
grep "重试耗尽" purr_hype.log

# 验证数据完整性
psql -d your_db -c "SELECT COUNT(*) FROM kline_analysis WHERE analysis_time >= NOW() - INTERVAL '1 hour';"
```

---

## 📞 支持

遇到任何问题，请查看详细文档或运行监控脚本获取诊断信息：

```bash
./monitor_deadlock.sh        # 主服务监控
./monitor_deadlock_hype.sh    # HYPE服务监控
```

---

**Author**: Claude Code
**Date**: 2026-01-29
