# Engle-Granger 协整检验详解

> 配对交易中的协整关系检验：理论、实现与应用

> **专注加密货币市场** | 完整理论 + 代码实现 + 实战案例

---

## 目录

1. [理论基础与历史背景](#第1章理论基础与历史背景)
2. [数学原理与公式推导](#第2章数学原理与公式推导)
3. [检验步骤详解](#第3章检验步骤详解)
4. [ADF检验深入理解](#第4章adf检验深入理解)
5. [优缺点分析](#第5章优缺点分析)
6. [与Johansen检验对比](#第6章与johansen检验对比)
7. [代码实现详解](#第7章代码实现详解)
8. [实战应用案例](#第8章实战应用案例)
9. [常见问题与注意事项](#第9章常见问题与注意事项)
10. [改进方向与扩展](#第10章改进方向与扩展)

---

## 第1章：理论基础与历史背景

### 1.1 什么是协整？

**协整（Cointegration）** 是时间序列分析中的重要概念，由 Robert Engle 和 Clive Granger 在1987年提出，两人因此获得2003年诺贝尔经济学奖。

#### 1.1.1 直观理解

**问题场景**：
- 两个价格序列（如 HYPE 和 PURR）各自都是非平稳的（价格会随机游走）
- 但它们之间存在长期均衡关系
- 当价差偏离均衡时，会向均衡回归

**协整的定义**：
如果两个非平稳时间序列的线性组合是平稳的，则称这两个序列是协整的。

#### 1.1.2 数学定义

**定义**：两个时间序列 $X_t$ 和 $Y_t$ 被称为协整的，当且仅当：

```
1. X_t ~ I(1), Y_t ~ I(1)  （两者都是一阶单整，即需要一次差分才平稳）
2. 存在参数向量 β = (1, -β)，使得：
   Z_t = Y_t - α - β × X_t ~ I(0)  （残差序列平稳）
```

**在配对交易中的应用**：
- $X_t$：log(基准币价格)，如 log(HYPE)
- $Y_t$：log(山寨币价格)，如 log(PURR)
- $\beta$：对冲比例系数（Beta）
- $Z_t$：价差序列（Spread）

### 1.2 Engle-Granger 两步法

**核心思想**：
1. **第一步**：使用 OLS 回归估计协整向量
2. **第二步**：对回归残差进行单位根检验（ADF检验）

**为什么叫"两步法"？**
- 不是一次性完成，而是分两步进行
- 先估计参数，再检验残差平稳性
- 这是最直观、最易理解的协整检验方法

### 1.3 历史意义

**1987年论文**：
- Engle, R. F., & Granger, C. W. J. (1987). "Co-integration and Error Correction: Representation, Estimation, and Testing"
- 开创了协整理论，为配对交易提供了理论基础

**应用领域**：
- 配对交易（Pairs Trading）
- 套利策略（Arbitrage）
- 风险管理（Risk Management）
- 宏观经济分析

---

## 第2章：数学原理与公式推导

### 2.1 协整关系的数学表达

#### 2.1.1 基本模型

**回归方程**：
```
log(Y_t) = α + β × log(X_t) + ε_t
```

其中：
- $Y_t$：因变量（如 PURR 价格）
- $X_t$：自变量（如 HYPE 价格）
- $\alpha$：截距项（价格溢价/折价）
- $\beta$：斜率系数（对冲比例）
- $\varepsilon_t$：残差项（价差序列）

#### 2.1.2 OLS 估计

**参数估计**：
```
β̂ = Cov(log(Y), log(X)) / Var(log(X))

α̂ = E[log(Y)] - β̂ × E[log(X)]
```

**标准误**：
```
SE(β̂) = σ_ε / √(Σ(X_i - X̄)²)

t统计量 = β̂ / SE(β̂)
```

### 2.2 残差序列的性质

#### 2.2.1 价差序列

**定义**：
```
spread_t = log(Y_t) - (α + β × log(X_t))
         = ε_t  （残差）
```

**协整成立的条件**：
如果协整关系成立，则：
- $E[spread_t] = \mu$（常数均值）
- $Var[spread_t] = \sigma^2$（有限方差）
- $spread_t$ 具有均值回归特性

#### 2.2.2 均值回归过程

**数学表达**：
```
Δspread_t = θ × (spread_{t-1} - μ) + ε_t

其中：
- θ < 0：均值回归速度
- μ：长期均衡值
- ε_t：白噪声
```

**经济直觉**：
- 当 $spread_t > \mu$ 时，价差偏高，预期下降
- 当 $spread_t < \mu$ 时，价差偏低，预期上升
- 这就是配对交易的套利机会

### 2.3 单位根检验的必要性

**为什么需要检验残差的平稳性？**

如果残差序列 $Z_t$ 是平稳的（$I(0)$），则：
- 协整关系成立
- 两个序列存在长期均衡关系
- 适合进行配对交易

如果残差序列 $Z_t$ 是非平稳的（$I(1)$），则：
- 协整关系不成立
- 两个序列只是随机游走，没有长期关系
- 不适合配对交易

---

## 第3章：检验步骤详解

### 3.1 完整检验流程

#### 步骤1：数据预处理

**要求**：
1. 两个序列长度必须相同
2. 数据量足够（建议至少50-100个观测值）
3. 处理缺失值和异常值

**代码示例**：
```python
# 数据验证
if len(base_prices) != len(alt_prices):
    return None

if len(base_prices) < 10:  # 最小数据点要求
    return None
```

#### 步骤2：对数变换

**为什么取对数？**
1. 价格序列通常是指数增长的，对数后更平稳
2. 对数价格的变化率就是收益率
3. 对数变换使模型更符合金融理论

**代码实现**：
```python
log_base_series = np.log(base_prices)
log_alt_series = np.log(alt_prices)
```

#### 步骤3：OLS 回归

**回归方程**：
```
log_alt = α + β × log_base + ε
```

**代码实现**：
```python
from sklearn.linear_model import LinearRegression

log_base = log_base_series.values.reshape(-1, 1)
log_alt = log_alt_series.values

model = LinearRegression()
model.fit(log_base, log_alt)

alpha = model.intercept_      # 截距项
beta = model.coef_[0]         # 斜率系数
```

**输出结果**：
- $\alpha$：截距项，表示价格溢价/折价
- $\beta$：斜率系数，表示对冲比例

#### 步骤4：计算残差序列

**残差（价差）计算**：
```python
spread_ols = log_alt_series - (alpha + beta * log_base_series)
```

**残差的含义**：
- 如果协整成立，残差应该是平稳的
- 残差序列就是价差序列，用于后续的 Z-score 计算

#### 步骤5：ADF 检验

**Augmented Dickey-Fuller 检验**：
- 检验残差序列是否存在单位根
- 如果拒绝原假设（p-value < 0.05），则残差平稳，协整成立

**代码实现**：
```python
from statsmodels.tsa.stattools import adfuller

adf_result = adfuller(spread_ols.values, autolag='AIC')
adf_pvalue = adf_result[1]  # p值

# 判断协整是否成立
if adf_pvalue < 0.05:
    print("协整检验通过：价差序列平稳")
else:
    print("协整检验未通过：价差序列非平稳")
```

### 3.2 检验结果解读

#### 3.2.1 ADF 检验统计量

**ADF 检验输出**：
```python
adf_result = adfuller(spread_ols.values, autolag='AIC')

# 输出包含：
# - adf_statistic: ADF 统计量
# - pvalue: p值
# - usedlag: 使用的滞后阶数
# - nobs: 观测值数量
# - critical_values: 临界值字典
```

**判断标准**：
- **p-value < 0.05**：拒绝原假设，残差平稳，协整成立 ✅
- **p-value ≥ 0.05**：不能拒绝原假设，残差非平稳，协整不成立 ❌

#### 3.2.2 临界值对比

**常用临界值**（5%显著性水平）：
```
1%: -3.43
5%: -2.86
10%: -2.57
```

**判断规则**：
- 如果 ADF 统计量 < 临界值，拒绝原假设（平稳）
- 如果 ADF 统计量 ≥ 临界值，不能拒绝原假设（非平稳）

### 3.3 完整代码示例

```python
from statsmodels.tsa.stattools import adfuller
from sklearn.linear_model import LinearRegression
import numpy as np
import pandas as pd

def engle_granger_test(base_prices: pd.Series, 
                       alt_prices: pd.Series) -> dict:
    """
    Engle-Granger 两步法协整检验
    
    Returns:
        dict: {
            'alpha': 截距项,
            'beta': 斜率系数,
            'spread': 价差序列,
            'adf_pvalue': ADF检验p值,
            'is_cointegrated': 是否协整
        }
    """
    # 步骤1：数据验证
    if len(base_prices) != len(alt_prices) or len(base_prices) < 10:
        return None
    
    # 步骤2：对数变换
    log_base = np.log(base_prices).values.reshape(-1, 1)
    log_alt = np.log(alt_prices).values
    
    # 步骤3：OLS回归
    model = LinearRegression()
    model.fit(log_base, log_alt)
    
    alpha = model.intercept_
    beta = model.coef_[0]
    
    # 步骤4：计算残差
    spread = log_alt - (alpha + beta * log_base.flatten())
    
    # 步骤5：ADF检验
    adf_result = adfuller(spread, autolag='AIC')
    adf_pvalue = adf_result[1]
    
    return {
        'alpha': alpha,
        'beta': beta,
        'spread': pd.Series(spread, index=base_prices.index),
        'adf_pvalue': adf_pvalue,
        'is_cointegrated': adf_pvalue < 0.05
    }
```

---

## 第4章：ADF检验深入理解

### 4.1 ADF检验的原理

#### 4.1.1 单位根过程

**随机游走模型**：
```
Y_t = Y_{t-1} + ε_t
```

**特征**：
- 方差随时间增长：$Var(Y_t) = t \times \sigma^2$
- 没有均值回归特性
- 是典型的非平稳过程

#### 4.1.2 ADF检验的回归方程

**ADF 检验的回归形式**：
```
ΔY_t = α + βt + γY_{t-1} + Σ(δ_i × ΔY_{t-i}) + ε_t
```

其中：
- $\alpha$：常数项
- $\beta t$：时间趋势项（可选）
- $\gamma$：关键参数，检验 $\gamma = 0$（单位根）
- $\delta_i$：滞后差分项的系数

**原假设和备择假设**：
- $H_0: \gamma = 0$（存在单位根，非平稳）
- $H_1: \gamma < 0$（不存在单位根，平稳）

### 4.2 ADF检验的参数选择

#### 4.2.1 滞后阶数选择

**自动选择方法**：
```python
# 使用 AIC 准则自动选择滞后阶数
adf_result = adfuller(spread.values, autolag='AIC')

# 或使用 BIC 准则
adf_result = adfuller(spread.values, autolag='BIC')

# 或手动指定
adf_result = adfuller(spread.values, maxlag=5)
```

**选择原则**：
- **AIC**：倾向于选择更多滞后项（更保守）
- **BIC**：倾向于选择更少滞后项（更简洁）
- **maxlag**：手动指定最大滞后阶数

#### 4.2.2 回归形式选择

**三种回归形式**：
1. **无常数项、无趋势项**：`regression='nc'`
2. **有常数项、无趋势项**：`regression='c'`（默认，最常用）
3. **有常数项、有趋势项**：`regression='ct'`

**选择建议**：
- 对于价差序列，通常使用 `regression='c'`（有常数项）
- 如果价差有明显趋势，考虑使用 `regression='ct'`

### 4.3 ADF检验的局限性

#### 4.3.1 检验功效问题

**问题**：
- ADF 检验在样本量较小时，检验功效（power）较低
- 可能无法拒绝非平稳的原假设，即使序列实际上是平稳的

**解决方案**：
- 增加样本量（建议至少50-100个观测值）
- 使用其他检验方法作为补充（如 KPSS 检验）

#### 4.3.2 结构突变问题

**问题**：
- 如果序列存在结构突变（如 Beta 漂移），ADF 检验可能失效
- 需要先检测结构突变，再进行协整检验

**解决方案**：
- 使用滚动窗口检验
- 使用时变协整模型

---

## 第5章：优缺点分析

### 5.1 Engle-Granger 方法的优点

#### 5.1.1 简单直观

**优势**：
- 方法简单，易于理解和实现
- 只需要基本的 OLS 回归和 ADF 检验
- 结果容易解释

**适用场景**：
- 快速验证两个变量是否存在协整关系
- 配对交易策略的初步筛选

#### 5.1.2 计算效率高

**优势**：
- 计算速度快，适合实时交易
- 不需要复杂的数值优化
- 内存占用小

#### 5.1.3 结果可解释性强

**优势**：
- $\beta$ 系数有明确的经济含义（对冲比例）
- $\alpha$ 系数表示价格溢价/折价
- 价差序列可以直接用于交易信号

### 5.2 Engle-Granger 方法的缺点

#### 5.2.1 仅适用于两个变量

**限制**：
- 只能检验两个变量之间的协整关系
- 无法同时处理多个变量
- 如果涉及3个或更多变量，需要其他方法（如 Johansen 检验）

#### 5.2.2 变量选择问题

**问题**：
- 需要预先指定哪个变量作为因变量
- 不同的选择可能得到不同的结果
- 理论上应该对两个方向都进行检验

**解决方案**：
```python
# 检验方向1：Y 对 X 回归
result1 = engle_granger_test(X, Y)

# 检验方向2：X 对 Y 回归
result2 = engle_granger_test(Y, X)

# 如果任一方向通过，则认为协整成立
is_cointegrated = result1['is_cointegrated'] or result2['is_cointegrated']
```

#### 5.2.3 只能检测一个协整关系

**限制**：
- 如果存在多个协整关系，只能检测到其中一个
- 对于多变量系统，可能遗漏其他协整关系

#### 5.2.4 小样本问题

**问题**：
- 在样本量较小时，检验功效较低
- OLS 估计在小样本下可能不准确
- ADF 检验的临界值在小样本下可能不适用

**建议**：
- 至少需要50-100个观测值
- 对于高频数据，可以使用更长的历史窗口

#### 5.2.5 参数估计的渐近性质

**问题**：
- OLS 估计在协整关系下具有"超一致性"（super-consistency）
- 但在有限样本下，估计可能仍有偏差
- 标准误的计算需要特殊方法（Newey-West 调整）

### 5.3 适用场景总结

**适合使用 Engle-Granger 的情况**：
- ✅ 只有2个变量
- ✅ 配对交易场景
- ✅ 需要快速实现和解释
- ✅ 样本量较大（>50）
- ✅ 变量之间有明确的因果关系

**不适合使用的情况**：
- ❌ 3个或更多变量
- ❌ 需要检测多个协整关系
- ❌ 样本量很小（<30）
- ❌ 需要严格的统计推断

---

## 第6章：与Johansen检验对比

### 6.1 方法对比表

| 特性 | Engle-Granger | Johansen |
|------|---------------|----------|
| **适用变量数** | 仅2个变量 | 多个变量（≥2） |
| **协整关系数** | 只能检测1个 | 可以检测多个 |
| **方法类型** | 两步法 | 系统方法 |
| **理论基础** | 基于残差平稳性 | 基于VAR模型 |
| **实现难度** | 简单 | 较复杂 |
| **计算速度** | 快 | 较慢 |
| **统计性质** | 渐近有效 | 更优 |

### 6.2 数学原理对比

#### 6.2.1 Engle-Granger 方法

**模型**：
```
Y_t = α + βX_t + ε_t
检验：ε_t 是否平稳
```

**特点**：
- 单方程模型
- 需要预先指定因变量
- 基于残差检验

#### 6.2.2 Johansen 方法

**模型**：
```
ΔY_t = ΠY_{t-1} + Γ_1ΔY_{t-1} + ... + ε_t

检验：rank(Π) = r（协整关系的数量）
```

**特点**：
- 多方程系统
- 不需要预先指定因变量
- 基于矩阵秩检验

### 6.3 实际应用建议

#### 6.3.1 何时使用 Engle-Granger？

**推荐场景**：
1. **配对交易**：只有2个资产，如 HYPE/PURR
2. **快速筛选**：需要快速验证大量资产对
3. **实时交易**：需要低延迟的计算
4. **易于解释**：需要向非技术人员解释结果

#### 6.3.2 何时使用 Johansen？

**推荐场景**：
1. **多资产组合**：3个或更多资产
2. **学术研究**：需要严格的统计推断
3. **复杂系统**：可能存在多个协整关系
4. **长期分析**：不追求实时性

### 6.4 代码对比示例

#### Engle-Granger 实现（简单）
```python
# 只需几行代码
model = LinearRegression()
model.fit(log_base, log_alt)
spread = log_alt - model.predict(log_base)
adf_result = adfuller(spread)
```

#### Johansen 实现（复杂）
```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen

# 需要准备多变量数据
data = pd.DataFrame({
    'var1': series1,
    'var2': series2,
    'var3': series3
})

# 需要选择参数
result = coint_johansen(
    data, 
    det_order=0,      # 确定性项
    k_ar_diff=1       # 滞后阶数
)

# 需要解释多个统计量
trace_stat = result.lr1
max_eigen_stat = result.lr2
```

---

## 第7章：代码实现详解

### 7.1 项目中的实现

#### 7.1.1 核心函数：`_calculate_cointegration_params`

**代码位置**：`purr5.py` 第375-454行

**功能**：
- 使用 OLS 回归计算协整参数
- 进行 ADF 检验验证价差平稳性
- 返回完整的协整检验结果

**完整代码**：
```python
@staticmethod
def _calculate_cointegration_params(base_prices: pd.Series, 
                                     alt_prices: pd.Series,
                                     coin: str = None) -> Optional[dict]:
    """
    使用OLS回归计算协整参数（验证性函数）
    
    通过OLS回归计算截距项α和斜率β，并进行ADF检验验证价差平稳性。
    这是协整检验的标准方法（Engle-Granger两步法）。
    """
    try:
        # 1. 数据验证
        if len(base_prices) != len(alt_prices):
            return None
        
        if len(base_prices) < 10:
            return None
        
        # 2. 计算对数价格
        log_base_series = np.log(base_prices)
        log_alt_series = np.log(alt_prices)
        
        # 3. OLS回归
        log_base = log_base_series.values.reshape(-1, 1)
        log_alt = log_alt_series.values
        
        model = LinearRegression()
        model.fit(log_base, log_alt)
        
        alpha = model.intercept_
        beta = model.coef_[0]
        
        # 4. 计算OLS价差（残差）
        spread_ols = log_alt_series - (alpha + beta * log_base_series)
        
        # 5. ADF检验价差平稳性
        adf_result = adfuller(spread_ols.values, autolag='AIC')
        adf_pvalue = adf_result[1]
        
        return {
            'alpha': alpha,
            'beta': beta,
            'spread': spread_ols,
            'adf_pvalue': adf_pvalue
        }
    except Exception as e:
        return None
```

#### 7.1.2 实时交易函数：`price_diff_spread_ols_window`

**代码位置**：`purr5.py` 第456-499行

**功能**：
- 使用滚动窗口避免 look-ahead bias
- 适合实时交易场景
- 双窗口策略：长窗口估计 Beta，短窗口计算统计量

**关键设计**：
```python
# 使用前 beta_window-1 个点计算OLS参数（避免 look-ahead bias）
ols_base = recent_base_full.iloc[:-1]
ols_alt = recent_alt_full.iloc[:-1]

# 使用最后 zscore_window 个点计算价差和统计量
recent_base = recent_base_full.iloc[-zscore_window:]
recent_alt = recent_alt_full.iloc[-zscore_window:]
```

### 7.2 改进建议

#### 7.2.1 双向检验

**当前实现**：只检验一个方向（alt 对 base）

**改进建议**：
```python
def bidirectional_engle_granger_test(base_prices, alt_prices):
    """双向 Engle-Granger 检验"""
    # 方向1：alt 对 base
    result1 = _calculate_cointegration_params(base_prices, alt_prices)
    
    # 方向2：base 对 alt
    result2 = _calculate_cointegration_params(alt_prices, base_prices)
    
    # 选择更好的结果
    if result1 and result2:
        if result1['adf_pvalue'] < result2['adf_pvalue']:
            return result1
        else:
            return result2
    elif result1:
        return result1
    elif result2:
        return result2
    else:
        return None
```

#### 7.2.2 置信区间计算

**当前实现**：只提供点估计

**改进建议**：
```python
from scipy import stats

def calculate_beta_confidence_interval(log_base, log_alt, beta, alpha, confidence=0.95):
    """计算 Beta 的置信区间"""
    n = len(log_base)
    residuals = log_alt - (alpha + beta * log_base.flatten())
    mse = np.sum(residuals**2) / (n - 2)
    
    x_mean = np.mean(log_base)
    sxx = np.sum((log_base.flatten() - x_mean)**2)
    
    se_beta = np.sqrt(mse / sxx)
    t_critical = stats.t.ppf((1 + confidence) / 2, n - 2)
    
    beta_lower = beta - t_critical * se_beta
    beta_upper = beta + t_critical * se_beta
    
    return beta_lower, beta_upper
```

#### 7.2.3 滚动窗口检验

**改进建议**：
```python
def rolling_cointegration_test(base_prices, alt_prices, window=100, step=10):
    """滚动窗口协整检验，检测 Beta 稳定性"""
    results = []
    
    for i in range(window, len(base_prices), step):
        base_window = base_prices.iloc[i-window:i]
        alt_window = alt_prices.iloc[i-window:i]
        
        result = _calculate_cointegration_params(base_window, alt_window)
        if result:
            result['window_end'] = base_prices.index[i]
            results.append(result)
    
    return pd.DataFrame(results)
```

---

## 第8章：实战应用案例

### 8.1 项目中的实际应用

#### 8.1.1 协整检验流程

**在 `purr5.py` 中的调用**：
```python
# 1. 计算协整参数
ols_params = DelayCorrelationAnalyzer._calculate_cointegration_params(
    base_prices, alt_prices, coin=coin
)

# 2. 分析协整结果
self.cointegration_analysis(ols_params, 'old', coin, stats_period_key)

# 3. 使用滚动窗口方法（实时交易）
cointegration_result = DelayCorrelationAnalyzer.price_diff_spread_ols_window(
    base_prices, alt_prices, beta_window, zscore_window
)

# 4. 再次分析
self.cointegration_analysis(cointegration_result, 'new', coin, stats_period_key)
```

#### 8.1.2 协整分析函数

**`cointegration_analysis` 函数**：
```python
def cointegration_analysis(self, cointegration_result: dict, 
                          method_type: str, coin: str = None, 
                          stats_period_key: tuple = None) -> dict:
    """
    协整分析
    
    判断标准：ADF p-value < 0.05 表示协整成立
    """
    if cointegration_result is None or cointegration_result['adf_pvalue'] >= 0.05:
        # 协整检验未通过
        logger.info(f"❌ 协整检验未通过 | "
                   f"α={cointegration_result['alpha']:.4f}, "
                   f"β={cointegration_result['beta']:.4f} | "
                   f"ADF p-value: {cointegration_result['adf_pvalue']:.4f} >= 0.05")
        return {'is_cointegrated': False}
    else:
        # 协整检验通过
        logger.info(f"✅ 协整检验通过 | "
                   f"α={cointegration_result['alpha']:.4f}, "
                   f"β={cointegration_result['beta']:.4f} | "
                   f"ADF p-value={cointegration_result['adf_pvalue']:.4f} < 0.05")
        return {'is_cointegrated': True}
```

### 8.2 实际案例：HYPE/PURR 配对

#### 8.2.1 数据准备

**假设数据**：
- HYPE 价格序列：100个观测值
- PURR 价格序列：100个观测值
- 时间窗口：最近100个周期

#### 8.2.2 检验过程

**步骤1：对数变换**
```python
log_hype = np.log(hype_prices)
log_purr = np.log(purr_prices)
```

**步骤2：OLS回归**
```python
model = LinearRegression()
model.fit(log_hype.values.reshape(-1, 1), log_purr.values)

alpha = 0.15  # 截距项
beta = 1.48   # 斜率系数（对冲比例）
```

**步骤3：计算价差**
```python
spread = log_purr - (alpha + beta * log_hype)
```

**步骤4：ADF检验**
```python
adf_result = adfuller(spread.values, autolag='AIC')
adf_pvalue = 0.023  # p值
```

**步骤5：判断结果**
```python
if adf_pvalue < 0.05:
    print("✅ 协整检验通过：HYPE 和 PURR 存在协整关系")
    print(f"对冲比例 β = {beta:.2f}")
    print(f"价差均值回归，适合配对交易")
else:
    print("❌ 协整检验未通过：不适合配对交易")
```

#### 8.2.3 结果解读

**如果协整成立**：
- $\beta = 1.48$：HYPE 涨1%，PURR 平均涨1.48%
- $\alpha = 0.15$：PURR 相对 HYPE 有15%的溢价
- 价差序列平稳：可以计算 Z-score 进行交易

**交易策略**：
- 当 Z-score > 2：价差偏高，做空 PURR，做多 HYPE
- 当 Z-score < -2：价差偏低，做多 PURR，做空 HYPE
- 当 |Z-score| < 0.5：价差回归，平仓

### 8.3 常见问题处理

#### 8.3.1 协整检验不通过

**可能原因**：
1. 两个币种确实没有长期关系
2. 样本量不足
3. 存在结构突变（Beta 漂移）

**解决方案**：
- 增加样本量
- 使用滚动窗口重新检验
- 检查是否存在 Beta 漂移

#### 8.3.2 Beta 值不稳定

**问题**：不同时间窗口得到的 Beta 值差异很大

**解决方案**：
- 使用自适应窗口选择
- 监控 Beta 稳定性
- 使用加权回归（近期数据权重更大）

---

## 第9章：常见问题与注意事项

### 9.1 数据要求

#### 9.1.1 最小样本量

**建议**：
- 最少需要 **30-50** 个观测值
- 推荐使用 **100+** 个观测值
- 对于高频数据（如1分钟K线），可以使用更长的历史窗口

**原因**：
- ADF 检验在小样本下功效较低
- OLS 估计需要足够的数据点

#### 9.1.2 数据质量

**要求**：
- 两个序列必须对齐（相同的时间点）
- 处理缺失值（删除或插值）
- 处理异常值（Winsorize 或删除）

**代码示例**：
```python
# 对齐数据
aligned_data = pd.DataFrame({
    'base': base_prices,
    'alt': alt_prices
}).dropna()

# 处理异常值（Winsorize）
from scipy.stats import mstats
aligned_data['base'] = mstats.winsorize(aligned_data['base'], limits=[0.01, 0.01])
aligned_data['alt'] = mstats.winsorize(aligned_data['alt'], limits=[0.01, 0.01])
```

### 9.2 参数选择

#### 9.2.1 ADF 检验参数

**滞后阶数选择**：
- **autolag='AIC'**：自动选择，推荐
- **autolag='BIC'**：更保守，选择更少滞后项
- **maxlag=5**：手动指定

**回归形式选择**：
- **regression='c'**：有常数项（默认，最常用）
- **regression='nc'**：无常数项
- **regression='ct'**：有常数项和趋势项

#### 9.2.2 显著性水平

**常用水平**：
- **0.05**（5%）：标准水平，推荐
- **0.01**（1%）：更严格
- **0.10**（10%）：更宽松

**选择建议**：
- 配对交易：使用 0.05
- 严格筛选：使用 0.01
- 初步筛选：可以使用 0.10

### 9.3 常见误区

#### 9.3.1 混淆相关性和协整

**错误理解**：
- 认为高相关性就意味着协整
- 认为协整就是相关性

**正确理解**：
- **相关性**：衡量两个序列的线性关系强度
- **协整**：衡量两个序列的长期均衡关系
- 高相关性不一定协整，协整也不一定高相关

**例子**：
- 两个随机游走序列可能高度相关，但不协整
- 两个协整序列可能短期相关性较低

#### 9.3.2 忽略 Beta 漂移

**问题**：
- 假设 Beta 是常数
- 不监控 Beta 的变化

**正确做法**：
- 定期重新估计 Beta
- 监控 Beta 的稳定性
- 使用滚动窗口检验

#### 9.3.3 Look-ahead Bias

**问题**：
- 使用未来数据估计参数
- 在实时交易中无法实现

**正确做法**：
- 使用历史数据估计参数
- 使用滚动窗口避免未来信息泄露
- 分离训练集和测试集

### 9.4 性能优化

#### 9.4.1 计算效率

**优化建议**：
```python
# 使用向量化操作
log_base = np.log(base_prices.values).reshape(-1, 1)
log_alt = np.log(alt_prices.values)

# 避免循环
spread = log_alt - (alpha + beta * log_base.flatten())

# 批量处理多个资产对
results = []
for pair in asset_pairs:
    result = engle_granger_test(pair['base'], pair['alt'])
    results.append(result)
```

#### 9.4.2 内存优化

**优化建议**：
- 使用生成器处理大量数据
- 及时释放不需要的中间变量
- 使用 `del` 删除大对象

---

## 第10章：改进方向与扩展

### 10.1 理论扩展

#### 10.1.1 时变协整

**问题**：传统 Engle-Granger 假设 Beta 是常数

**扩展方向**：
- Markov-Switching 协整模型
- 时变参数协整模型
- 门限协整模型

#### 10.1.2 非线性协整

**问题**：线性协整可能无法捕捉非线性关系

**扩展方向**：
- 非线性协整检验
- 神经网络协整模型

### 10.2 方法改进

#### 10.2.1 增强的 Engle-Granger 检验

**改进点**：
1. 双向检验（两个方向都检验）
2. 置信区间计算
3. 滚动窗口稳定性监控
4. 结构突变检测

#### 10.2.2 结合其他检验方法

**建议**：
- 结合 KPSS 检验（互补）
- 结合 Phillips-Ouliaris 检验
- 使用多种方法交叉验证

### 10.3 实际应用扩展

#### 10.3.1 多资产配对

**扩展**：
- 从2个资产扩展到3个或更多
- 使用 Johansen 检验
- 构建多资产组合

#### 10.3.2 动态调整

**扩展**：
- 实时监控协整关系
- 自动调整 Beta
- 自适应窗口选择

### 10.4 代码改进建议

#### 10.4.1 完整的实现示例

```python
class EnhancedEngleGranger:
    """增强版 Engle-Granger 检验"""
    
    def __init__(self, significance_level=0.05):
        self.significance_level = significance_level
    
    def test(self, base_prices, alt_prices, bidirectional=True):
        """完整的协整检验"""
        # 1. 数据预处理
        base_prices, alt_prices = self._preprocess(base_prices, alt_prices)
        
        # 2. 双向检验（可选）
        if bidirectional:
            result1 = self._test_direction(base_prices, alt_prices)
            result2 = self._test_direction(alt_prices, base_prices)
            return self._select_best_result(result1, result2)
        else:
            return self._test_direction(base_prices, alt_prices)
    
    def _test_direction(self, x, y):
        """单方向检验"""
        # OLS回归
        model = LinearRegression()
        model.fit(x.values.reshape(-1, 1), y.values)
        
        # 计算残差
        spread = y - (model.intercept_ + model.coef_[0] * x)
        
        # ADF检验
        adf_result = adfuller(spread.values, autolag='AIC')
        
        # 计算置信区间
        beta_ci = self._calculate_confidence_interval(x, y, model)
        
        return {
            'alpha': model.intercept_,
            'beta': model.coef_[0],
            'beta_ci': beta_ci,
            'spread': spread,
            'adf_pvalue': adf_result[1],
            'adf_statistic': adf_result[0],
            'is_cointegrated': adf_result[1] < self.significance_level
        }
```

---

## 总结

### 核心要点

1. **Engle-Granger 两步法**是协整检验的经典方法，简单直观
2. **适用场景**：2个变量的配对交易
3. **关键步骤**：OLS回归 + ADF检验
4. **判断标准**：ADF p-value < 0.05 表示协整成立
5. **注意事项**：避免 look-ahead bias，监控 Beta 稳定性

### 在项目中的应用

- ✅ 已实现基本的 Engle-Granger 检验
- ✅ 使用滚动窗口避免未来信息泄露
- ✅ 结合 Beta 稳定性监控
- 🔄 可改进：双向检验、置信区间、结构突变检测

### 进一步学习

- **理论**：Engle & Granger (1987) 原始论文
- **实践**：项目中的 `purr5.py` 实现
- **扩展**：Johansen 检验、时变协整模型

---

**文档版本**：v1.0  
**最后更新**：2024年  
**基于项目**：hyperliquid-pair-hype-purr-analyze

