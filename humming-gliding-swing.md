# TimescaleDB集成实施计划

## 📋 需求概述

为 `multi_coins3.py` 添加TimescaleDB持久化支持，实现：
- K线数据持久化存储
- 分析结果历史记录
- 增量数据更新减少API调用
- Docker Compose一键部署

## 🎯 用户选择的配置

| 维度 | 选择方案 |
|------|---------|
| **缓存策略** | 双层缓存（TimescaleDB→API） |
| **数据更新** | 增量更新（智能检测缺失时间段） |
| **结果持久化** | 是（存储相关系数、Z-score等） |
| **部署方式** | Docker Compose |

## 📁 文件修改清单

### 新增文件（6个）

1. **`utils/timescaledb.py`** (约150行)
   - 数据库连接管理
   - K线数据CRUD操作
   - 分析结果存储接口

2. **`docker-compose.yml`** (约30行)
   - TimescaleDB容器配置
   - 端口映射和卷挂载

3. **`init_timescaledb.sql`** (约80行)
   - 创建hypertable（klines表）
   - 创建分析结果表（analysis_results）
   - 创建索引和数据保留策略

4. **`.env.example`** (约15行)
   - TimescaleDB连接配置示例

5. **`migrations/001_initial_schema.sql`** (约50行)
   - 独立的迁移脚本备份

6. **`README_TIMESCALEDB.md`** (约100行)
   - 快速开始指南
   - 数据库表结构说明
   - 常见问题排查

### 修改文件（3个）

1. **`utils/config.py`** (+10行)
   - 添加TimescaleDB连接配置

2. **`pyproject.toml`** (+3行)
   - 添加`psycopg[binary]`依赖

3. **`multi_coins3.py`** (修改约200行)
   - 集成数据库查询逻辑
   - 实现增量更新算法
   - 保存分析结果到数据库

## 🗄️ 数据库设计

### 表1: klines（K线数据表）

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

-- 转换为hypertable（自动分区）
SELECT create_hypertable('klines', 'time',
    chunk_time_interval => INTERVAL '7 days');

-- 索引优化
CREATE INDEX idx_symbol_timeframe_time
    ON klines (symbol, timeframe, time DESC);

-- 数据保留策略（自动清理90天前的数据）
SELECT add_retention_policy('klines', INTERVAL '90 days');
```

**设计说明**：
- **分区策略**: 按时间自动分区（每7天一个chunk）
- **复合主键**: (time, symbol, timeframe) 确保唯一性
- **索引优化**: 支持按币种+周期+时间倒序查询
- **自动清理**: 90天滚动窗口，自动删除过期数据

### 表2: analysis_results（分析结果表）

```sql
CREATE TABLE analysis_results (
    id                  SERIAL PRIMARY KEY,
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
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 转换为hypertable
SELECT create_hypertable('analysis_results', 'analysis_time',
    chunk_time_interval => INTERVAL '30 days');

-- 索引优化
CREATE INDEX idx_analysis_symbol_time
    ON analysis_results (symbol, analysis_time DESC);
CREATE INDEX idx_anomaly_time
    ON analysis_results (is_anomaly, analysis_time DESC)
    WHERE is_anomaly = TRUE;
```

**设计说明**：
- **分析快照**: 每次运行存储所有币种的分析结果
- **信号筛选**: 通过`is_anomaly`索引快速查询套利机会
- **历史回测**: 支持追踪币种的相关性变化趋势

## 🔧 实现详细设计

### 1. utils/timescaledb.py

```python
"""
TimescaleDB连接管理和数据访问层

提供K线数据和分析结果的CRUD操作
"""
import psycopg
from psycopg_pool import ConnectionPool
from typing import Optional, Dict, List, Tuple
import pandas as pd
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('HyperliquidAnalyzer')

class TimescaleDBClient:
    """TimescaleDB客户端单例"""

    _instance = None
    _pool = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host: str, port: int, database: str,
                 user: str, password: str, pool_size: int = 10):
        """初始化连接池"""
        if self._pool is None:
            conninfo = f"host={host} port={port} dbname={database} user={user} password={password}"
            self._pool = ConnectionPool(conninfo, min_size=2, max_size=pool_size)
            logger.info(f"TimescaleDB连接池已创建 | host={host} | db={database}")

    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        return self._pool.connection()

    def close(self):
        """关闭连接池"""
        if self._pool:
            self._pool.close()
            logger.info("TimescaleDB连接池已关闭")

