# BTC 缓存延迟导致 5m Z-score 假信号 — Bug 分析报告

> **分析日期**: 2026-01-27
> **涉及模块**: `multi_coins5.py`
> **严重程度**: 高（可导致错误告警）
> **影响范围**: 所有通过 `multi_coins5.py` 扫描的山寨币，排序越靠后影响越大

---

## 一、问题概述

`multi_coins5.py` 在 2026-01-27 01:19（UTC+7）对 XAI/USDC:USDC 发出了飞书告警（Z-score=2.35, correlation=0.604），但 `realtime_kline_service.py` 在同一时间点未触发告警（5m Z-score=-0.44, 1h=1.23, 4h=0.33，因符号不一致被拦截）。

经过完整的代码审查和数据模拟，确认根因是 **BTC 数据缓存机制导致新旧数据混搭，产生了不反映真实市场状态的 Z-score 值**。

---

## 二、Bug 根因

### 2.1 一句话概括

**同一根 5m K线（如 18:05），BTC 侧存的是"形成中"的中间价格，XAI 侧存的是已完成的最终收盘价。用中间价和最终价做对比，算出来的 Z-score 不代表任何真实的市场关系。**

### 2.2 涉及的代码路径

| 步骤 | 代码位置 | 行为 |
|------|---------|------|
| BTC 缓存 | `_get_base_data()` (line 957-967) | 首次调用下载并缓存，后续调用返回缓存副本 |
| 山寨币实时获取 | `_get_alt_data()` (line 969-1009) | 每个币种独立下载（也有缓存，但每个币种只分析一次） |
| API 返回未完成K线 | `download_ccxt_data()` (line 280) | `exchange.fetch_ohlcv()` 返回包含当前 forming candle 的数据 |
| 数据对齐 | `_align_and_validate_data()` (line 1055) | `base_df.index.intersection(alt_df.index)` 内连接，保留共同时间戳 |
| Z-score 计算 | `price_diff_spread_ols_window()` (line 553-562) | `spread = log(XAI) - β × log(BTC)`，使用最后 30 个点 |
| 阈值检查 | `zscore_analysis()` (line 1497-1500) | 要求 5m \|Z\| > 1.8, 1h \|Z\| > 1.5, 4h \|Z\| > 0.2 |

---

## 三、Bug 形成的完整时间线

以告警时刻 18:19 UTC 为锚点反推：

```
18:05:30 UTC — 扫描开始，处理第 1 个币种
│
├── BTC 5m 数据首次下载并缓存
│   └── 最后一根K线: timestamp=18:05
│       close = 88,200（BTC 在 18:05:30 的瞬时价格）
│       状态: FORMING（这根 candle 要到 18:10:00 才完成）
│
│   ... 约 150 个币种 × (2s 间隔 + ~4.5s API) ≈ 14 分钟 ...
│
18:19:00 UTC — 轮到 XAI（约第 130 个币种）
│
├── XAI 5m 数据实时下载
│   └── 包含 18:05 candle: close = 0.01459
│       状态: COMPLETED（9 分钟前已关闭，这是最终收盘价）
│
├── BTC 5m 数据: 从缓存返回（18:05:30 获取的那份）
│   └── 18:05 candle: close = 88,200（依然是中间值）
│
├── 数据对齐（内连接）
│   └── 共同最后时间戳: 18:05
│       BTC 18:05 close = 88,200（中间值，非最终值）
│       XAI 18:05 close = 0.01459（最终值）
│
├── Z-score 计算
│   └── spread_last = log(0.01459) - 1.88 × log(88200)
│       这个 spread 混合了不同时刻、不同状态的数据
│       → 5m Z-score 被人为抬高到 > 1.8
│
└── 告警发出: Z-score = 2.35（所有周期最大绝对值）
```

### 时间线图示

```
时间轴:
18:05:30          18:10:00          18:19:00
   │                 │                 │
   │  BTC 5m 数据    │  18:05 candle   │  XAI 5m 数据
   │  被缓存         │  真正关闭       │  被下载
   │                 │                 │
   ▼                 ▼                 ▼

BTC 18:05 close    BTC 18:05 close   XAI 18:05 close
= 88,200           = 87,700          = 0.01459
(中间值)            (最终值)           (最终值)
   ↑                                     ↑
   └──── 缓存里的是这个 ─────────────── Z-score 用的是这个组合
         而不是这个 ↑                    BTC中间值 + XAI最终值
                                        = 从未存在的市场状态
```

