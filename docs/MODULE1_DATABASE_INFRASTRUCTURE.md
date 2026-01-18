# 模块1: 数据库基础设施 (Database Infrastructure)

## 📋 模块概述

负责TimescaleDB容器的部署、数据库schema的初始化、表结构创建以及数据保留和压缩策略的配置。

### 模块职责
- ✅ TimescaleDB Docker容器配置
- ✅ 数据库初始化SQL脚本
- ✅ 表结构和索引设计
- ✅ 数据保留策略（90天滚动窗口）
- ✅ 数据压缩策略（7天后自动压缩）
- ✅ 连续聚合视图（每日统计）

### 依赖关系
- **上游依赖**: 无（基础模块）
- **下游依赖**: 模块2（数据库访问层）、模块3（实时数据流）、模块4（分析引擎）

## 🗄️ 数据库表设计

### 表1: klines（K线数据表）

**用途**: 存储所有币种的K线历史数据

```sql
CREATE TABLE klines (
    time            TIMESTAMPTZ NOT NULL,
    symbol          VARCHAR(50) NOT NULL,
    timeframe       VARCHAR(10) NOT NULL,
    open            DOUBLE PRECISION NOT NULL,
    high            DOUBLE PRECISION NOT NULL,
    low             DOUBLE PRECISION NOT NULL,
    close           DOUBLE PRECISION NOT NULL,
    volume          DOUBLE PRECISION NOT NULL,
    volume_usd      DOUBLE PRECISION,
    return_pct      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, symbol, timeframe)
);
```

**设计要点**:
- **复合主键**: `(time, symbol, timeframe)` 确保唯一性
- **时间分区**: 使用TimescaleDB的hypertable，按7天自动分区
- **数据类型**: DOUBLE PRECISION存储价格和成交量，TIMESTAMPTZ存储时间（UTC时区）
- **索引优化**: 支持按币种+周期+时间倒序查询

**Hypertable配置**:
```sql
SELECT create_hypertable('klines', 'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);
```

**索引策略**:
```sql
-- 按币种+周期+时间倒序查询索引
CREATE INDEX idx_symbol_timeframe_time
    ON klines (symbol, timeframe, time DESC);
```

**数据保留策略**:
```sql
-- 自动删除90天前的数据
SELECT add_retention_policy('klines', INTERVAL '90 days', if_not_exists => TRUE);
```

**压缩策略**:
```sql
-- 启用压缩
ALTER TABLE klines SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,timeframe'
);

-- 自动压缩7天前的数据
SELECT add_compression_policy('klines', INTERVAL '7 days', if_not_exists => TRUE);
```

---

### 表2: symbol_metadata（币种元数据表）

**用途**: 追踪所有币种的上线时间、数据质量状态和最后更新时间

```sql
CREATE TABLE symbol_metadata (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(50) UNIQUE NOT NULL,
    base_asset      VARCHAR(20),
    quote_asset     VARCHAR(20),
    listing_time    TIMESTAMPTZ,
    first_kline_time TIMESTAMPTZ,
    last_kline_time  TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    data_quality_score DOUBLE PRECISION,
    total_klines    BIGINT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**设计要点**:
- **唯一约束**: `symbol` 字段唯一
- **数据质量追踪**: `data_quality_score` 评估数据完整性（0-1.0）
- **活跃状态**: `is_active` 标记退市币种
- **时间追踪**: `listing_time` 记录币种上线时间，`first_kline_time`/`last_kline_time` 记录数据范围

**索引策略**:
```sql
-- 活跃币种快速查询
CREATE INDEX idx_active_symbols ON symbol_metadata (is_active, symbol)
    WHERE is_active = TRUE;

