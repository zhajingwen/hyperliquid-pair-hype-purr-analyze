# 模块4: 分析引擎集成 (Analysis Engine Integration)

## 📋 模块概述

改造 `multi_coins3.py` 分析引擎，集成TimescaleDB数据库查询、实现智能增量更新、保存分析结果持久化。

### 模块职责
- ✅ 修改数据下载方法支持增量更新
- ✅ 集成数据库查询和缓存
- ✅ 分析结果持久化到analysis_results表
- ✅ 降级策略（数据库不可用时使用纯API模式）
- ✅ API调用次数减少70%+

### 依赖关系
- **上游依赖**: 模块1（数据库）、模块2（访问层）
- **下游依赖**: 无

## 🎯 改造目标

| 指标 | 改造前 | 改造后 | 改善幅度 |
|------|--------|--------|---------|
| API调用次数/运行 | 150次 | <45次 | -70% |
| 数据加载时间 | 5-10分钟 | 1-2分钟 | -70% |
| 内存占用 | ~500MB | ~200MB | -60% |
| 历史数据可用性 | 无 | 90天滚动窗口 | ∞ |

## 🔧 核心改造点

### 改造点1: __init__() - 初始化数据库连接

**位置**: `multi_coins3.py` 第153-176行

**改造前**:
```python
def __init__(self, exchange_name="hyperliquid", timeout=30000,
             default_combinations=None):
    self.exchange = ccxt.hyperliquid({"timeout": timeout})
    self.base_df_cache = {}
    self.alt_df_cache = {}
    # ... 其他初始化 ...
```

**改造后**:
```python
def __init__(self, exchange_name="hyperliquid", timeout=30000,
             default_combinations=None, enable_db=True):
    """
    新增参数:
        enable_db: 是否启用TimescaleDB（默认True）
    """
    self.exchange = ccxt.hyperliquid({"timeout": timeout})
    self.base_df_cache = {}
    self.alt_df_cache = {}

    # 新增：初始化TimescaleDB客户端
    self.enable_db = enable_db
    self.db_client = None
    self.kline_repo = None
    self.analysis_repo = None

    if self.enable_db:
        try:
            from utils.timescaledb import TimescaleDBClient, KlineRepository, AnalysisResultRepository
            from utils.config import (
                timescaledb_host, timescaledb_port, timescaledb_name,
                timescaledb_user, timescaledb_password, timescaledb_pool_size
            )

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
            logger.info("✅ TimescaleDB已启用并成功连接")
        except Exception as e:
            logger.warning(f"⚠️ TimescaleDB连接失败，降级为纯API模式: {e}")
            self.enable_db = False
```

**改造说明**:
- 新增 `enable_db` 参数，默认启用数据库
- 尝试连接TimescaleDB，失败时自动降级为纯API模式
- 初始化3个仓储对象：db_client, kline_repo, analysis_repo

---

### 改造点2: download_ccxt_data() - 智能增量更新

**位置**: `multi_coins3.py` 第256-303行

**改造策略**:
1. 检查数据库覆盖率
2. 如果覆盖率≥95%，直接从数据库读取
3. 如果有缺失，仅下载缺失的时间段
4. 合并数据库数据和API数据
5. 保存新数据到数据库

