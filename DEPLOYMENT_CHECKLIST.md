# WebSocket 原生重构 - 部署检查清单

## 📋 部署前检查 (Pre-Deployment)

### 1. 代码修改验证

- [x] `utils/enhanced_ws_manager.py` 修改完成
  - [x] 导入语句已更新
  - [x] 类初始化已修改
  - [x] `_connect()` 方法重写
  - [x] 添加 `_on_open()`, `_on_message()`, `_on_error()`, `_on_close()` 回调
  - [x] 添加 `_ping_loop()` 方法
  - [x] `_is_connected()` 方法重写
  - [x] `_force_cleanup_connection()` 方法重写
  - [x] `add_subscriptions()` 方法修改
  - [x] `_reconnect()` 方法修改
  - [x] `stop()` 方法修改

### 2. 依赖检查

- [x] `websocket-client==1.8.0` 已安装
  ```bash
  source venv/bin/activate
  python -c "import websocket; print(websocket.__version__)"
  # 预期输出: 1.8.0
  ```

### 3. 语法检查

- [x] Python 语法检查通过
  ```bash
  source venv/bin/activate
  python -m py_compile utils/enhanced_ws_manager.py
  # 预期: 无输出(成功)
  ```

### 4. 单元测试

- [x] 基本功能测试通过 (`test_native_ws.py`)
  - 连接成功率: 100%
  - 消息接收: 79条/32秒
  - 健康度: 98.1%
  - 清理流程: 5步全部完成

- [x] 重连功能测试通过 (`test_reconnection.py`)
  - 自动重连: 成功
  - 重连耗时: ~4秒
  - 消息恢复: 正常

### 5. 代码备份

```bash
# 备份当前生产代码
cp utils/enhanced_ws_manager.py utils/enhanced_ws_manager.py.backup_$(date +%Y%m%d_%H%M%S)

# 验证备份
ls -lh utils/enhanced_ws_manager.py*
```

---

## 🚀 部署步骤 (Deployment)

### 方案 A: 安全部署(推荐)

**适用场景**: 生产环境,需要最小化风险

```bash
# 1. 停止服务
systemctl stop hyperliquid-kline-service
# 或
pkill -f realtime_kline_service.py

# 2. 等待当前连接优雅关闭(最多30秒)
sleep 5

# 3. 检查进程是否已完全退出
ps aux | grep realtime_kline_service

# 4. 部署新代码(已在 venv 中安装 websocket-client)
# (代码已在开发环境修改完成)

# 5. 启动服务
systemctl start hyperliquid-kline-service
# 或
source venv/bin/activate && python realtime_kline_service.py &

# 6. 等待启动(5秒)
sleep 5

# 7. 检查日志
tail -f logs/app.log | grep -E "WebSocket|连接|重连|健康"
```

### 方案 B: 热重启(快速)

**适用场景**: 开发/测试环境

```bash
# 1. 发送停止信号
kill -SIGTERM <pid>

# 2. 等待5秒
sleep 5

# 3. 强制终止(如果还未退出)
kill -9 <pid>

# 4. 立即重启
source venv/bin/activate && python realtime_kline_service.py &
```

---

## 📊 部署后监控 (Post-Deployment)

### 1. 立即检查(0-5分钟)

**关键日志模式**:
```bash
# 连接建立
grep "WebSocket 连接已建立" logs/app.log

# 订阅成功
grep "订阅成功" logs/app.log

# 状态转换
grep "状态转换" logs/app.log

# 消息接收
grep "收到消息" logs/app.log
```

**预期输出**:
```
2026-01-29 XX:XX:XX - app - INFO - WebSocket 连接已建立
2026-01-29 XX:XX:XX - app - INFO - 状态转换: connecting → connected
2026-01-29 XX:XX:XX - app - INFO - ✅ WebSocket连接成功 | 订阅数: N
```

**异常检查**:
```bash
# 错误日志
grep -E "ERROR|CRITICAL|失败" logs/app.log | tail -20

# 重连日志
grep "重连" logs/app.log

# 清理日志
grep "强制清理" logs/app.log
```

### 2. 短期监控(5-30分钟)

**健康指标**:
```bash
# 每5分钟检查一次
watch -n 300 'grep "健康报告" logs/app.log | tail -5'
```

**预期指标**:
- 健康度: >95%
- 消息数: 持续增长
- 重连次数: 0-1次

**告警条件**:
- 健康度 <80% (可能是假活)
- 消息数不增长 (可能是连接断开)
- 重连次数 >3次 (可能是网络不稳定)

### 3. 长期监控(30分钟-7天)

**关键指标**:

| 指标 | 目标值 | 检查频率 | 告警阈值 |
|------|--------|---------|---------|
| 连接成功率 | >99.9% | 每小时 | <99% |
| 消息接收率 | >99.9% | 每小时 | <99% |
| 重连次数 | <5次/天 | 每天 | >10次/天 |
| 内存占用 | <512MB | 每小时 | >600MB |
| CPU 占用 | <50% | 每小时 | >80% |
| 僵尸状态 | 0次 | 实时 | 1次 |

