# 修复验证清单

## 代码修改验证

### realtime_kline_service_hype.py
- [x] 第34行：已添加 `timezone` 导入
- [x] 第395行：K线时间使用 `timezone.utc`
- [x] 第907行：查询结束时间使用 `timezone.utc`
- [x] 第1154行：分析时间使用 `timezone.utc`

### utils/timescaledb.py - batch_insert()
- [x] 第781-796行：values 添加 `kline_time` 和 `analysis_delay_seconds`
- [x] 第798-810行：INSERT 语句添加对应字段（16个参数）

### utils/timescaledb.py - batch_insert_copy()
- [x] 第844-859行：CSV 数据添加新字段
- [x] 第867-882行：临时表结构添加新字段
- [x] 第886-893行：COPY 命令添加新字段
- [x] 第898-912行：INSERT 语句添加新字段

## 语法验证
```bash
✅ python -m py_compile realtime_kline_service_hype.py
✅ python -m py_compile utils/timescaledb.py
```

## 文件清单
- [x] detect_timezone_errors.sql - 历史错误检测脚本
- [x] tests/verify_timezone_fix.sql - 部署后验证脚本
- [x] tests/integration_test_timezone.py - 集成测试脚本
- [x] DEPLOYMENT_GUIDE.md - 部署指南
- [x] FIX_SUMMARY.md - 修复总结
- [x] deploy_fix.sh - 快速部署脚本
- [x] verification_checklist.md - 验证清单

## 部署前检查

### 1. 备份准备
- [ ] 代码备份路径确认
- [ ] 数据库备份路径确认
- [ ] 磁盘空间充足（至少1GB）

### 2. 权限检查
- [ ] Python 脚本执行权限
- [ ] 数据库连接权限
- [ ] 日志目录写入权限

### 3. 依赖检查
- [ ] psycopg3 已安装
- [ ] PostgreSQL 可连接
- [ ] 必要的环境变量已设置

## 部署步骤

### 方式1: 自动部署（推荐）
```bash
./deploy_fix.sh
```

### 方式2: 手动部署
```bash
# 1. 备份
./deploy_fix.sh  # 选择只执行备份

# 2. 检测
psql -h 127.0.0.1 -U postgres -d crypto_data -f detect_timezone_errors.sql

# 3. 测试
python tests/integration_test_timezone.py

# 4. 重启
# 停止服务 -> 启动服务

# 5. 验证
psql -h 127.0.0.1 -U postgres -d crypto_data -f tests/verify_timezone_fix.sql
```

## 部署后验证

### 关键指标
- [ ] 时区偏移 = 0（UTC+0）
- [ ] kline_time 字段非 NULL
- [ ] analysis_delay_seconds 字段非 NULL
- [ ] 延迟计算误差 < 0.01秒
- [ ] 无负延迟记录
- [ ] 平均延迟 3-8秒
- [ ] P95延迟 < 15秒

### 验证命令
```bash
# 快速检查
psql -h 127.0.0.1 -U postgres -d crypto_data -c "
SELECT
    COUNT(*) AS records_last_5min,
    COUNT(CASE WHEN kline_time IS NULL THEN 1 END) AS missing_kline_time,
    COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
    ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '5 minutes';
"

# 完整验证
psql -h 127.0.0.1 -U postgres -d crypto_data -f tests/verify_timezone_fix.sql
```

## 回滚准备

### 回滚触发条件
- [ ] 服务无法启动
- [ ] 大量数据写入失败
- [ ] 延迟指标异常（负延迟或超过30秒）
- [ ] 字段缺失率 > 10%

### 回滚命令
```bash
# 停止服务
ps aux | grep realtime_kline_service_hype | grep -v grep | awk '{print $2}' | xargs kill -15

# 恢复代码
cp realtime_kline_service_hype.py.backup.YYYYMMDD_HHMMSS realtime_kline_service_hype.py
cp utils/timescaledb.py.backup.YYYYMMDD_HHMMSS utils/timescaledb.py

# 重启服务
nohup python realtime_kline_service_hype.py > logs/service.log 2>&1 &
```

## 成功标准

### 数据质量
- ✅ 所有新记录 kline_time 非 NULL
- ✅ 所有新记录 analysis_delay_seconds 非 NULL
- ✅ 延迟计算误差 < 0.01秒
- ✅ 无负延迟记录

### 功能恢复
- ✅ 延迟监控功能正常
- ✅ K线时间追溯功能可用
- ✅ 时区一致性验证通过

### 性能指标
- ✅ 平均延迟 3-8秒
- ✅ P95延迟 < 15秒
- ✅ 服务稳定运行

## 联系人
- 技术负责人: [填写]
- 紧急联系: [填写]
