# Beta系数详解 - 配对交易核心参数解析

> 基于 purr5.py 的协整检验实现

## Beta_ols 参数的核心含义

`beta_ols` 是配对交易策略的核心参数，本文档详细解释其含义和应用。

---

## 1. 数学定义

### OLS回归公式

代码位置：`purr5.py` 第428-432行

```python
# 回归方程：log_alt = α + β × log_base + ε
model = LinearRegression()
model.fit(log_base, log_alt)  # X=log(基准币价格), Y=log(ALT币价格)

alpha = model.intercept_  # 截距项 α
beta = model.coef_[0]      # 斜率 β（核心参数）
```

**数学表达**：
```
log(PURR价格) = α + β × log(HYPE价格) + 误差

示例：β = 1.5, α = 0.2
log(PURR) = 0.2 + 1.5 × log(HYPE)
```

---

## 2. Beta的三重含义

### 2.1 价格敏感度（直观理解）

**定义**：β表示基准币涨1%时，ALT币平均涨多少%

**实际例子**：
```
假设 β = 1.5

场景：HYPE上涨 10%
预期：PURR应该上涨 15%（10% × 1.5）

实际情况分析：
- PURR实际涨8%  → 被低估 → 套利机会：做多PURR
- PURR实际涨15% → 正常     → 无套利机会
- PURR实际涨20% → 被高估 → 套利机会：做空PURR
```

**不同Beta值的市场含义**：

| Beta值 | 市场特征 | 涨跌关系 | 例子 |
|--------|----------|----------|------|
| β = 1.0 | 同步涨跌 | HYPE涨10% → PURR涨10% | 高度关联 |
| β = 1.5 | ALT更激进 | HYPE涨10% → PURR涨15% | 高波动币种 |
| β = 0.5 | ALT更保守 | HYPE涨10% → PURR涨5% | 防御性币种 |
| β = -0.5 | 负相关 | HYPE涨10% → PURR跌5% | 对冲资产 |
| β = 0 | 无关联 | HYPE涨跌对PURR无影响 | 独立走势 |

### 2.2 对冲比例（交易执行）

**定义**：β决定配对交易中的对冲头寸大小

**计算公式**：
```python
# 配对交易对冲比例
买入 1 个 PURR
卖出 β × (PURR价格/HYPE价格) 个 HYPE
```

**数值示例**：
```
假设：
- PURR价格 = $3
- HYPE价格 = $10
- β = 1.5

执行配对交易：
- 买入：1 PURR（$3）
- 卖出：1.5 × (3/10) = 0.45 个 HYPE（$4.5）

对冲效果：
- 如果市场整体上涨10%，两边盈亏抵消
- 只有价差偏离时才产生盈亏
- 实现市场中性策略
```

**对冲的必要性**：
- ❌ 不对冲：单边做多PURR → 承担市场风险
- ✅ 对冲后：只赌价差回归 → 市场中性策略
- ✅ 收益来源：价差偏离的均值回归，而非市场涨跌

### 2.3 协整关系核心（统计基础）

**定义**：β保证价差序列平稳（ADF检验的关键）

**价差公式**（代码第489行）：
```python
spread = log(PURR) - (α + β × log(HYPE))
```

**β对价差平稳性的影响**：
```
β选择不当的后果：
- β太小 → spread持续上升（趋势向上）❌ 非平稳
- β太大 → spread持续下降（趋势向下）❌ 非平稳
- β最优 → spread围绕0上下波动（均值回归）✅ 平稳

ADF检验目的：
验证用当前β计算的spread是否真正平稳
```

---

## 3. 代码中的实际应用

### 3.1 两种方法对比（第607-608行）

```python
# 老方法：全样本估计（360期）
ols_params = _calculate_cointegration_params(base_prices, alt_prices, coin=coin)
beta_old = ols_params['beta']  # 例：1.52

# 新方法：滚动窗口估计（100期）
cointegration_result = price_diff_spread_ols_window(base_prices, alt_prices, ...)
beta_new = cointegration_result['beta']  # 例：1.48

# Beta稳定性检查（应该添加）
if abs(beta_old - beta_new) > 0.1:
    logger.warning(f"Beta漂移严重 | 老方法: {beta_old:.2f} | 新方法: {beta_new:.2f}")
    # Beta不稳定 → 协整关系可能失效 → 拒绝信号
```