**监控命令**:
```bash
# 内存占用
ps aux | grep realtime_kline_service | awk '{print $6/1024 " MB"}'

# CPU 占用
top -p <pid> -n 1 | grep realtime_kline_service

# 连接状态
netstat -an | grep 'api.hyperliquid.xyz'
```

---

## 🔧 故障排查 (Troubleshooting)

### 问题 1: 连接建立失败

**症状**:
```
ERROR - WebSocket连接失败: [Errno 61] Connection refused
```

**原因**:
- 网络不可达
- API 服务器宕机
- 防火墙阻止

**排查步骤**:
```bash
# 1. 测试网络连通性
ping api.hyperliquid.xyz

# 2. 测试 WebSocket 端点
curl -I https://api.hyperliquid.xyz

# 3. 检查防火墙
sudo iptables -L | grep hyperliquid
```

**解决方案**:
- 检查网络配置
- 等待 API 服务器恢复
- 调整防火墙规则

### 问题 2: 频繁重连

**症状**:
```
INFO - ⏳ 准备重连 (第5次/30)
INFO - ⏳ 准备重连 (第6次/30)
```

**原因**:
- 网络不稳定
- 服务器压力大
- 订阅过多

**排查步骤**:
```bash
# 1. 检查网络延迟
ping -c 10 api.hyperliquid.xyz

# 2. 检查订阅数量
grep "订阅数" logs/app.log | tail -1

# 3. 检查服务器响应
time curl https://api.hyperliquid.xyz/info
```

**解决方案**:
- 优化网络环境
- 减少订阅数量
- 增加重连延迟

### 问题 3: 假活状态

**症状**:
```
WARNING - 假活状态检测: 35.0秒未收到数据
```

**原因**:
- WebSocket 连接正常但无消息
- 订阅频道无更新
- Ping 超时

**排查步骤**:
```bash
# 1. 检查底层连接状态
grep "_is_connected" logs/app.log | tail -10

# 2. 检查 Ping 状态
grep "Ping" logs/app.log | tail -10

# 3. 检查订阅状态
grep "订阅" logs/app.log | tail -10
```

**解决方案**:
- 触发手动重连
- 检查订阅配置
- 调整超时阈值

### 问题 4: 内存泄漏

**症状**:
- 内存占用持续增长
- 进程占用超过 600MB

**排查步骤**:
```bash
# 1. 监控内存增长
watch -n 60 'ps aux | grep realtime_kline_service'

# 2. 检查线程数
ps -eLf | grep realtime_kline_service | wc -l

# 3. 检查连接数
lsof -p <pid> | grep ESTABLISHED | wc -l
```

**解决方案**:
- 重启服务
- 检查清理流程日志
- 排查未释放的资源

---

## 🔄 回滚方案 (Rollback)

### 触发条件

**立即回滚**:
- 连接成功率 <90%
- 消息丢失率 >10%
- 服务崩溃

**计划回滚**:
- 内存泄漏(24小时增长 >100MB)
- 频繁重连(>10次/小时)

### 回滚步骤

```bash
# 1. 停止服务
systemctl stop hyperliquid-kline-service

# 2. 恢复备份
cp utils/enhanced_ws_manager.py.backup_YYYYMMDD_HHMMSS utils/enhanced_ws_manager.py

# 3. 卸载 websocket-client(可选)
source venv/bin/activate
pip uninstall websocket-client -y

# 4. 重启服务
systemctl start hyperliquid-kline-service

# 5. 验证
tail -f logs/app.log | grep "WebSocket"
```

**预计回滚时间**: 5-10分钟

---

## ✅ 部署验证检查清单

### 立即验证(0-5分钟)

- [ ] 服务进程已启动
- [ ] WebSocket 连接已建立
- [ ] 订阅消息已发送
- [ ] 开始接收数据
- [ ] 无 ERROR 日志

### 短期验证(5-30分钟)

- [ ] 消息持续接收
- [ ] 健康度 >95%
- [ ] 无异常重连
- [ ] 内存占用正常
- [ ] CPU 占用正常

### 长期验证(1-7天)

- [ ] 无崩溃
- [ ] 无僵尸状态
- [ ] 重连次数 <5次/天
- [ ] 内存稳定
- [ ] 性能正常

---

## 📞 联系方式

**问题上报**:
- 查看: `NATIVE_WS_REFACTOR_SUMMARY.md`
- 日志: `logs/app.log`

**紧急回滚**:
- 执行: 上述回滚方案
- 时间: <10分钟

---

**检查清单版本**: v1.0
**创建日期**: 2026-01-29
**最后更新**: 2026-01-29
