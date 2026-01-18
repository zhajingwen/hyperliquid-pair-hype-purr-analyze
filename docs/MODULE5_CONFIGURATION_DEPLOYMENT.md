# 模块5: 配置和部署 (Configuration & Deployment)

## 📋 模块概述

负责环境变量配置管理、依赖包管理、Docker Compose整合和部署文档编写。

### 模块职责
- ✅ 环境变量配置管理（utils/config.py）
- ✅ 依赖包声明（pyproject.toml）
- ✅ Docker Compose整合配置
- ✅ 部署文档和运维指南
- ✅ 一键部署验证

### 依赖关系
- **上游依赖**: 所有其他模块（模块1-4）
- **下游依赖**: 无（最终交付模块）

## 🔧 配置管理

### 文件1: utils/config.py

**改造前**:
```python
import os

ENV = os.getenv("ENV", "local")

# 飞书配置
lark_bot_id = os.getenv("LARKBOT_ID")

# Redis配置
redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
redis_password = os.getenv("REDIS_PASSWORD")
```

**改造后**:
```python
import os
from typing import Optional

# ========================================
# 运行环境配置
# ========================================
ENV = os.getenv("ENV", "local")

# ========================================
# 飞书Bot配置
# ========================================
lark_bot_id = os.getenv("LARKBOT_ID")

# ========================================
# Redis配置（原有）
# ========================================
redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
redis_password = os.getenv("REDIS_PASSWORD")

# ========================================
# TimescaleDB配置（新增）
# ========================================
timescaledb_host = os.getenv("TIMESCALEDB_HOST", "127.0.0.1")
timescaledb_port = int(os.getenv("TIMESCALEDB_PORT", "5432"))
timescaledb_name = os.getenv("TIMESCALEDB_NAME", "crypto_data")
timescaledb_user = os.getenv("TIMESCALEDB_USER", "postgres")
timescaledb_password = os.getenv("TIMESCALEDB_PASSWORD", "postgres")
timescaledb_pool_size = int(os.getenv("TIMESCALEDB_POOL_SIZE", "10"))

# ========================================
# 功能开关（新增）
# ========================================
enable_database = os.getenv("ENABLE_DATABASE", "true").lower() == "true"
enable_realtime_stream = os.getenv("ENABLE_REALTIME_STREAM", "false").lower() == "true"

# ========================================
# 配置验证（新增）
# ========================================
def validate_config():
    """验证必要的配置项"""
    errors = []

    # 验证TimescaleDB配置
    if enable_database:
        if not timescaledb_host:
            errors.append("TIMESCALEDB_HOST未设置")
        if not timescaledb_password or timescaledb_password == "postgres":
            errors.append("⚠️ 警告：使用默认数据库密码，建议修改")

    # 验证飞书Bot配置
    if lark_bot_id:
        if not lark_bot_id.startswith("cli_"):
            errors.append("LARKBOT_ID格式错误（应以cli_开头）")

    if errors:
        for error in errors:
            print(f"❌ 配置错误: {error}")
        if any("密码" not in e and "警告" not in e for e in errors):
            raise ValueError("配置验证失败，请检查环境变量")

# 启动时自动验证
if __name__ != "__main__":  # 仅在被导入时验证
    validate_config()
```

**改造说明**:
- 新增TimescaleDB连接配置（6个参数）
- 新增功能开关（enable_database, enable_realtime_stream）
- 新增配置验证函数（启动时自动检查）

---

### 文件2: .env.example（环境变量模板）

```env
# ========================================
# 运行环境
# ========================================
ENV=local

# ========================================
# TimescaleDB配置
# ========================================
# 数据库主机（Docker内使用timescaledb，本地使用localhost）
TIMESCALEDB_HOST=timescaledb
TIMESCALEDB_PORT=5432
TIMESCALEDB_NAME=crypto_data
TIMESCALEDB_USER=postgres
# ⚠️ 生产环境请修改默认密码！
TIMESCALEDB_PASSWORD=postgres
TIMESCALEDB_POOL_SIZE=10

# ========================================
# 功能开关
# ========================================
# 是否启用数据库（true/false）
ENABLE_DATABASE=true
# 是否启用实时数据流（true/false，可选功能）
ENABLE_REALTIME_STREAM=false

# ========================================
# 飞书Bot配置（可选）
# ========================================
# 飞书Bot Webhook ID（格式：cli_xxxxxx）
LARKBOT_ID=

# ========================================
# Redis配置（可选）
# ========================================
REDIS_HOST=127.0.0.1
REDIS_PASSWORD=
```