class KlineRepository:
    """K线数据访问接口"""

    def __init__(self, db_client: TimescaleDBClient):
        self.db = db_client

    def get_data_coverage(self, symbol: str, timeframe: str,
                         start: datetime, end: datetime) -> Dict:
        """
        检查数据覆盖范围，返回缺失的时间段

        Returns:
            {
                'total_expected': 720,  # 期望的K线数量
                'stored_count': 650,    # 已存储的数量
                'missing_ranges': [(start1, end1), (start2, end2)],  # 缺失时间段
                'coverage_rate': 0.903  # 覆盖率
            }
        """
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # 查询已存储的K线数量
                cur.execute("""
                    SELECT COUNT(*), MIN(time), MAX(time)
                    FROM klines
                    WHERE symbol = %s AND timeframe = %s
                        AND time >= %s AND time <= %s
                """, (symbol, timeframe, start, end))

                stored_count, db_start, db_end = cur.fetchone()

                # 计算期望的K线数量（基于timeframe）
                timeframe_minutes = self._timeframe_to_minutes(timeframe)
                total_minutes = (end - start).total_seconds() / 60
                total_expected = int(total_minutes / timeframe_minutes) + 1

                # 检测缺失时间段（简化实现：首尾缺失检测）
                missing_ranges = []
                if stored_count == 0:
                    missing_ranges = [(start, end)]
                else:
                    if db_start > start:
                        missing_ranges.append((start, db_start - timedelta(minutes=timeframe_minutes)))
                    if db_end < end:
                        missing_ranges.append((db_end + timedelta(minutes=timeframe_minutes), end))

                coverage_rate = stored_count / total_expected if total_expected > 0 else 0

                return {
                    'total_expected': total_expected,
                    'stored_count': stored_count,
                    'missing_ranges': missing_ranges,
                    'coverage_rate': coverage_rate
                }

    def batch_upsert(self, df: pd.DataFrame, symbol: str, timeframe: str) -> int:
        """
        批量插入或更新K线数据（使用ON CONFLICT处理重复）

        Returns:
            插入的记录数
        """
        if df.empty:
            return 0

        records = []
        for timestamp, row in df.iterrows():
            records.append((
                timestamp,
                symbol,
                timeframe,
                float(row['Open']),
                float(row['High']),
                float(row['Low']),
                float(row['Close']),
                float(row['Volume']),
                float(row.get('volume_usd', 0)),
                float(row.get('return', 0))
            ))

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # 使用ON CONFLICT DO UPDATE处理重复数据
                insert_sql = """
                    INSERT INTO klines (time, symbol, timeframe, open, high, low, close, volume, volume_usd, return_pct)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (time, symbol, timeframe)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        volume_usd = EXCLUDED.volume_usd,
                        return_pct = EXCLUDED.return_pct
                """
                cur.executemany(insert_sql, records)
                conn.commit()

        logger.info(f"K线数据已保存 | symbol={symbol} | timeframe={timeframe} | records={len(records)}")
        return len(records)

    def query_range(self, symbol: str, timeframe: str,
                   start: datetime, end: datetime) -> pd.DataFrame:
        """
        查询指定时间范围的K线数据

        Returns:
            DataFrame with columns: [Open, High, Low, Close, Volume, volume_usd, return]
        """
        with self.db.get_connection() as conn:
            query = """
                SELECT time, open, high, low, close, volume, volume_usd, return_pct
                FROM klines
                WHERE symbol = %s AND timeframe = %s
                    AND time >= %s AND time <= %s
                ORDER BY time ASC
            """
            df = pd.read_sql_query(query, conn, params=(symbol, timeframe, start, end))

        if df.empty:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume', 'volume_usd', 'return'])

        # 转换为符合代码期望的格式
        df = df.rename(columns={
            'time': 'Timestamp',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
            'return_pct': 'return'
        })
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
        df = df.set_index('Timestamp').sort_index()

        return df

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        """时间周期转分钟数（复用DelayCorrelationAnalyzer的逻辑）"""
        unit_multipliers = {'m': 1, 'h': 60, 'd': 24 * 60, 'w': 7 * 24 * 60}
        unit = timeframe[-1].lower()
        value = int(timeframe[:-1])
        return value * unit_multipliers[unit]

class AnalysisResultRepository:
    """分析结果数据访问接口"""

    def __init__(self, db_client: TimescaleDBClient):
        self.db = db_client

    def save_result(self, result_data: Dict) -> int:
        """
        保存分析结果

        Args:
            result_data: {
                'symbol': 'ETH/USDC:USDC',
                'base_symbol': 'BTC/USDC:USDC',
                'corr_5m_7d': 0.75,
                'corr_1h_30d': 0.82,
                'corr_4h_60d': 0.88,
                'zscore_5m': 2.1,
                'zscore_1h': 1.8,
                'zscore_4h': 1.5,
                'cointegration_passed': True,
                'adf_pvalue': 0.023,
                'is_anomaly': True,
                'trading_direction': 'short_alt_long_base',
                'signal_strength': 'strong'
            }

        Returns:
            插入记录的ID
        """
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                insert_sql = """
                    INSERT INTO analysis_results (
                        analysis_time, symbol, base_symbol,
                        corr_5m_7d, corr_1h_30d, corr_4h_60d,
                        zscore_5m, zscore_1h, zscore_4h,
                        cointegration_passed, adf_pvalue,
                        is_anomaly, trading_direction, signal_strength
                    ) VALUES (
                        NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING id
                """
                cur.execute(insert_sql, (
                    result_data['symbol'],
                    result_data['base_symbol'],
                    result_data.get('corr_5m_7d'),
                    result_data.get('corr_1h_30d'),
                    result_data.get('corr_4h_60d'),
                    result_data.get('zscore_5m'),
                    result_data.get('zscore_1h'),
                    result_data.get('zscore_4h'),
                    result_data.get('cointegration_passed'),
                    result_data.get('adf_pvalue'),
                    result_data.get('is_anomaly', False),
                    result_data.get('trading_direction'),
                    result_data.get('signal_strength')
                ))
                result_id = cur.fetchone()[0]
                conn.commit()

        logger.info(f"分析结果已保存 | symbol={result_data['symbol']} | id={result_id}")
        return result_id

    def get_recent_anomalies(self, hours: int = 24) -> pd.DataFrame:
        """获取最近N小时的异常信号"""
        with self.db.get_connection() as conn:
            query = """
                SELECT
                    analysis_time, symbol,
                    corr_4h_60d, zscore_4h,
                    trading_direction, signal_strength
                FROM analysis_results
                WHERE is_anomaly = TRUE
                    AND analysis_time >= NOW() - INTERVAL '%s hours'
                ORDER BY analysis_time DESC
            """
            return pd.read_sql_query(query, conn, params=(hours,))