### 3.2 交易信号生成（第640-669行）

```python
# Z-score基于价差序列
spread = log(PURR) - (α + β × log(HYPE))

# Beta估计错误的影响
假设：
- beta_true = 1.5（真实值）
- beta_used = 1.0（错误估计）

后果：
- spread_wrong = log(PURR) - (α + 1.0 × log(HYPE))
- 价差计算错误 → Z-score失真 → 虚假套利信号
- 可能导致：假阳性（错误入场）或假阴性（错过机会）
```

---

## 4. Beta的稳定性至关重要

### 4.1 稳定的Beta（健康的协整关系）

```python
# 滚动窗口Beta序列
期数 1-100：beta = 1.50
期数 2-101：beta = 1.52
期数 3-102：beta = 1.48
期数 4-103：beta = 1.51

标准差 = 0.017（很小）✅

特征：
- Beta在小范围内波动
- ADF检验稳定通过
- 交易信号可靠
- 策略可以长期运行
```

### 4.2 不稳定的Beta（协整关系失效）

```python
# 滚动窗口Beta序列
期数 1-100：beta = 1.50
期数 2-101：beta = 1.80（突然跳变）❌
期数 3-102：beta = 1.20（剧烈波动）❌
期数 4-103：beta = 1.65

标准差 = 0.26（很大）❌

特征：
- Beta剧烈波动
- 协整关系可能已失效
- ADF检验可能失败（或勉强通过但不可靠）
- 交易信号危险，应停止策略
```

### 4.3 Beta漂移的原因

| 原因 | 表现 | 应对策略 |
|------|------|----------|
| 市场结构变化 | Beta缓慢漂移 | 缩短窗口，增加更新频率 |
| 流动性变化 | Beta波动增大 | 增加Z-score阈值，减少交易频率 |
| 基本面变化 | Beta趋势性变化 | 重新评估协整关系，可能终止策略 |
| 极端行情 | Beta短期异常 | 暂停交易，等待市场恢复正常 |

---

## 5. 实战案例：理解Beta的作用

### 案例1：HYPE暴涨场景

```
初始状态（T=0）：
- HYPE = $10
- PURR = $3
- β = 1.5
- α = 0.2（假设）

市场变化（T=1）：
- HYPE暴涨到 $11（+10%）

理论计算：
log(PURR新) = α + β × log(HYPE新)
log(PURR新) = 0.2 + 1.5 × log(11)

简化估算：PURR应该涨 10% × 1.5 = 15%
PURR理论价格 = $3 × 1.15 = $3.45

实际市场的三种情况：

情况A：PURR涨到$3.45
- 价差 = 0（实际 = 理论）
- Z-score ≈ 0
- 结论：无套利机会

情况B：PURR只涨到$3.20（涨幅6.7%）
- 价差 < 0（PURR被低估）
- Z-score = -2.5（假设）
- 结论：做多PURR，做空HYPE
- 预期：价差回归，PURR补涨

情况C：PURR涨到$3.60（涨幅20%）
- 价差 > 0（PURR被高估）
- Z-score = +2.8（假设）
- 结论：做空PURR，做多HYPE
- 预期：价差回归，PURR回调
```

### 案例2：Z-score的计算逻辑

```python
# 基于案例1的情况B

# 1. 计算价差
spread_current = log(3.20) - (0.2 + 1.5 × log(11))
spread_current ≈ -0.15（负数 → PURR被低估）

# 2. 历史价差统计（前29期）
spread_mean = 0.01（历史均值，接近0说明协整关系稳定）
spread_std = 0.06（历史标准差）

# 3. 计算Z-score
zscore = (spread_current - spread_mean) / spread_std
zscore = (-0.15 - 0.01) / 0.06
zscore = -2.67

# 4. 交易决策
if zscore < -2.0:  # 偏离超过2个标准差
    # 做多PURR套利策略
    买入 1 PURR（$3.20）
    卖出 0.48 个 HYPE（1.5 × 3.20/10 = 0.48 个，价值$5.28）

    # 预期盈利逻辑
    # 当价差回归（zscore → 0）时：
    # PURR上涨到理论价格$3.45（+7.8%）
    # HYPE保持$11或小幅波动
    # 多头盈利：$0.25 × 1 = $0.25
    # 空头盈利/亏损：取决于HYPE走势（已对冲）
```

---

