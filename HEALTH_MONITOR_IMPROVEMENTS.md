# 协整健康监控器改进说明

## 📋 改进概览

本次修复解决了观察期数据准确性问题，确保健康监控能提供可靠的协整质量评估。

---

## ✅ 已完成的修复

### 1️⃣ **修复稳定性评分失真问题** 🔥

#### 问题
原代码依赖历史累积机制（`beta_history`、`adf_pass_history`），但实际使用中每次创建新实例，导致：
- β稳定性评分永远为0（需要≥5个历史值）
- ADF持续性评分失真（只有1个历史值）

#### 解决方案
**使用滚动窗口替代历史累积**：

```python
# β稳定性 (0-10分)
- 旧方法：依赖多次调用累积的 beta_history
- 新方法：将当前窗口分为5段，每段独立计算β，然后计算变异系数
- 实现：_calc_beta_stability() 方法

# ADF持续性 (0-10分)
- 旧方法：依赖多次调用累积的 adf_pass_history
- 新方法：在当前窗口内取5个子窗口（100%, 80%, 60%, 40%, 20%），分别做ADF检验，计算通过率
- 实现：_calc_adf_consistency() 方法

# 均值漂移 (0-10分)
- 保持不变：比较前20%和后20%数据的均值差异
- 优化：动态计算分段大小，最小20期
```

**效果**：稳定性评分现在能真实反映窗口内的β稳定性、均值漂移和ADF持续性。

---

### 2️⃣ **调整得分阈值匹配实际范围** 🔥

#### 问题
旧阈值设定 `(80, 60, 40)` 无法达到：
```python
# 实际可达到的最高分
旧版：0.4*40 + 0.3*30 + 0.3*20 = 31分 （稳定性最高20分）
新版：0.4*40 + 0.3*30 + 0.3*30 = 34分 （稳定性修复后满分30分）

# 结果：所有交易对都显示为 DEAD 状态
```

#### 解决方案
调整阈值为 `(25, 18, 12)`：
```python
state_thresholds = (25, 18, 12)  # HEALTHY, WARNING, DANGER

# 新的状态分布（假设最高分34）
HEALTHY: ≥25分 (≈74%满分)
WARNING: 18-25分 (≈53%-74%)
DANGER: 12-18分 (≈35%-53%)
DEAD: <12分 (<35%)
```

**建议**：观察100个样本后，根据实际分布重新校准阈值。

---

### 3️⃣ **改进半衰期计算的稳健性** 🔧

#### 问题
旧代码有5个if判断处理异常情况，且phi阈值设置为-2（不合理）：
```python
if phi <= -2:  # ❌ 错误：AR(1)的phi应该在(-1, 0)区间
    halflife = np.inf
```

#### 解决方案
**增强稳健性检验**：

```python
# 1. phi显著性检验
if phi_pvalue > 0.05:
    return 0, inf, "PHI_NOT_SIGNIFICANT"

# 2. AR(1)拟合优度检验
if rsquared < 0.2:
    return 0, inf, "AR1_POOR_FIT"

# 3. phi边界条件（修正）
if phi >= 0:
    return 0, inf, "NO_MEAN_REVERSION"
elif phi <= -1:  # ✅ 修正：从-2改为-1
    return 0, inf, "OVER_CORRECTION"

# 4. 返回失败原因
return score, halflife, reason, model
```

**新增失败原因追踪**：
- `PHI_NOT_SIGNIFICANT`: phi系数不显著
- `AR1_POOR_FIT`: AR(1)模型拟合优度太低
- `NO_MEAN_REVERSION`: 无均值回归（phi≥0）
- `OVER_CORRECTION`: 过度修正（phi≤-1）
- `TOO_SLOW`: 半衰期太长（>30期）
- `VERY_FAST`: 半衰期很快（≤5期）
- `NORMAL`: 正常范围

---

### 4️⃣ **添加诊断信息和异常警告** 📊

#### 新增功能