-- 按上线时间排序
CREATE INDEX idx_listing_time ON symbol_metadata (listing_time DESC);
```

---

### 表3: analysis_results（分析结果表）

**用途**: 存储每次分析运行的相关系数、Z-score、协整检验结果和交易信号

```sql
CREATE TABLE analysis_results (
    id                  SERIAL,
    analysis_time       TIMESTAMPTZ NOT NULL,
    symbol              VARCHAR(50) NOT NULL,
    base_symbol         VARCHAR(50) NOT NULL,

    -- 相关系数数据
    corr_5m_7d          DOUBLE PRECISION,
    corr_1h_30d         DOUBLE PRECISION,
    corr_4h_60d         DOUBLE PRECISION,

    -- Z-score数据
    zscore_5m           DOUBLE PRECISION,
    zscore_1h           DOUBLE PRECISION,
    zscore_4h           DOUBLE PRECISION,

    -- 协整检验结果
    cointegration_passed BOOLEAN,
    adf_pvalue          DOUBLE PRECISION,

    -- 交易信号
    is_anomaly          BOOLEAN,
    trading_direction   VARCHAR(50),
    signal_strength     VARCHAR(20),

    -- 元数据
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (analysis_time, id)
);
```

**设计要点**:
- **时间分区主键**: `(analysis_time, id)` 支持时间范围查询
- **信号筛选**: `is_anomaly` 字段快速过滤套利机会
- **多周期支持**: 存储5m、1h、4h三个周期的数据

**Hypertable配置**:
```sql
SELECT create_hypertable('analysis_results', 'analysis_time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE);
```

**索引策略**:
```sql
-- 按币种+时间倒序查询索引
CREATE INDEX idx_analysis_symbol_time
    ON analysis_results (symbol, analysis_time DESC);

-- 异常信号快速查询索引
CREATE INDEX idx_anomaly_time
    ON analysis_results (is_anomaly, analysis_time DESC)
    WHERE is_anomaly = TRUE;
```

**数据保留策略**:
```sql
-- 保留180天的分析历史
SELECT add_retention_policy('analysis_results', INTERVAL '180 days', if_not_exists => TRUE);
```

**压缩策略**:
```sql
ALTER TABLE analysis_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('analysis_results', INTERVAL '30 days', if_not_exists => TRUE);
```

---

### 连续聚合视图: daily_analysis_stats

**用途**: 每日分析统计，支持趋势分析和回测

```sql
CREATE MATERIALIZED VIEW daily_analysis_stats
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', analysis_time) AS day,
    symbol,
    AVG(corr_4h_60d) AS avg_correlation,
    AVG(zscore_4h) AS avg_zscore,
    COUNT(*) FILTER (WHERE is_anomaly = TRUE) AS anomaly_count,
    COUNT(*) AS total_count
FROM analysis_results
GROUP BY day, symbol
WITH NO DATA;
```

**自动刷新策略**:
```sql
SELECT add_continuous_aggregate_policy('daily_analysis_stats',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);
```

## 🐳 Docker Compose配置

### 文件: docker-compose.yml

```yaml
version: '3.8'

services:
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
    # 资源限制（生产环境）
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

volumes:
  timescaledb_data:
    driver: local

networks:
  crypto_network:
    driver: bridge
```

**配置说明**:
- **镜像版本**: timescale/timescaledb:latest-pg16 (PostgreSQL 16 + TimescaleDB最新版)
- **端口映射**: 5432:5432（主机可直接访问）
- **健康检查**: 每10秒检查一次，5秒超时，失败重试5次
- **自动重启**: `unless-stopped` 确保容器意外退出后自动重启
- **资源限制**: CPU 2核，内存4GB（可根据实际负载调整）

## 📄 SQL初始化脚本

### 文件: init_timescaledb.sql

**完整脚本**:

```sql
-- ========================================
-- TimescaleDB初始化脚本
-- 用途: 创建表结构、索引、保留策略、压缩策略
-- ========================================

-- 启用TimescaleDB扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ========================================
-- 表1: klines (K线数据表)
-- ========================================
CREATE TABLE IF NOT EXISTS klines (
    time            TIMESTAMPTZ NOT NULL,
    symbol          VARCHAR(50) NOT NULL,
    timeframe       VARCHAR(10) NOT NULL,
    open            DOUBLE PRECISION NOT NULL,
    high            DOUBLE PRECISION NOT NULL,
    low             DOUBLE PRECISION NOT NULL,
    close           DOUBLE PRECISION NOT NULL,
    volume          DOUBLE PRECISION NOT NULL,
    volume_usd      DOUBLE PRECISION,
    return_pct      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, symbol, timeframe)
);