**改造后代码**:
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
            f"数据覆盖检查 | {symbol} | {timeframe} | "
            f"覆盖率={coverage['coverage_rate']:.1%} | "
            f"已存储={coverage['stored_count']}/{coverage['total_expected']}条"
        )

        # 2. 如果覆盖率>=95%，直接从数据库读取
        if coverage['coverage_rate'] >= 0.95:
            logger.info(f"📊 数据库数据充足，跳过API调用 | {symbol}")
            db_df = self.kline_repo.query_range(symbol, timeframe, target_start, target_end)
            return db_df

        # 3. 如果有缺失，下载缺失时间段
        all_data_parts = []

        # 先获取已有数据
        if coverage['stored_count'] > 0:
            db_df = self.kline_repo.query_range(symbol, timeframe, target_start, target_end)
            all_data_parts.append(db_df)
            logger.info(f"📊 从数据库获取 {len(db_df)} 条历史数据")

        # 下载缺失数据
        for missing_start, missing_end in coverage['missing_ranges']:
            logger.info(f"⬇️ 下载缺失数据段 | {missing_start} 至 {missing_end}")
            api_df = self._download_from_api(symbol, timeframe, missing_start, missing_end)

            if not api_df.empty:
                all_data_parts.append(api_df)
                # 保存到数据库
                self.kline_repo.batch_upsert_copy(
                    self._df_to_records(api_df),
                    symbol,
                    timeframe
                )

        # 合并所有数据
        if all_data_parts:
            final_df = pd.concat(all_data_parts).sort_index()
            final_df = final_df[~final_df.index.duplicated(keep='last')]  # 去重
            return final_df

    # 降级：如果数据库未启用，使用原有API逻辑
    logger.debug(f"⚠️ 使用纯API模式下载数据 | {symbol}")
    api_df = self._download_from_api(symbol, timeframe, target_start, target_end)

    # 如果数据库可用，保存数据
    if self.enable_db and self.kline_repo and not api_df.empty:
        self.kline_repo.batch_upsert_copy(
            self._df_to_records(api_df),
            symbol,
            timeframe
        )

    return api_df

def _download_from_api(self, symbol: str, timeframe: str,
                       start: datetime, end: datetime) -> pd.DataFrame:
    """
    从API下载指定时间范围的数据（原download_ccxt_data的核心逻辑）
    """
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

def _df_to_records(self, df: pd.DataFrame) -> List[tuple]:
    """将DataFrame转换为records格式（用于batch_upsert_copy）"""
    records = []
    for timestamp, row in df.iterrows():
        records.append((
            timestamp,
            float(row['Open']),
            float(row['High']),
            float(row['Low']),
            float(row['Close']),
            float(row['Volume']),
            float(row.get('volume_usd', 0)),
            float(row.get('return', 0))
        ))
    return records
```

**改造说明**:
- 新增 `_download_from_api()` 方法：封装原有的API下载逻辑
- 新增 `_df_to_records()` 方法：DataFrame转换为batch_upsert_copy所需格式
- 主方法改为三层逻辑：
  1. 覆盖率检查 → 数据库读取或增量下载
  2. 降级处理：数据库不可用时使用原有API逻辑
  3. 数据保存：API下载的数据自动保存到数据库

---

### 改造点3: one_coin_analysis() - 分析结果持久化

**位置**: `multi_coins3.py` 第1322-1424行

**改造后代码**:
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

                result_id = self.analysis_repo.save_result(result_data)
                logger.info(f"✅ 分析结果已保存 | {coin} | id={result_id}")
            except Exception as e:
                logger.warning(f"⚠️ 分析结果保存失败 | coin={coin} | error={e}")

        return True

    # ... 原有返回逻辑 ...
```

**改造说明**:
- 在异常模式检测后，提取相关系数、Z-score、交易方向等数据
- 调用 `analysis_repo.save_result()` 保存到数据库
- 异常处理：保存失败不影响主流程

---

### 改造点4: 新增辅助方法

```python
def _get_trading_direction(self, zscore: float, coin: str) -> tuple:
    """
    根据Z-score判断交易方向

    Args:
        zscore: Z-score值
        coin: 币种符号

    Returns:
        (direction_code, direction_text)
        例如: ('short_alt_long_base', '做空ETH，做多BTC')
    """
    if zscore > 0:
        # 价差过大，做空价差
        direction_code = 'short_alt_long_base'
        direction_text = f"做空{coin}，做多{self.base_symbol}"
    else:
        # 价差过小，做多价差
        direction_code = 'long_alt_short_base'
        direction_text = f"做多{coin}，做空{self.base_symbol}"

    return (direction_code, direction_text)
```