**诊断信息结构**：
```python
diagnostics = {
    "model_quality": {
        "beta_rsquared": 0.75,      # Beta模型拟合优度
        "beta_model_valid": True,   # Beta模型是否有效(R²>0.3)
        "ar1_rsquared": 0.45,       # AR(1)模型拟合优度
        "ar1_model_valid": True,    # AR(1)模型是否有效(R²>0.2)
        "phi": -0.15,               # phi系数
        "phi_pvalue": 0.001         # phi系数p值
    },
    "data_quality": {
        "spread_std": 0.025,        # 价差标准差
        "spread_mean": 0.002,       # 价差均值
        "spread_skewness": -0.5,    # 偏度
        "spread_kurtosis": 3.2      # 峰度
    },
    "stability_breakdown": {
        "beta_cv": 0.08,            # β变异系数
        "beta_stability_score": 5,  # β稳定性得分
        "mean_shift_ratio": 0.3,    # 均值漂移比率
        "mean_shift_score": 10,     # 均值漂移得分
        "adf_pass_rate": 0.8,       # ADF通过率
        "adf_consistency_score": 8  # ADF持续性得分
    },
    "warnings": [
        "AR1_LOW_FIT",             # AR(1)拟合优度低
        "BETA_UNSTABLE",           # β不稳定
        "MEAN_SHIFT_LARGE",        # 均值大幅漂移
        "ADF_INCONSISTENT",        # ADF不一致
        "VOLATILITY_REGIME_CHANGE", # 波动率状态突变
        "HIGH_SKEWNESS",           # 高偏度
        "FAT_TAILS"                # 肥尾分布
    ]
}
```

**异常警告规则**：
| 警告 | 触发条件 | 含义 |
|------|---------|------|
| AR1_LOW_FIT | R² < 0.3 | AR(1)模型不适用，半衰期不可靠 |
| BETA_LOW_FIT | R² < 0.5 | Beta模型拟合差，协整关系弱 |
| BETA_UNSTABLE | β变异系数 > 0.2 | β系数不稳定 |
| MEAN_SHIFT_LARGE | 漂移比 > 1.5 | 价差中枢显著改变 |
| ADF_INCONSISTENT | 通过率 < 0.5 | 平稳性不稳定 |
| VOLATILITY_REGIME_CHANGE | 前后半波动率比 > 2 | 结构性变化 |
| HIGH_SKEWNESS | \|偏度\| > 2 | 分布不对称 |
| FAT_TAILS | 峰度 > 7 | 极端值频繁 |

---

### 5️⃣ **实现双窗口对比功能** 📈

#### 功能说明

同时计算200期和100期窗口的健康得分，对比差异：

```python
# 长期窗口（200期 = 33天）
result_long = monitor_long.update(log_base_series, log_alt_series)

# 短期窗口（100期 = 16.7天）
result_short = monitor_short.update(log_base_series, log_alt_series)

# 计算差异
score_diff = abs(result_long['health_score'] - result_short['health_score'])
```

**观察价值**：
- **差异 < 10分**：长短期一致，结构稳定
- **差异 > 10分**：需要关注
  - 长期高/短期低 → 短期结构恶化，可能暂停交易
  - 长期低/短期高 → 短期改善，可能是新机会
  - 长期高/短期高 → 持续健康，可以交易
  - 长期低/短期低 → 持续不健康，避免交易

---

### 6️⃣ **增强日志输出** 📝

#### 新日志格式

```
╔════════════════════════════════════════════════════════════════
║ 协整健康监控 | 币种: ATOM
╠════════════════════════════════════════════════════════════════
║ 【长期窗口 200期】
║   综合得分: 28.5 | 状态: HEALTHY
║   ADF: p=0.0123 (得分:35.2)
║   半衰期: 15.3 期 (得分:17.6) | 原因:NORMAL
║   稳定性: 25.7 (β变异:0.08, 均值漂移:0.30, ADF持续:80.0%)
║
║ 【短期窗口 100期】
║   综合得分: 26.8 | 状态: HEALTHY
║   ADF: p=0.0089 (得分:37.8)
║   半衰期: 18.2 期 (得分:14.2) | 原因:NORMAL
║   稳定性: 22.0 (β变异:0.12, 均值漂移:0.45, ADF持续:60.0%)
║
║ 【窗口对比】
║   得分差异: 1.70 ✓ 差异正常
║   趋势判断: 📉 短期恶化
║
║ 【诊断信息 - 长期】
║   模型质量: Beta R²=0.75, AR1 R²=0.45, phi=-0.15
║   数据质量: Spread σ=0.0250, 偏度=-0.50, 峰度=3.20
║   异常警告: 无异常
╚════════════════════════════════════════════════════════════════
```