## 6. Beta在代码流程中的关键作用

### 6.1 数据流图

```
价格数据（BASE, ALT）
    ↓
OLS回归（估计α和β）
    ↓
构建价差序列：spread = log(ALT) - (α + β × log(BASE))
    ↓
ADF检验：验证价差是否平稳（是否真正协整）
    ↓           ↓
  通过        失败
    ↓           ↓
计算Z-score   拒绝信号
    ↓
交易决策
```

### 6.2 关键检查点

代码应该添加的Beta质量检查：

```python
def validate_beta_quality(beta_current, beta_history, coin=None):
    """
    验证Beta质量（建议添加）

    Args:
        beta_current: 当前窗口估计的beta
        beta_history: 历史beta序列（滚动窗口）
        coin: 币种名称

    Returns:
        bool: Beta是否稳定可靠
    """
    # 检查1：Beta是否在合理范围
    if beta_current < 0 or beta_current > 3.0:
        logger.warning(f"Beta异常 | 币种: {coin} | Beta: {beta_current:.2f}")
        return False

    # 检查2：Beta是否剧烈波动（如果有历史数据）
    if len(beta_history) > 0:
        beta_std = np.std(beta_history)
        if beta_std > 0.3:  # 标准差过大
            logger.warning(f"Beta不稳定 | 币种: {coin} | 标准差: {beta_std:.2f}")
            return False

    # 检查3：Beta是否突然跳变
    if len(beta_history) > 0:
        beta_prev = beta_history[-1]
        beta_change = abs(beta_current - beta_prev) / beta_prev
        if beta_change > 0.2:  # 变化超过20%
            logger.warning(f"Beta突变 | 币种: {coin} | 变化: {beta_change:.1%}")
            return False

    return True
```

---

## 7. 总结

### Beta_ols 的多维度含义

| 维度 | 含义 | 用途 |
|------|------|------|
| **统计学** | OLS回归斜率 | 衡量log(ALT)对log(BASE)的敏感度 |
| **交易学** | 对冲比例系数 | 决定买1份ALT要卖多少份BASE |
| **风险管理** | 协整参数 | 确保价差序列平稳的关键 |
| **信号质量** | 稳定性指标 | Beta越稳定，信号越可靠 |

### 代码中的应用总结

purr5.py 中 Beta 的核心用途：

1. ✅ **构建价差序列**（第489行）：`spread = log(ALT) - (α + β × log(BASE))`
2. ✅ **ADF检验**（第492行）：验证价差平稳性
3. ✅ **Z-score计算**（第625行）：识别套利机会
4. ✅ **交易执行**（隐含）：确定对冲头寸大小

### 关键警示

⚠️ **Beta必须稳定**：
- Beta漂移 → 协整关系失效
- 协整失效 → ADF检验不可靠
- ADF不可靠 → Z-score信号失真
- 信号失真 → 策略失败

⚠️ **窗口选择影响Beta估计**：
- 窗口太短（<60期）：Beta噪声大，估计不稳定
- 窗口太长（>120期）：Beta包含过时关系，滞后市场变化
- 最佳窗口：60-120期（对于小时级别数据）

⚠️ **两种方法的Beta应该接近**：
- 如果老方法beta=1.5，新方法beta=2.0
- 说明Beta正在漂移，协整关系可能失效
- 应该拒绝该信号或降低置信度

---

## 参考文献

1. Engle, R.F. & Granger, C.W.J. (1987). "Co-integration and Error Correction: Representation, Estimation, and Testing". *Econometrica*, 55(2), 251-276.

2. Gatev, E., Goetzmann, W.N., & Rouwenhorst, K.G. (2006). "Pairs Trading: Performance of a Relative-Value Arbitrage Rule". *Review of Financial Studies*, 19(3), 797-827.

3. Do, B., & Faff, R. (2010). "Does simple pairs trading still work?". *Financial Analysts Journal*, 66(4), 83-95.

4. Vidyamurthy, G. (2004). *Pairs Trading: Quantitative Methods and Analysis*. John Wiley & Sons.

5. Alexander, C. & Dimitriu, A. (2005). "Indexing and statistical arbitrage". *Journal of Portfolio Management*, 31(2), 50-63.

---

**文档版本**: 1.0
**创建日期**: 2026-01-05
**基于代码**: purr5.py
**作者**: Claude (Anthropic)