---

### 文件3: .env.production（生产环境配置）

```env
ENV=production

# TimescaleDB配置（生产环境）
TIMESCALEDB_HOST=timescaledb
TIMESCALEDB_PORT=5432
TIMESCALEDB_NAME=crypto_data
TIMESCALEDB_USER=postgres
TIMESCALEDB_PASSWORD=your_strong_password_here  # 请修改！
TIMESCALEDB_POOL_SIZE=20

# 功能开关
ENABLE_DATABASE=true
ENABLE_REALTIME_STREAM=true  # 生产环境启用实时数据流

# 飞书Bot配置
LARKBOT_ID=cli_your_bot_id_here

# Redis配置
REDIS_HOST=redis
REDIS_PASSWORD=your_redis_password
```

## 📦 依赖管理

### 文件: pyproject.toml

**改造前**:
```toml
dependencies = [
    "ccxt>=4.5.14",
    "hyperliquid-python-sdk>=0.8.0",
    "matplotlib>=3.10.7",
    "numpy>=2.3.4",
    "pandas>=2.3.3",
    "pyinform>=0.2.0",
    "redis>=7.1.0",
    "retry>=0.9.2",
    "scikit-learn>=1.8.0",
    "seaborn>=0.13.2",
    "statsmodels>=0.14.6",
]
```

**改造后**:
```toml
dependencies = [
    # 原有依赖
    "ccxt>=4.5.14",
    "hyperliquid-python-sdk>=0.8.0",
    "matplotlib>=3.10.7",
    "numpy>=2.3.4",
    "pandas>=2.3.3",
    "pyinform>=0.2.0",
    "redis>=7.1.0",
    "retry>=0.9.2",
    "scikit-learn>=1.8.0",
    "seaborn>=0.13.2",
    "statsmodels>=0.14.6",

    # 新增依赖（TimescaleDB支持）
    "psycopg[binary]>=3.2.0",      # PostgreSQL驱动（带二进制扩展）
    "psycopg-pool>=3.2.0",         # 连接池
]

[project.optional-dependencies]
# 实时数据流依赖（可选）
realtime = [
    "websockets>=12.0",
]

# 开发依赖
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.23.0",
    "black>=24.0.0",
    "flake8>=7.0.0",
]
```

**说明**:
- `psycopg[binary]`: 包含C扩展的高性能PostgreSQL驱动
- `psycopg-pool`: 连接池管理
- `realtime`: 可选依赖组，用于实时数据流功能
- `dev`: 开发依赖组（测试、代码格式化）

## 🐳 Docker Compose整合

### 文件: docker-compose.yml（完整版）

```yaml
version: '3.8'

services:
  # ========================================
  # TimescaleDB数据库
  # ========================================
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: crypto_timescaledb
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: crypto_data
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      TIMESCALEDB_TELEMETRY: "off"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./init_timescaledb.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - crypto_network
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  # ========================================
  # 实时K线数据流服务（可选）
  # ========================================
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
      ENABLE_REALTIME_ANALYSIS: ${ENABLE_REALTIME_ANALYSIS:-false}
    volumes:
      - ./realtime_kline_service.py:/app/realtime_kline_service.py
      - ./utils:/app/utils
    networks:
      - crypto_network
    command: python realtime_kline_service.py
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
    # 默认不启动（需要手动启动或在.env中设置ENABLE_REALTIME_STREAM=true）
    profiles:
      - realtime

volumes:
  timescaledb_data:
    driver: local

networks:
  crypto_network:
    driver: bridge
```

**说明**:
- **profiles**: 实时服务默认不启动，需要手动指定 `--profile realtime` 或修改配置
- **depends_on**: 确保数据库健康后才启动实时服务
- **资源限制**: 防止容器占用过多资源

## 📚 部署文档

### 文件: README_TIMESCALEDB.md