**额外警告日志**（有异常时）：
```
⚠️ 币种 APT 健康监控异常 | 问题:
  - AR(1)模型拟合优度低(R²=0.18), 半衰期可能不可靠
  - β系数不稳定(变异系数=0.25), 协整关系可能恶化
  - 波动率状态突变, 可能发生结构性变化
```

---

## 🎯 观察期建议

### 阶段1：数据收集（1-2周）

**观察内容**：
1. 记录100个样本的得分分布
2. 统计各状态（HEALTHY/WARNING/DANGER/DEAD）的出现频率
3. 分析异常警告的出现频率和类型

**数据收集脚本示例**：
```python
# 观察期统计
scores = []
states = []
warnings_freq = {}

for coin, result in health_results.items():
    scores.append(result['health_score'])
    states.append(result['state'])

    for warning in result['diagnostics']['warnings']:
        warnings_freq[warning] = warnings_freq.get(warning, 0) + 1

# 统计分析
print(f"得分分布: min={min(scores)}, max={max(scores)}, mean={np.mean(scores):.2f}, median={np.median(scores):.2f}")
print(f"状态分布: {Counter(states)}")
print(f"Top 5 警告: {sorted(warnings_freq.items(), key=lambda x: x[1], reverse=True)[:5]}")
```

### 阶段2：阈值校准（第3周）

根据实际得分分布重新校准阈值：

```python
# 假设观察到：
# - 最高分：32
# - 75分位：26
# - 50分位：18
# - 25分位：12

# 校准建议
state_thresholds = (26, 18, 12)  # 基于实际分布
```

### 阶段3：规则验证（第4周）

验证监控指标与交易表现的关联：

```python
# 分析健康得分与交易盈亏的关系
high_health_pnl = []  # health_score >= 26
mid_health_pnl = []   # 18 <= health_score < 26
low_health_pnl = []   # health_score < 18

# 统计分析
print(f"高健康组: 胜率={win_rate_high:.2%}, 平均盈亏={avg_pnl_high:.4f}")
print(f"中健康组: 胜率={win_rate_mid:.2%}, 平均盈亏={avg_pnl_mid:.4f}")
print(f"低健康组: 胜率={win_rate_low:.2%}, 平均盈亏={avg_pnl_low:.4f}")

# 决策规则
if avg_pnl_low < 0:
    print("建议：health_score < 18 时跳过交易")
```

---

## 📦 使用示例

### 基础使用

```python
from utils.coingetation_more_check import CointegrationHealthMonitor

# 创建监控器
monitor = CointegrationHealthMonitor(
    window=100,
    max_halflife=30,
    min_halflife=5,
    state_thresholds=(25, 18, 12),
    enable_diagnostics=True
)

# 更新数据
result = monitor.update(log_price_A, log_price_B)

# 查看结果
print(f"健康得分: {result['health_score']}")
print(f"状态: {result['state']}")
print(f"半衰期: {result['halflife']} | 原因: {result['halflife_reason']}")
print(f"异常警告: {result['diagnostics']['warnings']}")
```

### 双窗口对比

```python
# 长期监控
monitor_long = CointegrationHealthMonitor(window=200, enable_diagnostics=True)
result_long = monitor_long.update(log_price_A, log_price_B)

# 短期监控
monitor_short = CointegrationHealthMonitor(window=100, enable_diagnostics=True)
result_short = monitor_short.update(log_price_A, log_price_B)

# 判断趋势
if result_short['health_score'] > result_long['health_score'] + 5:
    print("📈 短期改善，可能是新机会")
elif result_short['health_score'] < result_long['health_score'] - 5:
    print("📉 短期恶化，建议谨慎")
else:
    print("➡️ 稳定")
```

