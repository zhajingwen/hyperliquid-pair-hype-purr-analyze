# 快速操作指南

## 🚀 服务重启（激活新功能）

### 方式1: 分别重启两个服务

```bash
# 服务1: realtime_kline_service.py
kill 17089
nohup uv run realtime_kline_service.py > realtime_kline_service.log 2>&1 &

# 服务2: realtime_kline_service_hype.py
kill 17884
nohup uv run realtime_kline_service_hype.py > realtime_kline_service_hype.log 2>&1 &
```

### 方式2: 一起重启（推荐）

```bash
# 1. 停止所有服务
kill 17089 17884

# 2. 启动所有服务
nohup uv run realtime_kline_service.py > realtime_kline_service.log 2>&1 &
nohup uv run realtime_kline_service_hype.py > realtime_kline_service_hype.log 2>&1 &

# 3. 确认服务运行
ps aux | grep "realtime_kline_service" | grep -v grep

# 4. 监控日志
tail -f realtime_kline_service.log
tail -f realtime_kline_service_hype.log
```

## ✅ 运行时验证（重启后10分钟执行）

```bash
.venv/bin/python verify_runtime.py
```

## 📊 常用SQL查询

### 查看最新记录

```sql
SELECT
    symbol,
    kline_time,
    analysis_time,
    analysis_delay_seconds
FROM analysis_results
ORDER BY analysis_time DESC
LIMIT 20;
```

### 延迟分布统计

```sql
SELECT
    AVG(analysis_delay_seconds) as avg_delay,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p50,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p95,
    MAX(analysis_delay_seconds) as max_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 day';
```

### 高延迟分析

```sql
SELECT
    symbol,
    kline_time,
    analysis_time,
    analysis_delay_seconds
FROM analysis_results
WHERE analysis_delay_seconds > 10
ORDER BY analysis_delay_seconds DESC
LIMIT 20;
```

### 按币种统计延迟

```sql
SELECT
    symbol,
    COUNT(*) as count,
    AVG(analysis_delay_seconds) as avg_delay,
    MAX(analysis_delay_seconds) as max_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 day'
GROUP BY symbol
ORDER BY avg_delay DESC
LIMIT 20;
```

## 🔄 回滚方案

```bash
# 停止服务
kill $(pgrep -f "realtime_kline_service.py")

# 恢复旧代码
cp realtime_kline_service.py.backup realtime_kline_service.py

# 重启服务
nohup uv run realtime_kline_service.py > realtime_kline_service.log 2>&1 &
```

## 📖 详细文档

- `DEPLOYMENT_SUMMARY.md` - 完整部署报告
- `KLINE_TIME_MIGRATION_README.md` - 实施指南
- `verify_runtime.py` - 运行时验证脚本
