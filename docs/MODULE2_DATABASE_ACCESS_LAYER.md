# 模块2: 数据库访问层 (Database Access Layer)

## 📋 模块概述

负责实现高性能的数据库访问层，提供连接池管理、K线数据CRUD操作、币种元数据管理，以及PostgreSQL COPY命令的批量写入优化。

### 模块职责
- ✅ 连接池管理（psycopg ConnectionPool）
- ✅ K线数据CRUD操作（增删改查）
- ✅ 币种元数据管理（动态发现、数据质量追踪）
- ✅ COPY命令批量写入优化（10-100x性能提升）
- ✅ 数据覆盖率检测和增量更新支持
- ✅ 分析结果持久化

### 依赖关系
- **上游依赖**: 模块1（数据库必须已初始化）
- **下游依赖**: 模块3（实时数据流）、模块4（分析引擎）

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│              utils/timescaledb.py                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  TimescaleDBClient (连接池管理)                       │  │
│  │  - 单例模式                                           │  │
│  │  - psycopg ConnectionPool (2-10连接)                 │  │
│  │  - 自动重连                                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                             │                               │
│            ┌────────────────┼────────────────┐              │
│            │                │                │              │
│            ▼                ▼                ▼              │
│  ┌───────────────┐ ┌───────────────┐ ┌──────────────────┐ │
│  │ Kline         │ │ SymbolMetadata│ │ AnalysisResult   │ │
│  │ Repository    │ │ Repository    │ │ Repository       │ │
│  │               │ │               │ │                  │ │
│  │ - COPY批量写入│ │ - 动态币种发现│ │ - 分析结果保存   │ │
│  │ - 覆盖率检测  │ │ - 质量评估    │ │ - 异常信号查询   │ │
│  │ - 增量查询    │ │ - 新币监控    │ │ - 历史趋势分析   │ │
│  └───────────────┘ └───────────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
               ┌────────────────────────────┐
               │      TimescaleDB           │
               │  - klines表                │
               │  - symbol_metadata表       │
               │  - analysis_results表      │
               └────────────────────────────┘
```

## 📦 核心类设计

### 类1: TimescaleDBClient（连接池管理器）

**职责**: 管理数据库连接池，提供连接获取和释放

```python
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
```

**设计要点**:
- **单例模式**: 确保全局只有一个连接池实例
- **连接池配置**: min_size=2, max_size=10（可根据负载调整）
- **上下文管理器**: `with self.db.get_connection() as conn` 自动释放连接

---

### 类2: KlineRepository（K线数据访问）

**职责**: K线数据的增删改查，支持COPY命令批量写入和增量更新

#### 方法1: get_data_coverage() - 数据覆盖率检测

**功能**: 检查指定时间范围内的数据完整性，识别缺失时间段

```python
def get_data_coverage(self, symbol: str, timeframe: str,
                     start: datetime, end: datetime) -> Dict:
    """
    检查数据覆盖范围，返回缺失的时间段

    Returns:
        {
            'total_expected': 720,  # 期望的K线数量
            'stored_count': 650,    # 已存储的数量
            'missing_ranges': [(start1, end1), (start2, end2)],
            'coverage_rate': 0.903  # 覆盖率
        }
    """
```

**实现思路**:
1. 计算期望的K线数量（基于timeframe和时间范围）
2. 查询数据库中已存储的K线数量
3. 检测首尾缺失（简化实现，生产环境可使用窗口函数检测中间缺失）
4. 计算覆盖率：`stored_count / total_expected`

**SQL查询**:
```sql
SELECT COUNT(*), MIN(time), MAX(time)
FROM klines
WHERE symbol = %s AND timeframe = %s
    AND time >= %s AND time <= %s