```

### 2. multi_coins3.py 修改要点

#### 2.1 初始化部分（第153-176行）

```python
def __init__(self, exchange_name="hyperliquid", timeout=30000,
             default_combinations=None, enable_db=True):
    """
    新增参数:
        enable_db: 是否启用TimescaleDB（默认True）
    """
    # 原有初始化代码...

    # 新增：初始化TimescaleDB客户端
    self.enable_db = enable_db
    self.db_client = None
    self.kline_repo = None
    self.analysis_repo = None

    if self.enable_db:
        from utils.timescaledb import TimescaleDBClient, KlineRepository, AnalysisResultRepository
        from utils.config import (
            timescaledb_host, timescaledb_port, timescaledb_name,
            timescaledb_user, timescaledb_password, timescaledb_pool_size
        )

        try:
            self.db_client = TimescaleDBClient(
                host=timescaledb_host,
                port=timescaledb_port,
                database=timescaledb_name,
                user=timescaledb_user,
                password=timescaledb_password,
                pool_size=timescaledb_pool_size
            )
            self.kline_repo = KlineRepository(self.db_client)
            self.analysis_repo = AnalysisResultRepository(self.db_client)
            logger.info("TimescaleDB已启用并成功连接")
        except Exception as e:
            logger.warning(f"TimescaleDB连接失败，降级为纯API模式: {e}")
            self.enable_db = False
```

#### 2.2 数据下载方法改造（第257-303行）

```python
@retry(tries=10, delay=5, backoff=2, logger=logger)
def download_ccxt_data(self, symbol: str, period: str, timeframe: str) -> pd.DataFrame:
    """
    改造逻辑：
    1. 如果启用DB，检查数据覆盖范围
    2. 仅下载缺失的时间段
    3. 合并数据库数据和API数据
    4. 保存新数据到数据库
    """
    # 计算目标时间范围
    target_bars = self._period_to_bars(period, timeframe)
    ms_per_bar = self._timeframe_to_minutes(timeframe) * 60 * 1000
    now_ms = self.exchange.milliseconds()
    target_start = datetime.fromtimestamp((now_ms - target_bars * ms_per_bar) / 1000, tz=timezone.utc)
    target_end = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)

    # 如果启用数据库，先尝试从数据库获取
    if self.enable_db and self.kline_repo:
        # 1. 检查数据覆盖情况
        coverage = self.kline_repo.get_data_coverage(symbol, timeframe, target_start, target_end)

        logger.info(
            f"数据覆盖检查 | symbol={symbol} | timeframe={timeframe} | "
            f"覆盖率={coverage['coverage_rate']:.1%} | "
            f"已存储={coverage['stored_count']}/{coverage['total_expected']}条"
        )

        # 2. 如果覆盖率>=95%，直接从数据库读取
        if coverage['coverage_rate'] >= 0.95:
            logger.info(f"数据库数据充足，跳过API调用 | symbol={symbol}")
            db_df = self.kline_repo.query_range(symbol, timeframe, target_start, target_end)
            return db_df

        # 3. 如果有缺失，下载缺失时间段
        all_data_parts = []

        # 先获取已有数据
        if coverage['stored_count'] > 0:
            db_df = self.kline_repo.query_range(symbol, timeframe, target_start, target_end)
            all_data_parts.append(db_df)
            logger.info(f"从数据库获取 {len(db_df)} 条历史数据")

        # 下载缺失数据
        for missing_start, missing_end in coverage['missing_ranges']:
            logger.info(f"下载缺失数据段 | {missing_start} 至 {missing_end}")
            api_df = self._download_from_api(symbol, timeframe, missing_start, missing_end)

            if not api_df.empty:
                all_data_parts.append(api_df)
                # 保存到数据库
                self.kline_repo.batch_upsert(api_df, symbol, timeframe)

        # 合并所有数据
        if all_data_parts:
            final_df = pd.concat(all_data_parts).sort_index()
            final_df = final_df[~final_df.index.duplicated(keep='last')]  # 去重
            return final_df

    # 降级：如果数据库未启用，使用原有API逻辑
    logger.debug(f"使用纯API模式下载数据 | symbol={symbol}")
    api_df = self._download_from_api(symbol, timeframe, target_start, target_end)

    # 如果数据库可用，保存数据
    if self.enable_db and self.kline_repo and not api_df.empty:
        self.kline_repo.batch_upsert(api_df, symbol, timeframe)

    return api_df

def _download_from_api(self, symbol: str, timeframe: str,
                       start: datetime, end: datetime) -> pd.DataFrame:
    """
    从API下载指定时间范围的数据（原download_ccxt_data的核心逻辑）
    """
    # 原有的API下载逻辑（第278-302行的代码）
    since = int(start.timestamp() * 1000)
    all_rows = []

    while True:
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1500)
        if not ohlcv:
            break

        all_rows.extend(ohlcv)
        since = ohlcv[-1][0] + 1

        if len(ohlcv) < 1500:
            break

        time.sleep(1.5)

    if not all_rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "return", "volume_usd"])

    df = pd.DataFrame(all_rows, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="ms", utc=True).dt.tz_convert(None)
    df = df.set_index("Timestamp").sort_index()
    df['return'] = df['Close'].pct_change().fillna(0)
    df['volume_usd'] = df['Volume'] * df['Close']

    return df