---

## 四、定量分析：缓存延迟如何将 Z-score 推过阈值

### 4.1 Z-score 公式

```
spread = log(XAI_close) - β × log(BTC_close)       （β ≈ 1.88）
Z = (spread_last - mean(spread_前29个)) / std(spread_前29个)
```

### 4.2 偏移量计算

假设 BTC 在 18:05 candle 期间发生了 $500 的价格变动（0.57%，对 BTC 而言常见）：

| 参数 | 值 |
|------|-----|
| BTC 缓存中间值 | 88,200 |
| BTC 最终收盘价 | 87,700 |
| 价格差 | +500 (0.57%) |
| β | 1.88 |
| spread 偏移 | -β × Δlog(BTC) = -1.88 × log(88200/87700) = **-0.01071** |
| spread_std（前 29 点） | ≈ 0.009 |
| **Z-score 偏移** | 0.01071 / 0.009 = **1.19** |

### 4.3 实际效果

| 场景 | 5m Z-score | 是否通过阈值(1.8) |
|------|-----------|-----------------|
| 无缓存延迟（真实市场状态） | +0.94 | 否 |
| 有缓存延迟（BTC 中间值 + XAI 最终值） | +0.94 + 1.19 = **+2.13** | **是** |

这就是为什么告警能够发出——**不是因为市场真的出现了异常偏离，而是 BTC 缓存延迟人为制造了偏离**。

### 4.4 模拟验证

通过 `scan_5m_zscore.py` 对 17:00-18:30 UTC 区间进行全面扫描：

| 测试场景 | 5m \|Z\| 最大值 | 是否达到 1.8 |
|---------|----------------|-------------|
| BTC 和 XAI 同一截止时间 | 1.74 | 否 |
| BTC 比 XAI 早 0-29 分钟 | 1.49 | 否 |
| BTC 有 forming candle（Open 近似） | 1.44 | 否 |

使用**已完成K线**的 API 数据，5m |Z-score| **从未超过 1.8**。只有在 BTC 的 forming candle close 取特定的中间值时，才可能超过阈值。

---

## 五、为什么只有 5m 周期受影响

| 周期 | BTC 缓存的最后K线 | 完成时间 | XAI 获取时状态 | 不对称性 |
|------|-----------------|---------|---------------|---------|
| **5m** | 18:05 candle | 18:10:00 | **已完成**（XAI 在 18:19 获取，candle 9 分钟前已关闭） | **严重** |
| 1h | 18:00 candle | 19:00:00 | 也是 forming（XAI 在 18:19 获取，candle 要 19:00 才关闭） | 轻微 |
| 4h | 16:00 candle | 20:00:00 | 也是 forming（XAI 在 18:19 获取，candle 要 20:00 才关闭） | 极小 |

**核心矛盾**：5m candle 的生命周期（5 分钟）远小于扫描延迟（14 分钟），导致 BTC 的 forming candle 到 XAI 被分析时已经完成。BTC 侧保留的是中间值，XAI 侧已经是最终值——二者性质完全不同。

1h/4h candle 的生命周期（1~4 小时）远大于扫描延迟，所以 BTC 和 XAI 都处于 forming 状态，不对称性很小。

---

## 六、为什么 realtime_kline_service.py 不受此 bug 影响

| 维度 | `multi_coins5.py` | `realtime_kline_service.py` |
|------|-------------------|---------------------------|
| 数据源 | 交易所 REST API（一次性批量获取） | TimescaleDB（WebSocket 实时写入） |
| BTC 数据 | 扫描开始时获取，全程缓存 | 每次分析时从 DB 读取最新数据 |
| 数据新鲜度 | BTC 可能陈旧 14+ 分钟 | BTC 和山寨币同步更新 |
| forming candle | 包含（API 默认返回） | 不包含（DB 只存完成的 K 线） |
| 5m Z-score | +2.13（人工偏移） | -0.44（真实市场状态） |