```

---

#### 方法2: batch_upsert_copy() - COPY命令批量写入

**功能**: 使用PostgreSQL COPY命令实现10-100x性能提升的批量写入

```python
def batch_upsert_copy(self, records: List[tuple], symbol: str, timeframe: str) -> int:
    """
    使用COPY命令批量插入K线数据（10-100x faster）

    Args:
        records: [(timestamp, open, high, low, close, volume, volume_usd, return_pct), ...]
        symbol: 币种符号
        timeframe: 时间周期

    Returns:
        插入的记录数
    """
    if not records:
        return 0

    # 1. 准备CSV缓冲区
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)

    for ts, o, h, l, c, v, v_usd, ret in records:
        writer.writerow([
            ts.isoformat(),  # 时间戳（ISO格式）
            symbol,
            timeframe,
            o, h, l, c, v, v_usd, ret
        ])

    csv_buffer.seek(0)

    # 2. 使用COPY写入临时表
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            # 创建临时表（结构与klines表相同）
            cur.execute("CREATE TEMP TABLE temp_klines (LIKE klines) ON COMMIT DROP")

            # COPY数据到临时表（超高速）
            cur.copy_expert(
                "COPY temp_klines (time, symbol, timeframe, open, high, low, close, volume, volume_usd, return_pct) FROM STDIN WITH CSV",
                csv_buffer
            )

            # 3. 从临时表INSERT到主表（处理冲突）
            cur.execute("""
                INSERT INTO klines
                SELECT * FROM temp_klines
                ON CONFLICT (time, symbol, timeframe)
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    volume_usd = EXCLUDED.volume_usd,
                    return_pct = EXCLUDED.return_pct
            """)

            conn.commit()

    logger.info(f"COPY批量写入完成 | {symbol} | {timeframe} | {len(records)}条")
    return len(records)
```

**性能对比**:
| 方法 | 10000条记录 | 性能提升 |
|------|------------|---------|
| executemany() | 10-30秒 | 1x |
| COPY命令 | 0.1-0.3秒 | 100x |

---

#### 方法3: query_range() - 时间范围查询

**功能**: 查询指定时间范围内的K线数据，返回pandas DataFrame

```python
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
```

---

#### 方法4: get_latest_timestamp() - 最新时间戳查询

**功能**: 获取某币种某周期的最新K线时间戳，支持增量更新

```python
def get_latest_timestamp(self, symbol: str, timeframe: str) -> Optional[datetime]:
    """获取最新K线时间戳（用于增量更新）"""
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(time) FROM klines
                WHERE symbol = %s AND timeframe = %s
            """, (symbol, timeframe))

            result = cur.fetchone()
            return result[0] if result[0] else None
```

---

### 类3: SymbolMetadataRepository（币种元数据管理）

**职责**: 管理币种元数据，支持动态币种发现和数据质量评估

#### 方法1: upsert_symbol() - 币种信息更新

```python
def upsert_symbol(self, symbol: str, base_asset: str, quote_asset: str,
                 listing_time: Optional[datetime] = None) -> int:
    """
    插入或更新币种元数据

    Returns:
        symbol记录的ID
    """
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO symbol_metadata (symbol, base_asset, quote_asset, listing_time)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol)
                DO UPDATE SET
                    base_asset = EXCLUDED.base_asset,
                    quote_asset = EXCLUDED.quote_asset,
                    listing_time = COALESCE(EXCLUDED.listing_time, symbol_metadata.listing_time),
                    updated_at = NOW()
                RETURNING id
            """, (symbol, base_asset, quote_asset, listing_time))

            symbol_id = cur.fetchone()[0]
            conn.commit()

    return symbol_id
```

#### 方法2: update_data_quality() - 数据质量更新

```python
def update_data_quality(self, symbol: str, first_kline_time: datetime,
                       last_kline_time: datetime, total_klines: int):
    """
    更新币种的数据质量指标

    计算逻辑：
    - 预期K线数量 = (last_kline_time - first_kline_time) / timeframe_interval
    - 数据质量分数 = total_klines / 预期K线数量
    """
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            # 查询预期K线数量（简化：假设1分钟周期）
            expected_minutes = int((last_kline_time - first_kline_time).total_seconds() / 60)
            quality_score = min(1.0, total_klines / expected_minutes if expected_minutes > 0 else 0)

            cur.execute("""
                UPDATE symbol_metadata
                SET first_kline_time = %s,
                    last_kline_time = %s,
                    total_klines = %s,
                    data_quality_score = %s,
                    updated_at = NOW()
                WHERE symbol = %s
            """, (first_kline_time, last_kline_time, total_klines, quality_score, symbol))

            conn.commit()