```

#### 2.3 分析结果保存（第1322-1424行 one_coin_analysis方法）

```python
def one_coin_analysis(self, coin: str) -> bool:
    """
    在方法末尾添加分析结果保存逻辑
    """
    # ... 原有分析逻辑 ...

    # 如果发现异常模式，保存分析结果
    if is_anomaly and zscore_result_list:
        zscore_result = zscore_result_list[np.argmax(np.abs(zscore_result_list))]
        self._output_results(coin, valid_results, diff_amount, zscore=zscore_result)

        # 新增：保存到数据库
        if self.enable_db and self.analysis_repo:
            try:
                # 提取相关系数数据
                corr_map = {f"{r[1]}_{r[2]}": r[0] for r in valid_results}

                result_data = {
                    'symbol': coin,
                    'base_symbol': self.base_symbol,
                    'corr_5m_7d': corr_map.get('5m_7d'),
                    'corr_1h_30d': corr_map.get('1h_30d'),
                    'corr_4h_60d': corr_map.get('4h_60d'),
                    'zscore_5m': zscore_result_list[0] if len(zscore_result_list) > 0 else None,
                    'zscore_1h': zscore_result_list[1] if len(zscore_result_list) > 1 else None,
                    'zscore_4h': zscore_result_list[2] if len(zscore_result_list) > 2 else None,
                    'cointegration_passed': True,  # 已通过协整检验才会进入此分支
                    'adf_pvalue': None,  # 可从前面保存的结果中提取
                    'is_anomaly': True,
                    'trading_direction': self._get_trading_direction(zscore_result, coin)[1],
                    'signal_strength': 'strong' if abs(zscore_result) > 2.0 else 'medium'
                }

                self.analysis_repo.save_result(result_data)
            except Exception as e:
                logger.warning(f"分析结果保存失败 | coin={coin} | error={e}")

        return True

    # ... 原有返回逻辑 ...
```

### 3. utils/config.py 修改

```python
import os

ENV = os.getenv("ENV", "local")

# 飞书配置
lark_bot_id = os.getenv("LARKBOT_ID")

# Redis配置
redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
redis_password = os.getenv("REDIS_PASSWORD")

# 新增：TimescaleDB配置
timescaledb_host = os.getenv("TIMESCALEDB_HOST", "127.0.0.1")
timescaledb_port = int(os.getenv("TIMESCALEDB_PORT", "5432"))
timescaledb_name = os.getenv("TIMESCALEDB_NAME", "crypto_data")
timescaledb_user = os.getenv("TIMESCALEDB_USER", "postgres")
timescaledb_password = os.getenv("TIMESCALEDB_PASSWORD", "postgres")
timescaledb_pool_size = int(os.getenv("TIMESCALEDB_POOL_SIZE", "10"))
```

### 4. pyproject.toml 修改

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
    "psycopg[binary]>=3.2.0",      # 新增：PostgreSQL驱动
    "psycopg-pool>=3.2.0",         # 新增：连接池
]
```

### 5. Docker Compose配置

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
      POSTGRES_PASSWORD: postgres
      TIMESCALEDB_TELEMETRY: "off"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./init_timescaledb.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - crypto_network

volumes:
  timescaledb_data:
    driver: local

networks:
  crypto_network:
    driver: bridge
```

### 6. SQL初始化脚本

```sql
-- init_timescaledb.sql
-- TimescaleDB初始化脚本

-- 启用TimescaleDB扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 创建K线数据表
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

-- 创建分析结果表
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

-- 创建压缩策略（自动压缩7天前的数据）
ALTER TABLE klines SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,timeframe'
);

