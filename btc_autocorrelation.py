import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import acf
from statsmodels.graphics.tsaplots import plot_acf

# 1. 获取过去 5 年的 BTC 周线数据
ticker = "BTC-USD"
data = yf.download(ticker, period="5y", interval="1wk")

# 2. 计算周收益率 (对数收益率更能反映统计特性)
data['Log_Return'] = pd.Series(data['Close']).apply(lambda x: pd.np.log(x)).diff()
returns = data['Log_Return'].dropna()

# 3. 计算具体的自相关系数值 (前 10 阶)
acf_values = acf(returns, nlags=10)
acf_df = pd.DataFrame({'Lag': range(len(acf_values)), 'ACF': acf_values})
print("BTC 周线收益率前 10 阶自相关系数:")
print(acf_df)

# 4. 可视化 ACF 图
plt.figure(figsize=(10, 6))
plot_acf(returns, lags=20, alpha=0.05) # alpha=0.05 表示 95% 置信区间
plt.title(f"BTC Weekly Returns Autocorrelation (Last 5 Years)")
plt.xlabel("Lags (Weeks)")
plt.ylabel("Autocorrelation")
plt.show()