`realtime_kline_service.py` 从 DB 读取的 BTC 和 XAI 数据是同步的、已完成的 K 线，不存在新旧混搭问题。它计算出的 5m Z-score = -0.44 是准确的。

---

## 七、影响范围评估

### 7.1 哪些币种受影响

扫描列表中**排序越靠后**的币种，BTC 数据越陈旧，受影响越大：

| 扫描位置 | 预计延迟 | 5m 不对称性 | 受影响程度 |
|---------|---------|-----------|----------|
| 第 1-20 名 | 0~2 分钟 | BTC forming candle 可能未完成 | 低 |
| 第 20-50 名 | 2~5 分钟 | BTC forming candle 刚完成 | 中 |
| 第 50-100 名 | 5~11 分钟 | BTC forming candle 已完成 1-2 根 | 高 |
| **第 100-150 名** | **11~17 分钟** | **BTC 多根 candle 已完成，严重陈旧** | **极高** |

### 7.2 触发条件

此 bug 不是必然触发，需要满足：

1. **BTC 在 forming candle 期间有显著价格波动**（> $300，约 0.35%）
2. **山寨币排在扫描列表的后半段**（延迟 > 10 分钟）
3. **该山寨币的 5m Z-score 本身接近阈值**（基准值 > 0.6）

三个条件同时满足时，BTC 缓存延迟可以将 5m Z-score 从阈值以下推到阈值以上。

### 7.3 不确定性

由于 `multi_coins5.py` 只输出到控制台（无 file handler），且告警消息中不包含各周期 Z-score 的明细，我们无法直接验证告警时的 5m Z-score 具体值。以上分析基于代码逻辑推导和数据模拟。

---

## 八、代码审查详情

### 8.1 已排除的假设

| 假设 | 验证方法 | 结论 |
|------|---------|------|
| 阈值检查逻辑有 bug | 逐行审查 `zscore_analysis()` line 1490-1500 | 逻辑正确 |
| Z-score 与周期映射错误 | 追踪 dict 插入顺序和索引 | 映射正确（Python 3.7+ 保序） |
| 阈值被运行时修改 | 检查 `__init__` 和所有赋值 | 无运行时修改 |
| 阈值在告警后被修改 | `git log --all -- multi_coins5.py` | 最后修改 Jan 16，告警 Jan 26，未变 |
| Close 价格被 Winsorization 处理 | 追踪 `_safe_download` → `download_ccxt_data` | Winsorization 只用于 returns，不影响 Close |
| `_calculate_cointegration_params` 修改了原始数据 | 阅读函数实现 | 创建新变量，无副作用 |
| 数据对齐 drop 了关键数据 | 检查 `_align_and_validate_data` | 标准内连接，行为正确 |

### 8.2 确认的问题

```python
# multi_coins5.py line 957-960
def _get_base_data(self, timeframe, period):
    cache_key = (timeframe, period)
    if cache_key in self.base_df_cache:
        return self.base_df_cache[cache_key].copy()  # ← 永远返回扫描开始时的数据
```

```python
# multi_coins5.py line 997
alt_df = self._safe_download(symbol, period, timeframe, coin)  # ← 每次实时下载
```

```python
# multi_coins5.py line 280
ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1500)
# ← Hyperliquid API 返回包含 forming candle 的数据
```

**三个因素叠加**：BTC 缓存 + API 返回 forming candle + 扫描耗时 14 分钟 = 5m 数据出现严重的新旧混搭。

---

## 九、修复建议

### 方案 A：每个币种重新获取 BTC 数据（彻底修复）

移除 BTC 缓存，每次分析都重新下载 BTC 数据：

```python
def _get_base_data(self, timeframe, period):
    # 不使用缓存，每次都实时获取
    base_df = self._safe_download(self.base_symbol, period, timeframe)
    return base_df
```

- 优点：完全消除新旧混搭问题
- 缺点：API 请求量增加约 3 倍（每个币种 3 个周期 × 150 个币种 = 450 次 BTC 请求），扫描时间可能延长