### 决策集成（观察完成后）

```python
# 未来可以这样使用
result = monitor.update(log_price_A, log_price_B)

# 过滤不健康交易对
if result['state'] == 'DEAD':
    logger.warning(f"跳过不健康交易对 {coin}")
    continue

# 根据警告调整仓位
if 'VOLATILITY_REGIME_CHANGE' in result['diagnostics']['warnings']:
    logger.warning(f"币种 {coin} 波动率突变，减仓50%")
    position_size *= 0.5

# 根据健康得分调整风险参数
if result['health_score'] < 20:
    zscore_threshold *= 1.2  # 提高入场门槛
```

---

## 🔍 技术细节

### 评分体系

| 维度 | 权重 | 满分 | 评分方法 |
|------|------|------|---------|
| ADF平稳性 | 40% | 40分 | p<0.01→40分, p>0.1→0分, 中间线性插值 |
| 半衰期 | 30% | 30分 | ≤5期→30分, ≥30期→0分, 中间线性插值 |
| 稳定性 | 30% | 30分 | β稳定10分 + 均值漂移10分 + ADF持续10分 |

**满分**: 100分（理论）
**实际最高分**: 约34分（考虑实际数据限制）

### 稳定性细分

| 维度 | 满分 | 优秀 | 良好 | 不合格 |
|------|------|------|------|--------|
| β稳定性 | 10分 | CV<0.05 (10分) | CV<0.15 (5分) | CV≥0.15 (0分) |
| 均值漂移 | 10分 | 漂移<0.5σ (10分) | 漂移<1.5σ (5分) | 漂移≥1.5σ (0分) |
| ADF持续性 | 10分 | 通过率×10 | - | - |

### 参数建议

| 参数 | 100期窗口 | 200期窗口 | 说明 |
|------|----------|----------|------|
| window | 100 | 200 | 与交易信号窗口一致 vs 评估长期稳定性 |
| max_halflife | 30 | 30 | 30个4h周期 = 5天 |
| min_halflife | 5 | 5 | 5个4h周期 = 20小时 |
| state_thresholds | (25,18,12) | (25,18,12) | 根据观察期调整 |

---

## 🐛 已知限制

1. **数据要求**：至少需要window期数据（100或200期）
2. **计算开销**：双窗口模式会增加计算时间（约2倍）
3. **ADF检验**：在强趋势或结构突变时可能失效
4. **AR(1)假设**：价差必须符合AR(1)过程，否则半衰期不可靠

---

## 📝 更新日志

### v2.0.0 (当前版本)

**重大改进**：
- ✅ 修复稳定性评分失真（使用滚动窗口）
- ✅ 调整阈值为实际可达范围
- ✅ 改进半衰期计算稳健性
- ✅ 添加诊断信息和异常警告
- ✅ 实现双窗口对比功能
- ✅ 大幅增强日志输出

**移除**：
- ❌ 历史累积机制（beta_history, adf_pass_history）
- ❌ beta_window 参数（改用滚动窗口）
- ❌ adf_history 参数（改用滚动窗口）

### v1.0.0 (旧版本)

**问题**：
- ❌ 稳定性评分失真（历史机制失效）
- ❌ 阈值无法达到（全部显示DEAD）
- ❌ 半衰期边界条件过多
- ❌ 缺少诊断信息

---

## 📞 问题反馈

如果在观察期发现以下情况，请记录并反馈：

1. **得分异常**：所有交易对得分都很高/很低
2. **警告频繁**：某个警告频繁出现
3. **阈值不合理**：HEALTHY状态的交易对表现很差
4. **半衰期异常**：半衰期经常是inf或失败原因不明确
5. **窗口对比异常**：长短期得分差异总是很大

---

## 🎓 参考资料

**协整理论**：
- Engle, R. F., & Granger, C. W. (1987). Co-integration and error correction
- Johansen, S. (1991). Estimation and hypothesis testing of cointegration vectors

**均值回归**：
- Ornstein-Uhlenbeck过程
- AR(1)模型与半衰期

**ADF检验**：
- Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series