```markdown
# TimescaleDB持久化部署指南

## 🚀 快速开始

### 1. 环境准备

**系统要求**:
- Docker 20.10+
- Docker Compose 2.0+
- 可用内存 ≥4GB
- 可用磁盘空间 ≥20GB

**检查Docker版本**:
```bash
docker --version
docker-compose --version
```

---

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
nano .env

# 必须修改的配置项：
# - TIMESCALEDB_PASSWORD（生产环境请使用强密码）
# - LARKBOT_ID（如需飞书通知）
```

---

### 3. 启动数据库

```bash
# 启动TimescaleDB（后台运行）
docker-compose up -d timescaledb

# 查看启动日志
docker-compose logs -f timescaledb

# 预期输出:
# ✅ TimescaleDB初始化完成！
# database system is ready to accept connections
```

---

### 4. 验证数据库

```bash
# 连接到数据库
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

# 验证表是否创建
\dt

# 验证hypertable配置
SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables;

# 退出psql
\q
```

---

### 5. 安装Python依赖

```bash
# 安装基础依赖
pip install -e .

# 如需实时数据流，安装额外依赖
pip install -e .[realtime]
```

---

### 6. 运行分析引擎

```bash
# 首次运行（会下载所有历史数据并保存到数据库）
python multi_coins.py

# 预期输出:
# ✅ TimescaleDB已启用并成功连接
# 📊 数据库数据充足，跳过API调用 | BTC/USDC:USDC
# ...
```

---

### 7. 启动实时数据流（可选）

```bash
# 启动实时数据流服务
docker-compose --profile realtime up -d realtime-kline

# 查看实时日志
docker-compose logs -f realtime-kline

# 预期输出:
# 🚀 启动实时K线服务...
# ✅ WebSocket已连接，开始接收实时数据
```

---

## 🧪 测试验证

### 测试1: 数据库连接

```bash
# 测试连接
python -c "from utils.timescaledb import TimescaleDBClient; \
client = TimescaleDBClient('localhost', 5432, 'crypto_data', 'postgres', 'postgres'); \
print('✅ 连接成功')"
```

### 测试2: 数据写入性能

```bash
# 运行性能基准测试
pytest tests/test_timescaledb.py::test_batch_upsert_copy_performance -v

# 预期输出:
# ✅ COPY写入10000条记录耗时: 0.287秒 (34843条/秒)
```

### 测试3: 端到端测试

```bash
# 运行集成测试
pytest tests/test_integration.py -v

# 预期: 所有测试通过
```

---

## 📊 监控和维护

### 查看数据库大小

```sql
-- 连接数据库
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

-- 查看总大小
SELECT pg_size_pretty(pg_database_size('crypto_data'));

-- 查看各表大小
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### 查看压缩效果

```sql
-- 查看压缩率
SELECT
    hypertable_name,
    ROUND(100.0 * (uncompressed_total_bytes - compressed_total_bytes) / uncompressed_total_bytes, 2) AS compression_ratio
FROM timescaledb_information.hypertable_compression_stats;
```

### 备份数据库

```bash
# 备份整个数据库
docker exec crypto_timescaledb pg_dump -U postgres crypto_data > backup_$(date +%Y%m%d).sql

# 恢复备份
cat backup_20250111.sql | docker exec -i crypto_timescaledb psql -U postgres -d crypto_data
```

---

## ⚙️ 配置优化

### 生产环境优化

**1. 调整连接池大小**:
```env
# .env
TIMESCALEDB_POOL_SIZE=20  # 高并发场景
```

**2. 调整chunk大小**:
```sql
-- 高频数据（1m周期）：使用3天chunk
SELECT set_chunk_time_interval('klines', INTERVAL '3 days');
```

**3. 增加数据库内存**:
```yaml
# docker-compose.yml
services:
  timescaledb:
    command: >
      postgres
      -c shared_buffers=2GB
      -c effective_cache_size=6GB
```

---

## 🚨 常见问题

### Q1: 容器启动失败

**A**: 检查端口占用
```bash
lsof -i :5432
# 如果被占用，修改docker-compose.yml中的端口映射
```

### Q2: 连接超时

**A**: 检查网络和防火墙
```bash
# 测试连接
telnet localhost 5432
```

### Q3: 数据覆盖率低

**A**: 检查API调用是否成功
```bash
# 查看日志
docker-compose logs timescaledb | grep ERROR
```

---

## 📞 技术支持

- **问题反馈**: 通过GitHub Issues提交
- **文档**: 参考 `docs/` 目录下的模块设计文档
- **社区**: TimescaleDB官方文档 https://docs.timescale.com/

---

**版本**: v1.0
**日期**: 2025-01-11
```