-- 转换为hypertable（自动分区）
SELECT create_hypertable('klines', 'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_symbol_timeframe_time
    ON klines (symbol, timeframe, time DESC);

-- 数据保留策略（保留90天）
SELECT add_retention_policy('klines', INTERVAL '90 days', if_not_exists => TRUE);

-- 压缩策略（7天后自动压缩）
ALTER TABLE klines SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,timeframe'
);

SELECT add_compression_policy('klines', INTERVAL '7 days', if_not_exists => TRUE);

-- ========================================
-- 表2: symbol_metadata (币种元数据表)
-- ========================================
CREATE TABLE IF NOT EXISTS symbol_metadata (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(50) UNIQUE NOT NULL,
    base_asset      VARCHAR(20),
    quote_asset     VARCHAR(20),
    listing_time    TIMESTAMPTZ,
    first_kline_time TIMESTAMPTZ,
    last_kline_time  TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    data_quality_score DOUBLE PRECISION,
    total_klines    BIGINT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_active_symbols ON symbol_metadata (is_active, symbol)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_listing_time ON symbol_metadata (listing_time DESC);

-- ========================================
-- 表3: analysis_results (分析结果表)
-- ========================================
CREATE TABLE IF NOT EXISTS analysis_results (
    id                  SERIAL,
    analysis_time       TIMESTAMPTZ NOT NULL,
    symbol              VARCHAR(50) NOT NULL,
    base_symbol         VARCHAR(50) NOT NULL,
    corr_5m_7d          DOUBLE PRECISION,
    corr_1h_30d         DOUBLE PRECISION,
    corr_4h_60d         DOUBLE PRECISION,
    zscore_5m           DOUBLE PRECISION,
    zscore_1h           DOUBLE PRECISION,
    zscore_4h           DOUBLE PRECISION,
    cointegration_passed BOOLEAN,
    adf_pvalue          DOUBLE PRECISION,
    is_anomaly          BOOLEAN DEFAULT FALSE,
    trading_direction   VARCHAR(50),
    signal_strength     VARCHAR(20),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (analysis_time, id)
);

-- 转换为hypertable
SELECT create_hypertable('analysis_results', 'analysis_time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_analysis_symbol_time
    ON analysis_results (symbol, analysis_time DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_time
    ON analysis_results (is_anomaly, analysis_time DESC)
    WHERE is_anomaly = TRUE;

-- 数据保留策略（保留180天）
SELECT add_retention_policy('analysis_results', INTERVAL '180 days', if_not_exists => TRUE);

-- 压缩策略（30天后自动压缩）
ALTER TABLE analysis_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('analysis_results', INTERVAL '30 days', if_not_exists => TRUE);

-- ========================================
-- 连续聚合视图: daily_analysis_stats
-- ========================================
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_analysis_stats
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', analysis_time) AS day,
    symbol,
    AVG(corr_4h_60d) AS avg_correlation,
    AVG(zscore_4h) AS avg_zscore,
    COUNT(*) FILTER (WHERE is_anomaly = TRUE) AS anomaly_count,
    COUNT(*) AS total_count
FROM analysis_results
GROUP BY day, symbol
WITH NO DATA;

-- 自动刷新连续聚合（每小时）
SELECT add_continuous_aggregate_policy('daily_analysis_stats',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- ========================================
-- 授权（可选：如果使用非postgres用户）
-- ========================================
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;

-- ========================================
-- 完成
-- ========================================
\echo '✅ TimescaleDB初始化完成！'
```

## 🔧 环境变量配置

### 文件: .env.example

```env
# TimescaleDB配置
POSTGRES_PASSWORD=postgres
TIMESCALEDB_HOST=127.0.0.1
TIMESCALEDB_PORT=5432
TIMESCALEDB_NAME=crypto_data
TIMESCALEDB_USER=postgres
TIMESCALEDB_POOL_SIZE=10

# 飞书Bot（可选）
LARKBOT_ID=your_bot_id_here

# Redis配置（可选）
REDIS_HOST=127.0.0.1
REDIS_PASSWORD=

# 运行环境
ENV=local
```

## 🚀 部署步骤

### 步骤1: 创建配置文件

```bash
# 进入项目目录
cd /Users/test/Downloads/hyperliquid-pair-hype-purr-analyze

# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，设置数据库密码（可选）
nano .env
```

### 步骤2: 启动TimescaleDB容器

```bash
# 启动容器（后台运行）
docker-compose up -d timescaledb

# 查看容器日志
docker-compose logs -f timescaledb
```

**预期输出**:
```
crypto_timescaledb | PostgreSQL init process complete; ready for start up.
crypto_timescaledb | ✅ TimescaleDB初始化完成！
crypto_timescaledb | database system is ready to accept connections
```

### 步骤3: 验证数据库

```bash
# 连接到数据库
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

# 验证表是否创建成功
\dt

# 验证hypertable配置
SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables;

# 退出psql
\q
```

**预期输出**:
```
                  List of relations
 Schema |         Name          | Type  |  Owner
--------+-----------------------+-------+----------
 public | analysis_results      | table | postgres
 public | klines                | table | postgres
 public | symbol_metadata       | table | postgres

 hypertable_name  | num_dimensions
------------------+----------------
 klines           |              1
 analysis_results |              1
```

## 🧪 测试策略

### 测试1: 容器健康检查

```bash
# 检查容器状态
docker ps | grep timescaledb

# 检查健康状态
docker inspect crypto_timescaledb | grep -A 10 Health
```

**预期结果**: Status显示为"healthy"

### 测试2: SQL脚本语法验证

```bash
# 使用PostgreSQL客户端验证语法
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data -f /docker-entrypoint-initdb.d/init.sql
```

**预期结果**: 无语法错误，所有表和索引创建成功

### 测试3: 表结构完整性测试

```sql
-- 连接到数据库
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data

-- 检查klines表结构
\d klines

-- 检查索引
\di

-- 检查压缩策略
SELECT * FROM timescaledb_information.compression_settings;

-- 检查保留策略
SELECT * FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';
```

### 测试4: 插入和查询性能基准测试

```sql
-- 插入测试数据（10000条）
INSERT INTO klines (time, symbol, timeframe, open, high, low, close, volume, volume_usd, return_pct)
SELECT
    generate_series(NOW() - INTERVAL '100 days', NOW(), INTERVAL '1 minute') AS time,
    'BTC/USDC:USDC' AS symbol,
    '1m' AS timeframe,
    50000 + random() * 1000 AS open,
    50000 + random() * 1000 AS high,
    50000 + random() * 1000 AS low,
    50000 + random() * 1000 AS close,
    random() * 100 AS volume,
    (50000 + random() * 1000) * random() * 100 AS volume_usd,
    random() * 0.01 AS return_pct
LIMIT 10000;

-- 查询性能测试
\timing on
SELECT * FROM klines WHERE symbol = 'BTC/USDC:USDC' AND timeframe = '1m'
ORDER BY time DESC LIMIT 100;
\timing off

-- 清理测试数据
DELETE FROM klines WHERE symbol = 'BTC/USDC:USDC';
```

**性能预期**:
- 插入10000条记录: <1秒
- 查询100条记录: <50ms

## 📊 监控和维护

### 数据库大小监控

```sql
-- 查看数据库总大小
SELECT pg_size_pretty(pg_database_size('crypto_data'));

-- 查看各表大小
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS data_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS external_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### 压缩率监控

```sql
-- 查看压缩效果
SELECT
    hypertable_name,
    compression_status,
    uncompressed_total_bytes,
    compressed_total_bytes,
    ROUND(100.0 * (uncompressed_total_bytes - compressed_total_bytes) / uncompressed_total_bytes, 2) AS compression_ratio
FROM timescaledb_information.hypertable_compression_stats;
```

### 数据保留策略监控

```sql
-- 查看保留策略执行历史
SELECT * FROM timescaledb_information.job_stats
WHERE job_id IN (
    SELECT job_id FROM timescaledb_information.jobs
    WHERE proc_name = 'policy_retention'
);
```

## ⚠️ 常见问题排查

### 问题1: 容器无法启动

**症状**: `docker-compose up -d` 后容器立即退出

**排查步骤**:
```bash
# 查看容器日志
docker-compose logs timescaledb

# 检查端口占用
lsof -i :5432

# 检查卷权限
ls -la timescaledb_data/
```

**解决方案**:
- 如果5432端口被占用，修改 `docker-compose.yml` 中的端口映射
- 如果卷权限错误，删除卷后重新创建：`docker-compose down -v && docker-compose up -d`

### 问题2: SQL初始化脚本执行失败

**症状**: 容器启动但表未创建

**排查步骤**:
```bash
# 进入容器
docker exec -it crypto_timescaledb bash

# 查看初始化日志
cat /var/lib/postgresql/data/pg_log/postgresql-*.log

# 手动执行SQL脚本
psql -U postgres -d crypto_data -f /docker-entrypoint-initdb.d/init.sql
```

**解决方案**:
- 检查SQL脚本语法
- 确保TimescaleDB扩展正确安装：`CREATE EXTENSION IF NOT EXISTS timescaledb;`

### 问题3: 连接超时

**症状**: 应用连接数据库时超时

**排查步骤**:
```bash
# 测试连接
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data -c "SELECT 1;"

# 检查防火墙
sudo ufw status
```

**解决方案**:
- 确保容器网络正确配置
- 检查 `pg_hba.conf` 是否允许客户端连接

## 📈 性能优化建议

### 1. 调整chunk大小

根据数据量调整hypertable的chunk_time_interval：

```sql
-- 高频数据（1m周期）：使用3天chunk
SELECT set_chunk_time_interval('klines', INTERVAL '3 days');

-- 低频数据（1d周期）：使用30天chunk
SELECT set_chunk_time_interval('klines', INTERVAL '30 days');
```

### 2. 增加连接池大小

修改 `docker-compose.yml`:

```yaml
environment:
  POSTGRES_MAX_CONNECTIONS: 200  # 默认100
```

### 3. 调整内存配置

修改 `docker-compose.yml`:

```yaml
command: >
  postgres
  -c shared_buffers=2GB
  -c effective_cache_size=6GB
  -c maintenance_work_mem=512MB
  -c work_mem=128MB
```

## ✅ 验收标准

- [ ] TimescaleDB容器成功启动并通过健康检查
- [ ] 所有表（klines, symbol_metadata, analysis_results）创建成功
- [ ] 所有索引创建成功
- [ ] Hypertable配置正确（7天chunk，自动压缩，90天保留）
- [ ] 连续聚合视图 `daily_analysis_stats` 创建成功
- [ ] 插入10000条测试数据性能<1秒
- [ ] 查询100条数据性能<50ms
- [ ] 数据库总大小<100MB（空库）
- [ ] 文档完整，部署步骤可重现

## 📝 下一步

模块1完成后，继续实施：
- **模块2**: 数据库访问层 (utils/timescaledb.py)
- **模块4**: 分析引擎集成 (multi_coins.py改造)

---

**版本**: v1.0
**日期**: 2025-01-11
**作者**: Claude Sonnet 4.5