SELECT add_compression_policy('klines', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE analysis_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('analysis_results', INTERVAL '30 days', if_not_exists => TRUE);

-- 创建连续聚合视图（每日统计）
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

-- 授权（如果需要非postgres用户）
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
```

## 🚀 实施步骤

### Phase 1: 基础设施部署（预计30分钟）

1. **创建Docker配置**
   - 编写 `docker-compose.yml`
   - 编写 `init_timescaledb.sql`
   - 创建 `.env.example`

2. **启动TimescaleDB**
   ```bash
   docker-compose up -d
   docker-compose logs -f timescaledb  # 验证启动成功
   ```

3. **验证数据库**
   ```bash
   docker exec -it crypto_timescaledb psql -U postgres -d crypto_data
   \dt  # 列出表
   \d klines  # 查看表结构
   ```

### Phase 2: 代码实现（预计2小时）

1. **创建数据库模块**
   - 编写 `utils/timescaledb.py`
   - 单元测试（手动插入/查询验证）

2. **修改配置文件**
   - 更新 `utils/config.py`
   - 更新 `pyproject.toml`

3. **改造核心分析引擎**
   - 修改 `multi_coins3.py` 初始化方法
   - 重构 `download_ccxt_data` 方法
   - 添加分析结果保存逻辑

### Phase 3: 测试验证（预计1小时）

1. **单元测试**
   - 测试数据库连接
   - 测试K线增量更新
   - 测试分析结果保存

2. **集成测试**
   - 运行完整分析流程
   - 验证数据覆盖率检测
   - 验证API调用减少

3. **性能对比**
   - 首次运行（冷启动）：下载所有数据 + 写入数据库
   - 二次运行（热启动）：从数据库读取，预期API调用减少70%+

### Phase 4: 文档编写（预计30分钟）

1. **快速开始指南**
   - Docker启动命令
   - 环境变量配置
   - 常见问题排查

2. **数据库维护指南**
   - 数据备份/恢复
   - 性能监控查询
   - 手动清理旧数据

## 📊 性能预期

| 指标 | 首次运行 | 后续运行 | 改善幅度 |
|------|---------|---------|---------|
| API调用次数 | 150次 | ~40次 | -73% |
| 数据下载时间 | 5-10分钟 | 1-2分钟 | -70% |
| 内存占用 | ~500MB | ~200MB | -60% |
| 历史数据可用性 | 无 | 90天滚动窗口 | ∞ |

## 🔍 验证标准

### 功能验证

- [ ] Docker Compose一键启动数据库
- [ ] 首次运行成功下载并存储K线数据
- [ ] 二次运行从数据库读取数据，API调用显著减少
- [ ] 分析结果成功保存到 `analysis_results` 表
- [ ] 数据保留策略正常工作（90天自动清理）

### 性能验证

- [ ] 数据覆盖率检测准确（容错±5%）
- [ ] 批量插入性能 >1000条/秒
- [ ] 查询响应时间 <100ms（单个币种+周期）
- [ ] 压缩策略生效（压缩率 >50%）

### 代码质量

- [ ] 所有数据库操作使用连接池
- [ ] 完整的异常处理和日志记录
- [ ] 数据库连接失败时优雅降级到纯API模式
- [ ] 代码风格与现有项目一致

## 🛡️ 风险与降级策略

| 风险 | 影响 | 降级方案 |
|------|------|---------|
| 数据库连接失败 | 无法使用持久化 | 自动降级为纯API模式，程序正常运行 |
| 数据覆盖率检测错误 | 重复下载数据 | 设置容错阈值，记录日志但不阻塞 |
| 批量插入性能低 | 数据保存慢 | 调整批次大小，异步写入 |
| Docker部署失败 | 无法快速启动 | 提供手动安装SQL脚本 |

## 📚 关键文件路径

```
hyperliquid-pair-hype-purr-analyze/
├── utils/
│   ├── config.py                    # 修改：添加TimescaleDB配置
│   └── timescaledb.py               # 新增：数据库访问层
├── multi_coins3.py                  # 修改：集成数据库逻辑
├── pyproject.toml                   # 修改：添加psycopg依赖
├── docker-compose.yml               # 新增：数据库容器配置
├── init_timescaledb.sql             # 新增：数据库初始化脚本
├── .env.example                     # 新增：环境变量示例
├── README_TIMESCALEDB.md            # 新增：使用文档
└── migrations/
    └── 001_initial_schema.sql       # 新增：迁移脚本备份
```

---

# 🚀 扩展功能：实时WebSocket数据流集成

基于 [strong-hyperliquid-websocket](https://github.com/zhajingwen/strong-hyperliquid-websocket) 项目集成实时K线数据流。

## 📋 实时数据流需求

1. **实时K线订阅**: 订阅多个币种的实时K线更新
2. **数据库实时写入**: 接收到K线数据后立即写入TimescaleDB
3. **实时分析触发**（可选）: 检测套利信号并发送飞书告警
4. **独立进程运行**: WebSocket服务与分析引擎解耦

## 🗄️ Hyperliquid K线数据格式

根据 [Hyperliquid官方文档](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)：

```json
{
  "channel": "candle",
  "data": {
    "t": 1704067260000,      // 开盘时间（毫秒）
    "T": 1704067319999,      // 收盘时间（毫秒）
    "s": "ETH",              // 币种符号
    "i": "1m",               // 时间周期
    "o": "2295.5",           // 开盘价
    "h": "2296.8",           // 最高价
    "l": "2295.2",           // 最低价
    "c": "2296.3",           // 收盘价
    "v": "1234.56",          // 成交量
    "n": 156                 // 交易次数
  }
}
```

**支持的时间周期**: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d

## 📁 新增文件清单（实时数据流）

### 7. **`realtime_kline_service.py`** (约200行)
   - WebSocket连接管理
   - K线数据接收和解析
   - 实时写入TimescaleDB
   - 可选的实时分析触发

### 8. **`requirements_websocket.txt`** (约5行)
   - strong-hyperliquid-websocket依赖声明

### 9. **`docker-compose.yml`** (更新)
   - 添加realtime-kline服务容器

## 🔧 实时服务实现设计

### realtime_kline_service.py

```python
"""
实时K线数据服务

功能：
1. 订阅Hyperliquid WebSocket K线数据
2. 实时写入TimescaleDB
3. 可选：触发实时套利信号检测
"""

import sys
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd
from hyperliquid.utils import constants

# 导入strong-hyperliquid-websocket（需要先安装项目）
sys.path.append('./strong-hyperliquid-websocket')
from enhanced_ws_manager import EnhancedWebSocketManager

# 导入项目模块
from utils.timescaledb import TimescaleDBClient, KlineRepository
from utils.config import (
    timescaledb_host, timescaledb_port, timescaledb_name,
    timescaledb_user, timescaledb_password
)
from utils.lark_bot import sender
from utils.config import lark_bot_id

logger = logging.getLogger('RealtimeKlineService')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class RealtimeKlineService:
    """实时K线数据服务"""

    def __init__(self, symbols: List[str], timeframes: List[str],
                 enable_realtime_analysis: bool = False):
        """
        初始化实时K线服务

        Args:
            symbols: 订阅的币种列表，如 ["BTC", "ETH", "SOL"]
            timeframes: 订阅的时间周期，如 ["1m", "5m", "1h"]
            enable_realtime_analysis: 是否启用实时分析（Z-score检测）
        """
        self.symbols = symbols
        self.timeframes = timeframes
        self.enable_realtime_analysis = enable_realtime_analysis

        # 初始化TimescaleDB客户端
        self.db_client = TimescaleDBClient(
            host=timescaledb_host,
            port=timescaledb_port,
            database=timescaledb_name,
            user=timescaledb_user,
            password=timescaledb_password
        )
        self.kline_repo = KlineRepository(self.db_client)

        # 飞书Webhook
        self.lark_hook = f'https://open.feishu.cn/open-apis/bot/v2/hook/{lark_bot_id}' if lark_bot_id else None

        # 构建WebSocket订阅列表
        self.subscriptions = self._build_subscriptions()

        # 初始化WebSocket管理器
        self.ws_manager = None

        logger.info(f"实时K线服务已初始化 | 币种: {len(symbols)} | 周期: {timeframes}")

    def _build_subscriptions(self) -> List[Dict]:
        """构建WebSocket订阅配置"""
        subscriptions = []
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                subscriptions.append({
                    "type": "candle",
                    "coin": symbol,
                    "interval": timeframe
                })
        logger.info(f"构建订阅配置 | 总订阅数: {len(subscriptions)}")
        return subscriptions

    def on_message(self, msg: Dict):
        """
        WebSocket消息回调处理

        Args:
            msg: Hyperliquid WebSocket消息
                格式：{"channel": "candle", "data": {...}}
        """
        try:
            channel = msg.get("channel")
            if channel != "candle":
                return

            data = msg.get("data", {})

            # 解析K线数据
            kline = self._parse_kline_data(data)
            if not kline:
                return

            # 写入数据库
            self._save_to_database(kline)

            # 可选：实时分析
            if self.enable_realtime_analysis:
                self._trigger_realtime_analysis(kline)

        except Exception as e:
            logger.error(f"消息处理失败: {type(e).__name__}: {str(e)}", exc_info=True)

    def _parse_kline_data(self, data: Dict) -> Optional[Dict]:
        """
        解析Hyperliquid K线数据为标准格式

        Args:
            data: WebSocket原始数据
                {
                    "t": 时间戳（毫秒）,
                    "s": "ETH",
                    "i": "1m",
                    "o": "2295.5",
                    "h": "2296.8",
                    "l": "2295.2",
                    "c": "2296.3",
                    "v": "1234.56",
                    "n": 156
                }

        Returns:
            标准化的K线数据字典
        """
        try:
            # 构建完整的交易对名称（Hyperliquid格式）
            symbol_full = f"{data['s']}/USDC:USDC"

            # 转换时间戳（毫秒 → datetime）
            timestamp = datetime.fromtimestamp(data['t'] / 1000, tz=timezone.utc)

            # 转换价格和成交量
            open_price = float(data['o'])
            high_price = float(data['h'])
            low_price = float(data['l'])
            close_price = float(data['c'])
            volume = float(data['v'])

            kline = {
                'timestamp': timestamp,
                'symbol': symbol_full,
                'timeframe': data['i'],
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
                'volume_usd': volume * close_price,
                'return_pct': 0.0  # 实时计算收益率需要前一根K线数据
            }

            logger.debug(f"K线数据解析成功 | {symbol_full} | {data['i']} | close={close_price}")
            return kline

        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"K线数据解析失败: {e} | data={data}")
            return None

    def _save_to_database(self, kline: Dict):
        """
        保存K线数据到TimescaleDB

        Args:
            kline: 标准化的K线数据
        """
        try:
            # 构建DataFrame（单行）
            df = pd.DataFrame([{
                'Timestamp': kline['timestamp'],
                'Open': kline['open'],
                'High': kline['high'],
                'Low': kline['low'],
                'Close': kline['close'],
                'Volume': kline['volume'],
                'volume_usd': kline['volume_usd'],
                'return': kline['return_pct']
            }])
            df = df.set_index('Timestamp')

            # 批量插入（单条记录）
            inserted = self.kline_repo.batch_upsert(
                df,
                symbol=kline['symbol'],
                timeframe=kline['timeframe']
            )

            if inserted > 0:
                logger.info(
                    f"✅ K线已保存 | {kline['symbol']} | {kline['timeframe']} | "
                    f"close={kline['close']:.2f} | time={kline['timestamp']}"
                )

        except Exception as e:
            logger.error(f"数据库写入失败: {e} | kline={kline}", exc_info=True)

    def _trigger_realtime_analysis(self, kline: Dict):
        """
        触发实时分析（可选功能）

        检测当前K线是否触发套利信号，如果触发则发送飞书告警。

        注意：实时分析需要足够的历史数据，建议数据库至少已存储60天数据。
        """
        # TODO: 实现实时Z-score计算逻辑
        # 1. 从数据库获取最近N根K线（如100根）
        # 2. 计算实时Z-score
        # 3. 如果超过阈值，发送飞书告警

        # 示例伪代码：
        # if abs(zscore) > 2.0 and self.lark_hook:
        #     message = f"🚨 实时套利信号 | {kline['symbol']} | Z-score={zscore:.2f}"
        #     sender(message, self.lark_hook)

        pass

    def on_state_change(self, old_state: str, new_state: str):
        """
        WebSocket连接状态变化回调

        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        logger.info(f"WebSocket状态变化: {old_state} → {new_state}")

        if new_state == "connected":
            logger.info("✅ WebSocket已连接，开始接收实时数据")
        elif new_state == "disconnected":
            logger.warning("⚠️ WebSocket已断开，等待重连...")
        elif new_state == "error":
            logger.error("❌ WebSocket连接错误")

    def start(self):
        """启动实时K线服务（阻塞运行）"""
        logger.info("🚀 启动实时K线服务...")

        # 创建WebSocket管理器
        self.ws_manager = EnhancedWebSocketManager(
            base_url=constants.MAINNET_API_URL,
            subscriptions=self.subscriptions,
            message_callback=self.on_message,
            on_state_change=self.on_state_change,
            timeout=30  # 30秒无数据超时
        )

        # 启动WebSocket（阻塞运行）
        try:
            self.ws_manager.start()
        except KeyboardInterrupt:
            logger.info("接收到中断信号，停止服务...")
            self.stop()
        except Exception as e:
            logger.error(f"服务运行异常: {e}", exc_info=True)
            self.stop()

    def stop(self):
        """停止实时K线服务"""
        logger.info("停止实时K线服务...")
        if self.ws_manager:
            self.ws_manager.stop()
        if self.db_client:
            self.db_client.close()
        logger.info("✅ 服务已停止")


def main():
    """主函数：配置和启动实时服务"""

    # 配置1: 订阅币种（可从数据库动态获取或硬编码）
    WATCHED_SYMBOLS = [
        "BTC", "ETH", "SOL", "ARB", "OP", "AVAX",
        "MATIC", "DOGE", "SHIB", "APE"
    ]

    # 配置2: 订阅时间周期（建议与分析引擎一致）
    TIMEFRAMES = ["5m", "1h", "4h"]

    # 配置3: 是否启用实时分析
    ENABLE_REALTIME_ANALYSIS = False  # 默认关闭，需要足够历史数据

    # 创建并启动服务
    service = RealtimeKlineService(
        symbols=WATCHED_SYMBOLS,
        timeframes=TIMEFRAMES,
        enable_realtime_analysis=ENABLE_REALTIME_ANALYSIS
    )

    service.start()


if __name__ == "__main__":
    main()
```

## 🐳 Docker Compose集成

更新 `docker-compose.yml` 添加实时服务容器：

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
      POSTGRES_PASSWORD: postgres
      TIMESCALEDB_TELEMETRY: "off"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./init_timescaledb.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - crypto_network

  # 新增：实时K线数据服务
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
      TIMESCALEDB_PASSWORD: postgres
      LARKBOT_ID: ${LARKBOT_ID}
    volumes:
      - ./realtime_kline_service.py:/app/realtime_kline_service.py
      - ./utils:/app/utils
    networks:
      - crypto_network
    command: python realtime_kline_service.py

volumes:
  timescaledb_data:
    driver: local

networks:
  crypto_network:
    driver: bridge
```

### Dockerfile.realtime

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制项目依赖
COPY pyproject.toml ./
COPY requirements_websocket.txt ./

# 安装Python依赖
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r requirements_websocket.txt

# 克隆并安装strong-hyperliquid-websocket
RUN git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git && \
    cd strong-hyperliquid-websocket && \
    pip install --no-cache-dir -e .

# 复制应用代码
COPY . .

CMD ["python", "realtime_kline_service.py"]
```

### requirements_websocket.txt

```txt
# strong-hyperliquid-websocket依赖
hyperliquid-python-sdk>=0.21.0
websockets>=12.0
```

## 📊 实时数据流架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   Hyperliquid Exchange                       │
│                  WebSocket API (wss://)                      │
└──────────────────┬──────────────────────────────────────────┘
                   │ 实时K线推送
                   │ (1m, 5m, 1h, 4h)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│          realtime_kline_service.py (独立进程)                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  EnhancedWebSocketManager (自动重连+健康检测)         │   │
│  └───────────────┬──────────────────────────────────────┘   │
│                  │                                           │
│                  ▼                                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  on_message() 回调                                    │   │
│  │  1. 解析K线数据（Hyperliquid → 标准格式）             │   │
│  │  2. 写入TimescaleDB                                   │   │
│  │  3. 可选：触发实时分析                                │   │
│  └───────────────┬──────────────────────────────────────┘   │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    TimescaleDB                               │
│  ┌──────────────────┐         ┌──────────────────┐          │
│  │  klines 表        │         │  实时分析结果     │          │
│  │  (实时更新)       │         │  (可选)          │          │
│  └──────────────────┘         └──────────────────┘          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│           multi_coins3.py (定时批量分析)                     │
│  - 从数据库读取历史K线                                       │
│  - 计算相关系数、Z-score                                    │
│  - 保存分析结果                                              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 部署和运行

### 方案1: Docker Compose一键部署（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置LARKBOT_ID等

# 2. 启动所有服务（数据库 + 实时K线）
docker-compose up -d

# 3. 查看实时日志
docker-compose logs -f realtime-kline

# 4. 验证数据写入
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data
SELECT symbol, timeframe, COUNT(*) as count, MAX(time) as latest_time
FROM klines
WHERE time >= NOW() - INTERVAL '1 hour'
GROUP BY symbol, timeframe
ORDER BY symbol, timeframe;
```

### 方案2: 独立进程运行

```bash
# 1. 安装依赖
pip install -e .
pip install -r requirements_websocket.txt

# 2. 克隆并安装WebSocket项目
git clone https://github.com/zhajingwen/strong-hyperliquid-websocket.git
cd strong-hyperliquid-websocket
pip install -e .
cd ..

# 3. 启动TimescaleDB（如果未启动）
docker-compose up -d timescaledb

# 4. 启动实时K线服务
python realtime_kline_service.py
```

## 📊 性能预期（实时数据流）

| 指标 | 预期值 | 说明 |
|------|--------|------|
| **延迟** | <500ms | WebSocket推送延迟 |
| **写入吞吐** | ~100条/秒 | 10币种 × 3周期 × 每分钟1根K线 |
| **数据库负载** | <10% CPU | TimescaleDB批量写入优化 |
| **内存占用** | ~100MB | 实时服务进程内存 |
| **数据新鲜度** | 实时 | K线闭合后立即写入 |

## 🔍 验证标准（实时数据流）

### 功能验证

- [ ] WebSocket成功连接Hyperliquid
- [ ] 订阅的所有币种都能接收到K线推送
- [ ] K线数据正确写入TimescaleDB
- [ ] 断线后自动重连成功
- [ ] 数据库中的K线时间戳连续无缺失

### 性能验证

- [ ] WebSocket消息延迟 <500ms
- [ ] 数据库写入无阻塞（无积压）
- [ ] 服务运行24小时无崩溃
- [ ] 内存无泄漏（稳定在100MB左右）

### 数据质量验证

- [ ] K线OHLC数据与Hyperliquid官方一致
- [ ] 成交量数据准确
- [ ] 无重复K线（主键冲突处理正确）
- [ ] 时间戳时区正确（UTC）

## 🛡️ 风险与降级策略（实时数据流）

| 风险 | 影响 | 降级方案 |
|------|------|---------|
| WebSocket长时间断线 | 实时数据中断 | 自动重连 + API补充缺失数据 |
| 数据库写入阻塞 | 实时数据积压 | 增加写入批次大小，异步写入队列 |
| 内存泄漏 | 服务崩溃 | 定时重启（cron任务） |
| Hyperliquid限流 | 连接被拒绝 | 减少订阅币种数量，增加重连延迟 |

## 🔄 实时分析触发逻辑（可选）

如果启用 `enable_realtime_analysis=True`，实时服务可以在每根K线闭合后立即检测套利信号：

```python
def _trigger_realtime_analysis(self, kline: Dict):
    """实时Z-score检测"""
    # 1. 从数据库获取最近100根K线
    end_time = kline['timestamp']
    start_time = end_time - timedelta(hours=24)  # 最近24小时

    base_df = self.kline_repo.query_range(
        symbol="BTC/USDC:USDC",
        timeframe=kline['timeframe'],
        start=start_time,
        end=end_time
    )

    alt_df = self.kline_repo.query_range(
        symbol=kline['symbol'],
        timeframe=kline['timeframe'],
        start=start_time,
        end=end_time
    )

    # 2. 计算实时Z-score（复用multi_coins3.py的逻辑）
    if len(base_df) >= 100 and len(alt_df) >= 100:
        zscore = self._calculate_zscore_realtime(base_df, alt_df)

        # 3. 检测阈值并发送告警
        if abs(zscore) > 2.0 and self.lark_hook:
            direction = "做空" if zscore > 0 else "做多"
            message = (
                f"🚨 实时套利信号\n"
                f"币种: {kline['symbol']}\n"
                f"周期: {kline['timeframe']}\n"
                f"Z-score: {zscore:.2f}\n"
                f"方向: {direction}\n"
                f"时间: {kline['timestamp']}"
            )
            sender(message, self.lark_hook)
            logger.info(f"✅ 实时信号已发送 | {kline['symbol']} | Z={zscore:.2f}")
```

**注意事项**：
- 实时分析需要数据库中有足够的历史数据（建议至少60天）
- 高频分析会增加数据库负载，建议仅在4h周期启用
- 可以添加防抖逻辑（如5分钟内同一币种仅告警一次）

## ⚙️ 可选优化项（后续迭代）

1. **异步IO支持**
   - 使用 `asyncpg` 替换 `psycopg` 提升并发性能
   - 需要重构为异步代码（工作量较大）

2. **数据质量监控**
   - 创建数据质量检查视图
   - 检测K线数据缺口和异常值

3. **高级分析视图**
   - 币种相关性热力图（基于历史数据）
   - 套利机会趋势分析

4. **实时数据流优化**
   - 消息队列缓冲（Redis/RabbitMQ）
   - 批量写入优化（累积N条后批量提交）
   - 多进程并发写入（按币种分片）

## ✅ 完成标准

### Phase 1-4: TimescaleDB基础集成

当满足以下所有条件时，认为基础功能实施完成：

1. ✅ 所有新增文件已创建并测试通过（utils/timescaledb.py等6个文件）
2. ✅ Docker Compose可一键启动数据库
3. ✅ `multi_coins3.py` 成功运行并验证增量更新
4. ✅ 数据库包含至少1个币种的完整K线数据
5. ✅ 分析结果表包含至少1条异常信号记录
6. ✅ README_TIMESCALEDB.md 文档完整可用
7. ✅ API调用次数相比原版减少 >60%

### Phase 5: 实时WebSocket数据流（可选扩展）

当满足以下所有条件时，认为实时数据流功能实施完成：

1. ✅ realtime_kline_service.py 已创建并独立运行
2. ✅ WebSocket成功连接Hyperliquid并接收K线推送
3. ✅ 实时K线数据正确写入TimescaleDB
4. ✅ Docker Compose包含realtime-kline服务容器
5. ✅ 服务运行24小时稳定无崩溃
6. ✅ 数据库中实时K线时间戳连续无缺失
7. ✅ 断线自动重连机制验证通过

### 优先级建议

- **必须完成**: Phase 1-4（TimescaleDB基础集成）
- **可选扩展**: Phase 5（实时数据流）
  - 如果需要实时监控套利机会 → 实施Phase 5
  - 如果仅需历史数据分析 → Phase 1-4已足够

### 实施顺序建议

1. **Week 1**: 完成Phase 1-2（基础设施 + 代码实现）
2. **Week 2**: 完成Phase 3-4（测试验证 + 文档）
3. **Week 3+**: 可选实施Phase 5（实时数据流）

总预计工作量：
- 基础功能（Phase 1-4）：**4小时**
- 实时数据流（Phase 5）：**额外6小时**
- 总计：**10小时**（含测试和文档）