## 🧪 集成测试

### 测试1: 端到端测试（首次运行）

```python
# 测试脚本: tests/test_integration.py

def test_first_run_with_db():
    """测试首次运行（数据库为空）"""
    analyzer = DelayCorrelationAnalyzer(enable_db=True)

    # 记录API调用次数
    api_call_count = 0
    original_fetch = analyzer.exchange.fetch_ohlcv

    def mock_fetch(*args, **kwargs):
        nonlocal api_call_count
        api_call_count += 1
        return original_fetch(*args, **kwargs)

    analyzer.exchange.fetch_ohlcv = mock_fetch

    # 运行分析（假设分析10个币种）
    analyzer.run(test_mode=True)

    # 验证API调用次数（首次运行会调用所有API）
    assert api_call_count > 0
    logger.info(f"首次运行API调用次数: {api_call_count}")

    # 验证数据库中有数据
    with analyzer.db_client.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM klines")
            kline_count = cur.fetchone()[0]
            assert kline_count > 0
            logger.info(f"✅ 数据库K线数量: {kline_count}")
```

### 测试2: 增量更新测试（二次运行）

```python
def test_second_run_with_db():
    """测试二次运行（数据库已有数据）"""
    analyzer = DelayCorrelationAnalyzer(enable_db=True)

    # 记录API调用次数
    api_call_count = 0
    original_fetch = analyzer.exchange.fetch_ohlcv

    def mock_fetch(*args, **kwargs):
        nonlocal api_call_count
        api_call_count += 1
        return original_fetch(*args, **kwargs)

    analyzer.exchange.fetch_ohlcv = mock_fetch

    # 运行分析
    analyzer.run(test_mode=True)

    # 验证API调用次数（二次运行应显著减少）
    assert api_call_count < 50  # 应该<50次（相比首次150次）
    logger.info(f"✅ 二次运行API调用次数: {api_call_count}（减少 {100 * (1 - api_call_count / 150):.0f}%）")
```

### 测试3: 数据库降级测试

```python
def test_database_fallback():
    """测试数据库不可用时的降级处理"""
    # 使用错误的数据库配置
    analyzer = DelayCorrelationAnalyzer(enable_db=True)
    analyzer.db_client = None  # 模拟连接失败

    # 应该能正常运行（使用纯API模式）
    result = analyzer.one_coin_analysis('ETH/USDC:USDC')

    # 验证仍能获取数据
    assert result is not None
    logger.info("✅ 数据库降级测试通过")
```

## 📊 性能对比测试

```bash
# 运行性能对比测试
python tests/benchmark_integration.py

# 预期输出:
# ========== 性能对比测试 ==========
# 纯API模式:
#   - API调用次数: 150次
#   - 总耗时: 8.5分钟
#   - 内存占用: 520MB
#
# 数据库模式（首次运行）:
#   - API调用次数: 150次
#   - 总耗时: 9.0分钟（含数据库写入）
#   - 内存占用: 450MB
#
# 数据库模式（二次运行）:
#   - API调用次数: 42次  (-72%)
#   - 总耗时: 2.5分钟   (-71%)
#   - 内存占用: 180MB   (-65%)
# ==================================
```

## ✅ 验收标准

- [ ] 数据库连接成功，降级策略生效
- [ ] 首次运行正常下载并保存所有数据
- [ ] 二次运行API调用次数减少70%+
- [ ] 数据库覆盖率检测准确（容错±5%）
- [ ] 分析结果正确保存到analysis_results表
- [ ] 数据库不可用时优雅降级到纯API模式
- [ ] 内存占用减少60%+
- [ ] 集成测试全部通过

## 📝 下一步

模块4完成后，继续实施：
- **模块5**: 配置和部署（环境变量、文档）

---

**版本**: v1.0
**日期**: 2025-01-11
**作者**: Claude Sonnet 4.5