## 🧪 部署验证脚本

### 文件: scripts/verify_deployment.sh

```bash
#!/bin/bash
# ========================================
# 部署验证脚本
# 用途: 验证TimescaleDB部署是否成功
# ========================================

set -e  # 遇到错误立即退出

echo "========================================="
echo "  TimescaleDB部署验证"
echo "========================================="

# 1. 检查Docker
echo "1️⃣ 检查Docker环境..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装"
    exit 1
fi
echo "✅ Docker版本: $(docker --version)"

# 2. 检查Docker Compose
echo ""
echo "2️⃣ 检查Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose未安装"
    exit 1
fi
echo "✅ Docker Compose版本: $(docker-compose --version)"

# 3. 检查容器状态
echo ""
echo "3️⃣ 检查容器状态..."
if ! docker ps | grep -q crypto_timescaledb; then
    echo "❌ TimescaleDB容器未运行"
    exit 1
fi
echo "✅ TimescaleDB容器正在运行"

# 4. 检查数据库连接
echo ""
echo "4️⃣ 检查数据库连接..."
if ! docker exec crypto_timescaledb psql -U postgres -d crypto_data -c "SELECT 1;" &> /dev/null; then
    echo "❌ 数据库连接失败"
    exit 1
fi
echo "✅ 数据库连接成功"

# 5. 检查表结构
echo ""
echo "5️⃣ 检查表结构..."
TABLE_COUNT=$(docker exec crypto_timescaledb psql -U postgres -d crypto_data -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
if [ "$TABLE_COUNT" -lt 3 ]; then
    echo "❌ 表结构不完整（应有3张表，实际${TABLE_COUNT}张）"
    exit 1
fi
echo "✅ 表结构完整（${TABLE_COUNT}张表）"

# 6. 检查Hypertable
echo ""
echo "6️⃣ 检查Hypertable配置..."
HYPERTABLE_COUNT=$(docker exec crypto_timescaledb psql -U postgres -d crypto_data -t -c "SELECT COUNT(*) FROM timescaledb_information.hypertables;")
if [ "$HYPERTABLE_COUNT" -lt 2 ]; then
    echo "❌ Hypertable配置不完整（应有2个，实际${HYPERTABLE_COUNT}个）"
    exit 1
fi
echo "✅ Hypertable配置正确（${HYPERTABLE_COUNT}个）"

# 7. 检查Python依赖
echo ""
echo "7️⃣ 检查Python依赖..."
if ! python -c "import psycopg" 2>/dev/null; then
    echo "❌ psycopg未安装"
    exit 1
fi
echo "✅ Python依赖完整"

# 8. 完成
echo ""
echo "========================================="
echo "  ✅ 部署验证通过！"
echo "========================================="
echo ""
echo "下一步: 运行 python multi_coins.py 开始分析"
```

**使用方法**:
```bash
# 添加执行权限
chmod +x scripts/verify_deployment.sh

# 运行验证
./scripts/verify_deployment.sh
```

## ✅ 验收标准

- [ ] .env.example 和 .env.production 文件创建完成
- [ ] utils/config.py 添加TimescaleDB配置
- [ ] pyproject.toml 添加psycopg依赖
- [ ] docker-compose.yml 整合所有服务
- [ ] README_TIMESCALEDB.md 文档完整
- [ ] verify_deployment.sh 脚本通过
- [ ] 一键部署成功（docker-compose up -d）
- [ ] 配置验证通过（无错误提示）

## 📝 总结

模块5完成后，整个TimescaleDB持久化项目的所有模块都已就绪：

✅ **模块1**: 数据库基础设施
✅ **模块2**: 数据库访问层
✅ **模块3**: 实时数据流（可选）
✅ **模块4**: 分析引擎集成
✅ **模块5**: 配置和部署

**可以开始实施了！** 🚀

---

**版本**: v1.0
**日期**: 2025-01-11
**作者**: Claude Sonnet 4.5