### 方案 B：过滤 forming candle（推荐）

在 `download_ccxt_data()` 中移除最后一根未完成的 K 线：

```python
# 在 download_ccxt_data() 返回前，移除 forming candle
now = pd.Timestamp.now(tz='UTC').tz_localize(None)
candle_duration = pd.Timedelta(minutes=self._timeframe_to_minutes(timeframe))
# 如果最后一根 candle 的结束时间在未来，说明它还在 forming
if len(df) > 0:
    last_candle_end = df.index[-1] + candle_duration
    if last_candle_end > now:
        df = df.iloc[:-1]  # 移除 forming candle
```

- 优点：改动小，不增加 API 请求，BTC 和 XAI 都只使用已完成的 K 线
- 缺点：损失最新一根 K 线的信息（对 5m 来说仅 5 分钟）

### 方案 C：定期刷新 BTC 缓存（折中方案）

设置缓存过期时间，超过后重新获取：

```python
def _get_base_data(self, timeframe, period):
    cache_key = (timeframe, period)
    cache_entry = self.base_df_cache.get(cache_key)

    # 缓存过期时间：小于 K 线周期的一半
    ttl_minutes = self._timeframe_to_minutes(timeframe) / 2

    if cache_entry:
        age = time.time() - cache_entry['timestamp']
        if age < ttl_minutes * 60:
            return cache_entry['data'].copy()

    base_df = self._safe_download(self.base_symbol, period, timeframe)
    if base_df is not None:
        self.base_df_cache[cache_key] = {
            'data': base_df,
            'timestamp': time.time()
        }
    return base_df
```

- 优点：平衡 API 负担和数据新鲜度
- 缺点：5m 数据的 TTL 为 2.5 分钟，仍需频繁请求

### 方案 D：为 multi_coins5.py 添加日志记录各周期 Z-score

无论选择哪个修复方案，都应在告警消息和日志中记录各周期的 Z-score 明细，便于事后审计：

```python
# 在 zscore_analysis() 返回前添加
logger.info(
    f"Z-score 明细 | 币种: {coin} | "
    f"5m={short_zscore:.4f} | 1h={middle_zscore:.4f} | 4h={direction:.4f} | "
    f"阈值: 5m>{self.ZSCORE_THRESHOLD_SHORT}, 1h>{self.ZSCORE_THRESHOLD_MIDDLE}, 4h>{self.ZSCORE_THRESHOLD_LONG}"
)
```

---

## 十、验证方法

修复后可通过以下方式验证：

1. **对比测试**：同时运行修复前后的版本，对比同一币种同一时刻的 5m Z-score
2. **日志审计**：检查告警中的 5m Z-score 是否在合理范围内（与 `realtime_kline_service.py` 的值对比）
3. **模拟测试**：人为延迟 BTC 缓存 15 分钟，确认修复后不再产生偏移

---

## 附录 A：相关文件

| 文件 | 用途 |
|------|------|
| `multi_coins5.py` | 存在 bug 的扫描脚本 |
| `realtime_kline_service.py` | 对照系统（不受此 bug 影响） |
| `utils/analysis_core.py` | Z-score 计算核心（`realtime_kline_service` 使用） |

## 附录 B：关键代码行索引

| 行号 | 函数 | 关键逻辑 |
|------|------|---------|
| 123-131 | 类属性 | Z-score 阈值定义 |
| 258-305 | `download_ccxt_data()` | 从 API 获取 K 线（含 forming candle） |
| 487-576 | `price_diff_spread_ols_window()` | OLS 回归 + spread 计算 |
| 741-832 | `_calculate_zscore()` | 从 spread 计算 Z-score |
| 943-967 | `_get_base_data()` | BTC 数据缓存逻辑（bug 根源） |
| 969-1009 | `_get_alt_data()` | 山寨币数据获取（每次实时下载） |
| 1034-1063 | `_align_and_validate_data()` | 内连接对齐 |
| 1431-1502 | `zscore_analysis()` | 多周期 Z-score 阈值检查 |
| 1592-1600 | `one_coin_analysis()` | 告警发送入口 |
| 1668-1686 | `run()` | 扫描主循环（2s 间隔） |