```

#### 方法3: get_active_symbols() - 活跃币种查询

```python
def get_active_symbols(self) -> List[str]:
    """获取所有活跃币种列表"""
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol FROM symbol_metadata
                WHERE is_active = TRUE
                ORDER BY symbol ASC
            """)

            return [row[0] for row in cur.fetchall()]
```

---

### 类4: AnalysisResultRepository（分析结果持久化）

**职责**: 保存分析结果，支持异常信号查询和历史趋势分析

#### 方法1: save_result() - 保存分析结果

```python
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
            cur.execute("""
                INSERT INTO analysis_results (
                    analysis_time, symbol, base_symbol,
                    corr_5m_7d, corr_1h_30d, corr_4h_60d,
                    zscore_5m, zscore_1h, zscore_4h,
                    cointegration_passed, adf_pvalue,
                    is_anomaly, trading_direction, signal_strength
                ) VALUES (
                    NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
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

    logger.info(f"分析结果已保存 | {result_data['symbol']} | id={result_id}")
    return result_id
```

#### 方法2: get_recent_anomalies() - 异常信号查询

```python
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

## 🧪 单元测试

### 文件: tests/test_timescaledb.py

```python
import pytest
from datetime import datetime, timedelta, timezone
import pandas as pd
from utils.timescaledb import TimescaleDBClient, KlineRepository, SymbolMetadataRepository

@pytest.fixture
def db_client():
    """数据库客户端fixture"""
    client = TimescaleDBClient(
        host='localhost',
        port=5432,
        database='crypto_data_test',  # 使用测试数据库
        user='postgres',
        password='postgres'
    )
    yield client
    client.close()

@pytest.fixture
def kline_repo(db_client):
    return KlineRepository(db_client)

@pytest.fixture
def symbol_repo(db_client):
    return SymbolMetadataRepository(db_client)

class TestKlineRepository:
    """K线数据访问层测试"""

    def test_batch_upsert_copy_performance(self, kline_repo):
        """测试COPY命令批量写入性能"""
        # 准备10000条测试数据
        now = datetime.now(timezone.utc)
        records = []
        for i in range(10000):
            ts = now - timedelta(minutes=i)
            records.append((ts, 50000.0, 51000.0, 49000.0, 50500.0, 100.0, 5050000.0, 0.01))

        # 计时写入
        import time
        start_time = time.time()
        inserted = kline_repo.batch_upsert_copy(records, 'BTC/USDC:USDC', '1m')
        elapsed = time.time() - start_time

        assert inserted == 10000
        assert elapsed < 1.0  # 必须在1秒内完成
        print(f"✅ COPY写入10000条记录耗时: {elapsed:.3f}秒 ({int(10000/elapsed)}条/秒)")

    def test_get_data_coverage(self, kline_repo):
        """测试数据覆盖率检测"""
        # 插入部分数据（只有前50条）
        now = datetime.now(timezone.utc)
        records = [(now - timedelta(minutes=i), 50000.0, 51000.0, 49000.0, 50500.0, 100.0, 5050000.0, 0.01)
                   for i in range(50)]
        kline_repo.batch_upsert_copy(records, 'ETH/USDC:USDC', '1m')

        # 检查覆盖率（期望100条，实际50条）
        start = now - timedelta(minutes=100)
        end = now
        coverage = kline_repo.get_data_coverage('ETH/USDC:USDC', '1m', start, end)

        assert coverage['total_expected'] == 101  # 101条（0-100分钟）
        assert coverage['stored_count'] == 50
        assert abs(coverage['coverage_rate'] - 0.495) < 0.01  # ~49.5%
        print(f"✅ 数据覆盖率: {coverage['coverage_rate']:.1%}")

    def test_query_range(self, kline_repo):
        """测试时间范围查询"""
        now = datetime.now(timezone.utc)
        records = [(now - timedelta(minutes=i), 50000.0, 51000.0, 49000.0, 50500.0, 100.0, 5050000.0, 0.01)
                   for i in range(100)]
        kline_repo.batch_upsert_copy(records, 'SOL/USDC:USDC', '1m')

        # 查询最近50条
        start = now - timedelta(minutes=50)
        end = now
        df = kline_repo.query_range('SOL/USDC:USDC', '1m', start, end)

        assert len(df) == 51  # 51条（0-50分钟）
        assert df.index.name == 'Timestamp'
        assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume', 'volume_usd', 'return']
        print(f"✅ 查询返回 {len(df)} 条记录")

class TestSymbolMetadataRepository:
    """币种元数据测试"""

    def test_upsert_symbol(self, symbol_repo):
        """测试币种信息插入和更新"""
        # 首次插入
        symbol_id1 = symbol_repo.upsert_symbol('BTC/USDC:USDC', 'BTC', 'USDC')
        assert symbol_id1 > 0

        # 再次插入（应该更新）
        symbol_id2 = symbol_repo.upsert_symbol('BTC/USDC:USDC', 'BTC', 'USDC')
        assert symbol_id1 == symbol_id2  # ID相同，说明是更新而非插入
        print(f"✅ 币种元数据Upsert成功 | ID={symbol_id1}")

    def test_get_active_symbols(self, symbol_repo):
        """测试活跃币种查询"""
        # 插入3个币种
        symbol_repo.upsert_symbol('BTC/USDC:USDC', 'BTC', 'USDC')
        symbol_repo.upsert_symbol('ETH/USDC:USDC', 'ETH', 'USDC')
        symbol_repo.upsert_symbol('SOL/USDC:USDC', 'SOL', 'USDC')

        active_symbols = symbol_repo.get_active_symbols()
        assert len(active_symbols) >= 3
        assert 'BTC/USDC:USDC' in active_symbols
        print(f"✅ 活跃币种数量: {len(active_symbols)}")
```

### 运行测试

```bash
# 安装pytest
pip install pytest pytest-cov

# 创建测试数据库
docker exec -it crypto_timescaledb psql -U postgres -c "CREATE DATABASE crypto_data_test;"
docker exec -it crypto_timescaledb psql -U postgres -d crypto_data_test -f /docker-entrypoint-initdb.d/init.sql

# 运行测试
pytest tests/test_timescaledb.py -v --cov=utils.timescaledb --cov-report=term-missing

# 预期输出
# test_batch_upsert_copy_performance PASSED    [ 33%]
# ✅ COPY写入10000条记录耗时: 0.287秒 (34843条/秒)
# test_get_data_coverage PASSED                [ 66%]
# ✅ 数据覆盖率: 49.5%
# test_query_range PASSED                      [100%]
# ✅ 查询返回 51 条记录
# Coverage: 85%
```

## 📊 性能基准测试

### 基准1: COPY vs executemany()

```python
# 测试脚本: benchmarks/compare_write_methods.py

import time
from utils.timescaledb import TimescaleDBClient, KlineRepository

def benchmark_copy_command(records, iterations=10):
    """基准测试：COPY命令"""
    db_client = TimescaleDBClient('localhost', 5432, 'crypto_data', 'postgres', 'postgres')
    repo = KlineRepository(db_client)

    times = []
    for _ in range(iterations):
        start = time.time()
        repo.batch_upsert_copy(records, 'BENCH/USDC:USDC', '1m')
        times.append(time.time() - start)

    avg_time = sum(times) / len(times)
    throughput = len(records) / avg_time
    print(f"COPY命令: {avg_time:.3f}秒/万条 ({throughput:.0f}条/秒)")

def benchmark_executemany(records, iterations=10):
    """基准测试：executemany()"""
    # ... 类似实现，使用executemany()
    pass

# 运行基准测试
records = [(datetime.now(timezone.utc) - timedelta(minutes=i), 50000.0, 51000.0, 49000.0, 50500.0, 100.0, 5050000.0, 0.01)
           for i in range(10000)]

benchmark_copy_command(records)
benchmark_executemany(records)
```

**预期结果**:
| 方法 | 平均耗时 | 吞吐量 | 性能提升 |
|------|---------|--------|---------|
| COPY命令 | 0.25秒 | 40000条/秒 | 100x |
| executemany() | 25秒 | 400条/秒 | 1x |

### 基准2: 连接池性能

```python
# 测试脚本: benchmarks/test_connection_pool.py

import concurrent.futures
from utils.timescaledb import TimescaleDBClient

def concurrent_query(client, worker_id):
    """并发查询测试"""
    with client.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM klines WHERE symbol = 'BTC/USDC:USDC'")
            count = cur.fetchone()[0]
    return (worker_id, count)

# 测试10个并发连接
client = TimescaleDBClient('localhost', 5432, 'crypto_data', 'postgres', 'postgres', pool_size=10)

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(concurrent_query, client, i) for i in range(10)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

print(f"✅ {len(results)}个并发查询全部成功")
```

## ✅ 验收标准

- [ ] TimescaleDBClient单例正常工作
- [ ] 连接池支持10个并发连接
- [ ] COPY命令写入10000条记录<1秒
- [ ] batch_upsert_copy()吞吐量>1000条/秒
- [ ] get_data_coverage()准确检测缺失数据
- [ ] query_range()返回正确格式的DataFrame
- [ ] SymbolMetadataRepository正确管理币种元数据
- [ ] AnalysisResultRepository正确保存分析结果
- [ ] 单元测试覆盖率>80%
- [ ] 所有测试通过

## 📝 下一步

模块2完成后，继续实施：
- **模块4**: 分析引擎集成 (multi_coins.py改造)
- **模块3**: 实时数据流 (realtime_kline_service.py)

---

**版本**: v1.0
**日期**: 2025-01-11
**作者**: Claude Sonnet 4.5
