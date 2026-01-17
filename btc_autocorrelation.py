import warnings
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns

HAS_STATSMODELS = True
try:
    from statsmodels.tsa.stattools import acf, pacf, grangercausalitytests
    from statsmodels.tsa.ar_model import AutoReg
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.regression.quantile_regression import QuantReg
    from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression
except Exception:
    HAS_STATSMODELS = False

HAS_SKLEARN = True
try:
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import (
        mean_absolute_error,
        mean_squared_error,
        r2_score,
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
    )
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    from sklearn.neural_network import MLPRegressor, MLPClassifier
    from sklearn.svm import SVC
    from sklearn.preprocessing import StandardScaler, PolynomialFeatures
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.feature_selection import mutual_info_regression
    from sklearn.inspection import permutation_importance
except Exception:
    HAS_SKLEARN = False

HAS_ARCH = True
try:
    from arch import arch_model
except Exception:
    HAS_ARCH = False

HAS_XGBOOST = True
try:
    from xgboost import XGBRegressor, XGBClassifier
except Exception:
    HAS_XGBOOST = False

HAS_LIGHTGBM = True
try:
    from lightgbm import LGBMRegressor, LGBMClassifier
except Exception:
    HAS_LIGHTGBM = False

HAS_SCIPY = True
try:
    from scipy.optimize import minimize
    from scipy import stats
except Exception:
    HAS_SCIPY = False

HAS_PYINFORM = True
try:
    from pyinform import transferentropy
except Exception:
    HAS_PYINFORM = False

HAS_TENSORFLOW = True
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
except Exception:
    HAS_TENSORFLOW = False

HAS_NETWORKX = True
try:
    import networkx as nx
except Exception:
    HAS_NETWORKX = False

HAS_TABULATE = True
try:
    from tabulate import tabulate
except Exception:
    HAS_TABULATE = False


MAX_LAG = 100
AR_MAX_ORDER = 20
ARMA_MAX_P = 10
ARMA_MAX_Q = 10
ARIMA_MAX_P = 10
ARIMA_MAX_Q = 10
ARIMA_D_VALUES = (0, 1)
ROLL_WINDOWS = (4, 12, 26, 52)
TEST_RATIO = 0.2
RANDOM_SEED = 42
STREAK_MIN_N = 2
STREAK_MAX_N = 12
STREAK_MIN_SAMPLES = 50
STREAK_THRESHOLDS = np.round(np.linspace(0.01, 0.20, 20), 4)
STREAK_SIGNIFICANCE_Z = 1.96

# 新增配置常量
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
N_REGIMES = 2
LSTM_LOOKBACK = 20
LSTM_EPOCHS = 50
LSTM_BATCH_SIZE = 32
INFLUENCE_METHODS = ['granger', 'mutual_info', 'transfer_entropy', 'acf', 'pacf']
TRANSITION_BINS = 5


def load_returns(ticker="BTC-USD", period="10y", interval="1wk"):
    data = yf.download(ticker, period=period, interval=interval, progress=False)
    if data is None or data.empty:
        raise ValueError("数据下载失败或为空")
    log_returns = np.log(data["Close"]).diff().dropna()
    if isinstance(log_returns, pd.DataFrame):
        if log_returns.shape[1] == 1:
            log_returns = log_returns.iloc[:, 0]
        else:
            raise ValueError("Close 列维度异常，无法转换为单一序列")
    if not isinstance(log_returns, pd.Series):
        log_returns = pd.Series(log_returns)
    log_returns.name = "returns"
    return log_returns


def compute_acf_pacf(returns, max_lag=MAX_LAG):
    if not HAS_STATSMODELS:
        raise RuntimeError("statsmodels 未安装，无法计算 ACF/PACF")
    acf_values = acf(returns, nlags=max_lag, fft=True)
    pacf_values = pacf(returns, nlags=max_lag, method="ywm")
    conf_interval = 1.96 / np.sqrt(len(returns))
    max_acf_lag = int(np.argmax(np.abs(acf_values[1:])) + 1)
    max_pacf_lag = int(np.argmax(np.abs(pacf_values[1:])) + 1)
    return {
        "acf": acf_values,
        "pacf": pacf_values,
        "conf_interval": conf_interval,
        "max_acf_lag": max_acf_lag,
        "max_pacf_lag": max_pacf_lag,
    }


def compute_sign_acf(returns, max_lag=MAX_LAG):
    if not HAS_STATSMODELS:
        raise RuntimeError("statsmodels 未安装，无法计算符号 ACF")
    sign_returns = np.sign(returns)
    acf_values = acf(sign_returns, nlags=max_lag, fft=True)
    conf_interval = 1.96 / np.sqrt(len(sign_returns))
    max_acf_lag = int(np.argmax(np.abs(acf_values[1:])) + 1)
    return {
        "acf": acf_values,
        "conf_interval": conf_interval,
        "max_acf_lag": max_acf_lag,
    }


# ============================================================================
# 模块1: 高级统计分析
# ============================================================================

def compute_granger_causality(returns, max_lag=MAX_LAG):
    """
    计算Granger因果检验,识别哪些滞后期对当前收益率有显著因果影响
    """
    if not HAS_STATSMODELS:
        print("警告: statsmodels 未安装,跳过Granger因果检验")
        return None

    print("  → 计算Granger因果检验...")
    results = []

    # 准备数据: 创建二维数据框
    df = pd.DataFrame({'returns': returns})

    for lag in range(1, min(max_lag + 1, len(returns) // 5)):
        try:
            # Granger检验需要二维数据
            test_data = pd.DataFrame({
                'y': returns[lag:].values,
                'x': returns[:-lag].values
            })

            # 执行Granger因果检验(maxlag=1因为我们已经手动创建了滞后)
            gc_result = grangercausalitytests(test_data[['y', 'x']], maxlag=1, verbose=False)

            # 提取F统计量和p值
            f_stat = gc_result[1][0]['ssr_ftest'][0]
            p_value = gc_result[1][0]['ssr_ftest'][1]

            results.append({
                'lag': lag,
                'f_stat': f_stat,
                'p_value': p_value,
                'significant': p_value < 0.05
            })
        except Exception as e:
            continue

    if results:
        df_results = pd.DataFrame(results)
        print(f"  → 完成Granger检验, {df_results['significant'].sum()}/{len(df_results)} 个滞后期显著")
        return df_results
    else:
        return None


def compute_mutual_information(returns, max_lag=MAX_LAG):
    """
    计算互信息,测量非线性依赖关系
    """
    if not HAS_SKLEARN:
        print("警告: sklearn 未安装,跳过互信息计算")
        return None

    print("  → 计算互信息...")
    results = []

    for lag in range(1, max_lag + 1):
        if lag >= len(returns):
            break

        try:
            X = returns[:-lag].values.reshape(-1, 1)
            y = returns[lag:].values

            mi = mutual_info_regression(X, y, random_state=RANDOM_SEED)

            results.append({
                'lag': lag,
                'mutual_info': mi[0]
            })
        except Exception:
            continue

    if results:
        df_results = pd.DataFrame(results)
        print(f"  → 完成互信息计算, 最大MI滞后期: lag_{df_results.loc[df_results['mutual_info'].idxmax(), 'lag']:.0f}")
        return df_results
    else:
        return None


def compute_transfer_entropy(returns, max_lag=MAX_LAG):
    """
    计算转移熵,测量信息传递方向和强度
    """
    if not HAS_PYINFORM:
        print("警告: pyinform 未安装,跳过转移熵计算")
        return None

    print("  → 计算转移熵...")
    results = []

    # 离散化收益率(转移熵需要离散值)
    bins = 5
    discretized = pd.cut(returns, bins=bins, labels=False)

    for lag in range(1, min(max_lag + 1, 30)):  # 限制到30以提高效率
        if lag >= len(discretized):
            break

        try:
            source = discretized[:-lag].values.astype(int)
            target = discretized[lag:].values.astype(int)

            # 计算转移熵
            te = transferentropy.transfer_entropy(source, target, k=1)

            results.append({
                'lag': lag,
                'transfer_entropy': te
            })
        except Exception:
            continue

    if results:
        df_results = pd.DataFrame(results)
        print(f"  → 完成转移熵计算, 最大TE滞后期: lag_{df_results.loc[df_results['transfer_entropy'].idxmax(), 'lag']:.0f}")
        return df_results
    else:
        return None


def compute_conditional_heteroskedasticity(returns):
    """
    检验条件异方差性(ARCH效应)
    """
    if not HAS_STATSMODELS:
        print("警告: statsmodels 未安装,跳过ARCH检验")
        return None

    print("  → 检验条件异方差性...")

    try:
        # Engle's ARCH test
        from statsmodels.stats.diagnostic import het_arch

        lags = min(10, len(returns) // 10)
        lm_stat, lm_pvalue, f_stat, f_pvalue = het_arch(returns, nlags=lags)

        result = {
            'lm_stat': lm_stat,
            'lm_pvalue': lm_pvalue,
            'f_stat': f_stat,
            'f_pvalue': f_pvalue,
            'has_arch_effect': lm_pvalue < 0.05
        }

        print(f"  → ARCH效应检验: {'存在' if result['has_arch_effect'] else '不存在'} (p={lm_pvalue:.4f})")
        return result
    except Exception as e:
        print(f"  → ARCH检验失败: {e}")
        return None


# ============================================================================
# 模块2: 收益率正负分离分析
# ============================================================================

def compute_asymmetric_acf(returns, max_lag=MAX_LAG):
    """
    分别计算正收益率和负收益率的自相关
    """
    if not HAS_STATSMODELS:
        print("警告: statsmodels 未安装,跳过不对称ACF计算")
        return None

    print("  → 计算正负收益率不对称ACF...")

    pos_returns = returns[returns > 0]
    neg_returns = returns[returns < 0]

    if len(pos_returns) < max_lag or len(neg_returns) < max_lag:
        print("  → 警告: 正或负收益率样本不足,减少max_lag")
        max_lag = min(len(pos_returns) // 2, len(neg_returns) // 2, max_lag)

    try:
        pos_acf = acf(pos_returns, nlags=max_lag, fft=True)
        neg_acf = acf(neg_returns, nlags=max_lag, fft=True)

        # 计算不对称指数
        asymmetry_index = np.mean(np.abs(neg_acf[1:]) - np.abs(pos_acf[1:]))

        conf_interval_pos = 1.96 / np.sqrt(len(pos_returns))
        conf_interval_neg = 1.96 / np.sqrt(len(neg_returns))

        result = {
            'pos_acf': pos_acf,
            'neg_acf': neg_acf,
            'asymmetry_index': asymmetry_index,
            'conf_interval_pos': conf_interval_pos,
            'conf_interval_neg': conf_interval_neg,
            'n_pos': len(pos_returns),
            'n_neg': len(neg_returns)
        }

        print(f"  → 不对称指数: {asymmetry_index:.4f} ({'负收益更持续' if asymmetry_index > 0 else '正收益更持续'})")
        return result
    except Exception as e:
        print(f"  → 不对称ACF计算失败: {e}")
        return None


def compute_transition_matrix(returns, bins=TRANSITION_BINS):
    """
    构建收益率状态转换矩阵
    """
    print(f"  → 构建{bins}状态转换矩阵...")

    # 将收益率离散化为bins个状态
    labels = [f"状态{i+1}" for i in range(bins)]
    states = pd.cut(returns, bins=bins, labels=labels)

    # 构建转换矩阵
    transition_counts = pd.crosstab(states[:-1], states[1:])
    transition_prob = transition_counts.div(transition_counts.sum(axis=1), axis=0)

    # 计算平稳分布(特征向量方法)
    try:
        eigenvalues, eigenvectors = np.linalg.eig(transition_prob.T)
        stationary_idx = np.argmax(eigenvalues.real)
        stationary_dist = np.abs(eigenvectors[:, stationary_idx].real)
        stationary_dist = stationary_dist / stationary_dist.sum()
    except Exception:
        stationary_dist = None

    result = {
        'transition_prob': transition_prob,
        'transition_counts': transition_counts,
        'stationary_dist': stationary_dist,
        'states': states
    }

    print(f"  → 转换矩阵构建完成, 对角线均值: {np.diag(transition_prob.values).mean():.3f}")
    return result


def compute_quantile_autoregression(returns, quantiles=QUANTILES):
    """
    分位数自回归分析
    """
    if not HAS_STATSMODELS:
        print("警告: statsmodels 未安装,跳过分位数自回归")
        return None

    print(f"  → 计算分位数自回归 (分位数: {quantiles})...")

    # 准备数据
    df = pd.DataFrame({
        'y': returns[1:].values,
        'lag1': returns[:-1].values
    })

    results = {}
    for q in quantiles:
        try:
            model = QuantReg(df['y'], df[['lag1']])
            result = model.fit(q=q)
            results[f'q{q}'] = {
                'coef': result.params['lag1'],
                'pvalue': result.pvalues['lag1']
            }
        except Exception:
            continue

    if results:
        print(f"  → 完成分位数自回归, {len(results)}个分位数")
        return results
    else:
        return None


def compute_directional_persistence(returns, max_lag=MAX_LAG):
    """
    计算方向持续性指标
    """
    print("  → 计算方向持续性...")

    directions = np.sign(returns)
    results = []

    for lag in range(1, max_lag + 1):
        if lag >= len(directions):
            break

        # P(+|+): 上涨后继续上涨
        pos_followed_by_pos = np.sum((directions[:-lag] > 0) & (directions[lag:] > 0))
        total_pos = np.sum(directions[:-lag] > 0)
        p_pos_given_pos = pos_followed_by_pos / total_pos if total_pos > 0 else 0

        # P(-|-): 下跌后继续下跌
        neg_followed_by_neg = np.sum((directions[:-lag] < 0) & (directions[lag:] < 0))
        total_neg = np.sum(directions[:-lag] < 0)
        p_neg_given_neg = neg_followed_by_neg / total_neg if total_neg > 0 else 0

        # P(+|-): 下跌后反转上涨
        neg_followed_by_pos = np.sum((directions[:-lag] < 0) & (directions[lag:] > 0))
        p_pos_given_neg = neg_followed_by_pos / total_neg if total_neg > 0 else 0

        # P(-|+): 上涨后反转下跌
        pos_followed_by_neg = np.sum((directions[:-lag] > 0) & (directions[lag:] < 0))
        p_neg_given_pos = pos_followed_by_neg / total_pos if total_pos > 0 else 0

        results.append({
            'lag': lag,
            'p_pos_given_pos': p_pos_given_pos,
            'p_neg_given_neg': p_neg_given_neg,
            'p_pos_given_neg': p_pos_given_neg,
            'p_neg_given_pos': p_neg_given_pos,
            'persistence_score': (p_pos_given_pos + p_neg_given_neg) / 2
        })

    df_results = pd.DataFrame(results)
    print(f"  → 方向持续性计算完成, 平均持续得分: {df_results['persistence_score'].mean():.3f}")
    return df_results


def make_feature_frame(returns, max_lag=MAX_LAG, roll_windows=ROLL_WINDOWS):
    if isinstance(returns, pd.DataFrame):
        if returns.shape[1] == 1:
            returns = returns.iloc[:, 0]
        else:
            raise ValueError("returns 维度异常，无法转换为单一序列")
    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)
    df = pd.DataFrame({"y": returns})
    for lag in range(1, max_lag + 1):
        df[f"lag_{lag}"] = returns.shift(lag)
        df[f"sign_lag_{lag}"] = np.sign(returns.shift(lag))
        df[f"abs_lag_{lag}"] = np.abs(returns.shift(lag))
    for window in roll_windows:
        shifted = returns.shift(1)
        df[f"roll_mean_{window}"] = shifted.rolling(window).mean()
        df[f"roll_std_{window}"] = shifted.rolling(window).std()
        df[f"roll_skew_{window}"] = shifted.rolling(window).skew()
        df[f"roll_kurt_{window}"] = shifted.rolling(window).kurt()
    df = df.dropna()
    X = df.drop(columns=["y"])
    y_value = df["y"]
    y_direction = (y_value > 0).astype(int)
    return X, y_value, y_direction


def train_test_split_series(X, y_value, y_direction, test_ratio=TEST_RATIO):
    split_idx = int(len(X) * (1 - test_ratio))
    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_value_train = y_value.iloc[:split_idx]
    y_value_test = y_value.iloc[split_idx:]
    y_dir_train = y_direction.iloc[:split_idx]
    y_dir_test = y_direction.iloc[split_idx:]
    return X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test


def evaluate_value(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    direction_acc = np.mean(np.sign(y_true) == np.sign(y_pred))
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "direction_acc": direction_acc,
    }


def evaluate_direction(y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    return {
        "accuracy": acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def fit_ar_models(returns, max_order=AR_MAX_ORDER, test_ratio=TEST_RATIO):
    if not HAS_STATSMODELS:
        return []
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]
    results = []
    for order in range(1, max_order + 1):
        try:
            model = AutoReg(train, lags=order, old_names=False).fit()
            preds = model.predict(start=test.index[0], end=test.index[-1])
            metrics = evaluate_value(test, preds)
            results.append(
                {
                    "model": f"AR({order})",
                    "aic": model.aic,
                    "bic": model.bic,
                    "metrics": metrics,
                    "preds": preds,
                }
            )
        except Exception:
            continue
    return results


def fit_arma_models(returns, max_p=ARMA_MAX_P, max_q=ARMA_MAX_Q, test_ratio=TEST_RATIO):
    if not HAS_STATSMODELS:
        return []
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]
    results = []
    for p in range(1, max_p + 1):
        for q in range(1, max_q + 1):
            try:
                model = ARIMA(train, order=(p, 0, q)).fit()
                preds = model.forecast(steps=len(test))
                preds.index = test.index
                metrics = evaluate_value(test, preds)
                results.append(
                    {
                        "model": f"ARMA({p},{q})",
                        "aic": model.aic,
                        "bic": model.bic,
                        "metrics": metrics,
                        "preds": preds,
                    }
                )
            except Exception:
                continue
    return results


def fit_arima_models(returns, max_p=ARIMA_MAX_P, max_q=ARIMA_MAX_Q, d_values=ARIMA_D_VALUES, test_ratio=TEST_RATIO):
    if not HAS_STATSMODELS:
        return []
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]
    results = []
    for d in d_values:
        for p in range(1, max_p + 1):
            for q in range(1, max_q + 1):
                try:
                    model = ARIMA(train, order=(p, d, q)).fit()
                    preds = model.forecast(steps=len(test))
                    preds.index = test.index
                    metrics = evaluate_value(test, preds)
                    results.append(
                        {
                            "model": f"ARIMA({p},{d},{q})",
                            "aic": model.aic,
                            "bic": model.bic,
                            "metrics": metrics,
                            "preds": preds,
                        }
                    )
                except Exception:
                    continue
    return results


def fit_threshold_ar(returns, lag=1, threshold=0.0, test_ratio=TEST_RATIO):
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]
    X_train = pd.DataFrame({"lag_1": train.shift(1)}).dropna()
    y_train = train.loc[X_train.index]
    regime_pos = X_train["lag_1"] > threshold
    regime_neg = X_train["lag_1"] <= threshold
    if regime_pos.sum() < 5 or regime_neg.sum() < 5:
        return None
    X_pos = np.column_stack([np.ones(regime_pos.sum()), X_train.loc[regime_pos, "lag_1"].values])
    X_neg = np.column_stack([np.ones(regime_neg.sum()), X_train.loc[regime_neg, "lag_1"].values])
    y_pos = y_train.loc[regime_pos].values
    y_neg = y_train.loc[regime_neg].values
    beta_pos = np.linalg.lstsq(X_pos, y_pos, rcond=None)[0]
    beta_neg = np.linalg.lstsq(X_neg, y_neg, rcond=None)[0]
    X_test = pd.DataFrame({"lag_1": test.shift(1)}).dropna()
    preds = []
    for idx, row in X_test.iterrows():
        if row["lag_1"] > threshold:
            pred = beta_pos[0] + beta_pos[1] * row["lag_1"]
        else:
            pred = beta_neg[0] + beta_neg[1] * row["lag_1"]
        preds.append(pred)
    preds = pd.Series(preds, index=X_test.index)
    metrics = evaluate_value(test.loc[preds.index], preds)
    return {
        "model": f"TAR(lag={lag}, threshold={threshold})",
        "metrics": metrics,
        "preds": preds,
    }


def fit_star_model(returns, test_ratio=TEST_RATIO):
    if not HAS_SCIPY:
        return None
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]
    lagged = train.shift(1).dropna()
    y = train.loc[lagged.index].values
    x = lagged.values

    def star_resid(params):
        c0, c1, d0, d1, gamma, c = params
        g = 1 / (1 + np.exp(-gamma * (x - c)))
        y_hat = (c0 + c1 * x) + (d0 + d1 * x) * g
        return np.mean((y - y_hat) ** 2)

    init = np.array([0.0, 0.1, 0.0, 0.1, 1.0, 0.0])
    bounds = [(-1, 1), (-5, 5), (-1, 1), (-5, 5), (0.1, 10), (-1, 1)]
    result = minimize(star_resid, init, bounds=bounds)
    if not result.success:
        return None
    c0, c1, d0, d1, gamma, c = result.x
    x_test = test.shift(1).dropna()
    g_test = 1 / (1 + np.exp(-gamma * (x_test.values - c)))
    preds = (c0 + c1 * x_test.values) + (d0 + d1 * x_test.values) * g_test
    preds = pd.Series(preds.flatten(), index=x_test.index)
    metrics = evaluate_value(test.loc[preds.index], preds)
    return {
        "model": "STAR(1)",
        "metrics": metrics,
        "preds": preds,
    }


def fit_garch_model(returns, test_ratio=TEST_RATIO):
    if not HAS_ARCH:
        return None
    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx] * 100
    test = returns.iloc[split_idx:] * 100
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = arch_model(train, mean="Zero", vol="GARCH", p=1, q=1).fit(disp="off")
    forecast = model.forecast(horizon=len(test))
    variance = forecast.variance.iloc[-1]
    volatility = np.sqrt(variance) / 100
    mean_prediction = pd.Series(0.0, index=test.index)
    metrics = evaluate_value(test / 100, mean_prediction)
    return {
        "model": "GARCH(1,1)",
        "metrics": metrics,
        "volatility": volatility,
    }


def fit_ml_models(X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test):
    if not HAS_SKLEARN:
        return {"value": [], "direction": []}
    results_value = []
    results_direction = []

    regressors = {
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=200, random_state=RANDOM_SEED, n_jobs=-1
        ),
        "MLPRegressor": MLPRegressor(
            hidden_layer_sizes=(64, 32), max_iter=500, random_state=RANDOM_SEED
        ),
        "PolyRegression": Pipeline(
            [("poly", PolynomialFeatures(degree=2)), ("lin", LinearRegression())]
        ),
    }

    classifiers = {
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=200, random_state=RANDOM_SEED, n_jobs=-1
        ),
        "SVC": Pipeline(
            [("scaler", StandardScaler()), ("svc", SVC(kernel="rbf", probability=False))]
        ),
        "MLPClassifier": MLPClassifier(
            hidden_layer_sizes=(64, 32), max_iter=500, random_state=RANDOM_SEED
        ),
    }

    if HAS_XGBOOST:
        regressors["XGBRegressor"] = XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=4, random_state=RANDOM_SEED
        )
        classifiers["XGBClassifier"] = XGBClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=4, random_state=RANDOM_SEED
        )

    if HAS_LIGHTGBM:
        regressors["LGBMRegressor"] = LGBMRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=-1, random_state=RANDOM_SEED
        )
        classifiers["LGBMClassifier"] = LGBMClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=-1, random_state=RANDOM_SEED
        )

    for name, model in regressors.items():
        try:
            model.fit(X_train, y_value_train)
            preds = pd.Series(model.predict(X_test), index=y_value_test.index)
            metrics = evaluate_value(y_value_test, preds)
            results_value.append(
                {"model": name, "metrics": metrics, "preds": preds, "model_obj": model}
            )
        except Exception:
            continue

    for name, model in classifiers.items():
        try:
            model.fit(X_train, y_dir_train)
            preds = pd.Series(model.predict(X_test), index=y_dir_test.index)
            metrics = evaluate_direction(y_dir_test, preds)
            results_direction.append(
                {"model": name, "metrics": metrics, "preds": preds, "model_obj": model}
            )
        except Exception:
            continue

    return {"value": results_value, "direction": results_direction}


# ============================================================================
# 模块3: 影响因素重要性分析
# ============================================================================

def analyze_feature_importance_multi_model(X_train, y_train, y_dir_train):
    """
    使用多种模型计算特征重要性
    """
    if not HAS_SKLEARN:
        print("警告: sklearn 未安装,跳过特征重要性分析")
        return None

    print("  → 分析特征重要性(多模型)...")
    importance_dict = {}

    # 1. RandomForest重要性
    try:
        rf = RandomForestRegressor(n_estimators=100, random_state=RANDOM_SEED, n_jobs=-1)
        rf.fit(X_train, y_train)
        importance_dict['RandomForest'] = pd.Series(rf.feature_importances_, index=X_train.columns)
        print("  → RandomForest重要性完成")
    except Exception:
        pass

    # 2. XGBoost重要性
    if HAS_XGBOOST:
        try:
            xgb = XGBRegressor(n_estimators=100, random_state=RANDOM_SEED)
            xgb.fit(X_train, y_train)
            importance_dict['XGBoost'] = pd.Series(xgb.feature_importances_, index=X_train.columns)
            print("  → XGBoost重要性完成")
        except Exception:
            pass

    # 3. LightGBM重要性
    if HAS_LIGHTGBM:
        try:
            lgbm = LGBMRegressor(n_estimators=100, random_state=RANDOM_SEED, verbose=-1)
            lgbm.fit(X_train, y_train)
            importance_dict['LightGBM'] = pd.Series(lgbm.feature_importances_, index=X_train.columns)
            print("  → LightGBM重要性完成")
        except Exception:
            pass

    # 4. Permutation Importance
    try:
        rf_base = RandomForestRegressor(n_estimators=50, random_state=RANDOM_SEED, n_jobs=-1)
        rf_base.fit(X_train, y_train)
        perm_result = permutation_importance(rf_base, X_train, y_train, n_repeats=10, random_state=RANDOM_SEED)
        importance_dict['Permutation'] = pd.Series(perm_result.importances_mean, index=X_train.columns)
        print("  → Permutation重要性完成")
    except Exception:
        pass

    if not importance_dict:
        return None

    # 合并所有重要性
    importance_df = pd.DataFrame(importance_dict)

    # 标准化到[0,1]
    importance_df_norm = (importance_df - importance_df.min()) / (importance_df.max() - importance_df.min())

    # 聚合重要性(平均)
    aggregated_importance = importance_df_norm.mean(axis=1).sort_values(ascending=False)

    # 提取lag特征
    lag_features = [col for col in aggregated_importance.index if col.startswith('lag_')]
    top_lags = aggregated_importance[lag_features].head(10)

    result = {
        'importance_df': importance_df,
        'importance_df_norm': importance_df_norm,
        'aggregated_importance': aggregated_importance,
        'top_lags': top_lags
    }

    print(f"  → 特征重要性分析完成, Top滞后期: {', '.join([f'{k}' for k in top_lags.index[:5]])}")
    return result


def compute_lag_influence_matrix(returns, max_lag=MAX_LAG):
    """
    创建滞后期影响力矩阵
    """
    print("  → 构建滞后期影响力矩阵...")

    influence_data = {}

    # 计算ACF
    if HAS_STATSMODELS:
        acf_data = compute_acf_pacf(returns, max_lag=max_lag)
        influence_data['ACF'] = np.abs(acf_data['acf'][1:max_lag+1])
        influence_data['PACF'] = np.abs(acf_data['pacf'][1:max_lag+1])

    # Granger因果
    granger_results = compute_granger_causality(returns, max_lag=min(max_lag, 20))
    if granger_results is not None:
        granger_series = pd.Series(0.0, index=range(1, max_lag+1))
        for _, row in granger_results.iterrows():
            granger_series[row['lag']] = row['f_stat']
        influence_data['Granger_F'] = granger_series.values

    # 互信息
    mi_results = compute_mutual_information(returns, max_lag=max_lag)
    if mi_results is not None:
        mi_series = pd.Series(0.0, index=range(1, max_lag+1))
        for _, row in mi_results.iterrows():
            mi_series[row['lag']] = row['mutual_info']
        influence_data['MutualInfo'] = mi_series.values

    # 转移熵
    te_results = compute_transfer_entropy(returns, max_lag=max_lag)
    if te_results is not None:
        te_series = pd.Series(0.0, index=range(1, max_lag+1))
        for _, row in te_results.iterrows():
            te_series[row['lag']] = row['transfer_entropy']
        influence_data['TransferEntropy'] = te_series.values

    # 构建矩阵
    influence_matrix = pd.DataFrame(influence_data, index=range(1, max_lag+1))

    print(f"  → 影响力矩阵构建完成, 维度: {influence_matrix.shape}")
    return influence_matrix


def identify_max_influence_factors(influence_matrix, top_n=10):
    """
    识别最大影响因素
    """
    print(f"  → 识别Top {top_n}影响因素...")

    # 标准化每列到[0,1]
    influence_norm = (influence_matrix - influence_matrix.min()) / (influence_matrix.max() - influence_matrix.min() + 1e-10)

    # 加权聚合(可配置权重)
    weights = {
        'ACF': 0.15,
        'PACF': 0.15,
        'Granger_F': 0.30,
        'MutualInfo': 0.25,
        'TransferEntropy': 0.15
    }

    influence_score = pd.Series(0.0, index=influence_matrix.index)
    for col in influence_norm.columns:
        weight = weights.get(col, 1.0 / len(influence_norm.columns))
        influence_score += influence_norm[col] * weight

    # 排序
    influence_ranking = influence_score.sort_values(ascending=False)

    max_influence_lag = influence_ranking.index[0]
    max_influence_score = influence_ranking.iloc[0]

    result = {
        'max_influence_lag': max_influence_lag,
        'max_influence_score': max_influence_score,
        'influence_ranking': influence_ranking.head(top_n),
        'influence_score_full': influence_score
    }

    print(f"  → 最大影响滞后期: lag_{max_influence_lag}, 得分: {max_influence_score:.4f}")
    return result


def compute_partial_correlation_network(returns, max_lag=MAX_LAG, threshold=0.05):
    """
    构建偏相关网络
    """
    if not HAS_SCIPY:
        print("警告: scipy 未安装,跳过偏相关网络")
        return None

    print(f"  → 构建偏相关网络 (阈值: {threshold})...")

    # 创建滞后期数据框
    df = pd.DataFrame()
    for lag in range(1, min(max_lag + 1, 20)):
        df[f'lag_{lag}'] = returns.shift(lag)
    df = df.dropna()

    # 计算相关矩阵
    corr_matrix = df.corr()

    # 计算偏相关(简化版: 使用逆相关矩阵)
    try:
        precision_matrix = np.linalg.inv(corr_matrix.values)
        partial_corr = -precision_matrix / np.sqrt(np.outer(np.diag(precision_matrix), np.diag(precision_matrix)))
        np.fill_diagonal(partial_corr, 1.0)

        partial_corr_df = pd.DataFrame(partial_corr, index=corr_matrix.index, columns=corr_matrix.columns)

        # 应用阈值
        partial_corr_filtered = partial_corr_df.where(np.abs(partial_corr_df) > threshold, 0)

        print(f"  → 偏相关网络构建完成, 边数: {(np.abs(partial_corr_filtered.values) > threshold).sum() // 2}")
        return partial_corr_filtered
    except Exception as e:
        print(f"  → 偏相关网络构建失败: {e}")
        return None


# ============================================================================
# 模块4: 增强自回归模型
# ============================================================================

def fit_markov_switching_ar(returns, n_regimes=N_REGIMES, order=5, test_ratio=TEST_RATIO):
    """
    马尔可夫转换自回归模型
    """
    if not HAS_STATSMODELS:
        print("警告: statsmodels 未安装,跳过MarkovSwitching AR")
        return None

    print(f"  → 拟合Markov Switching AR({order})模型, {n_regimes}个状态...")

    split_idx = int(len(returns) * (1 - test_ratio))
    train = returns.iloc[:split_idx]
    test = returns.iloc[split_idx:]

    try:
        # 拟合模型
        model = MarkovAutoregression(train, k_regimes=n_regimes, order=order, switching_ar=True)
        result = model.fit()

        # 获取状态概率
        smoothed_probs = result.smoothed_marginal_probabilities

        # 预测
        forecast_result = result.forecast(steps=len(test))

        # 提取预测值
        if hasattr(forecast_result, 'forecasts'):
            preds = forecast_result.forecasts
        else:
            preds = forecast_result

        preds = pd.Series(preds[:, 0] if preds.ndim > 1 else preds, index=test.index[:len(preds)])

        metrics = evaluate_value(test.iloc[:len(preds)], preds)

        # 提取状态转换概率
        regime_transition = result.regime_transition

        return {
            'model': f'MarkovSwitchingAR({order},{n_regimes})',
            'metrics': metrics,
            'preds': preds,
            'regime_transition': regime_transition,
            'smoothed_probs': smoothed_probs,
            'model_obj': result
        }
    except Exception as e:
        print(f"  → Markov Switching AR拟合失败: {e}")
        return None


def fit_lstm_autoregression(returns, lookback=LSTM_LOOKBACK, test_ratio=TEST_RATIO):
    """
    LSTM神经网络自回归
    """
    if not HAS_TENSORFLOW:
        print("警告: TensorFlow 未安装,跳过LSTM模型")
        return None

    print(f"  → 拟合LSTM自回归模型 (lookback={lookback})...")

    # 准备数据
    def create_lstm_dataset(data, lookback):
        X, y = [], []
        for i in range(len(data) - lookback):
            X.append(data[i:i+lookback])
            y.append(data[i+lookback])
        return np.array(X), np.array(y)

    data_values = returns.values
    split_idx = int(len(data_values) * (1 - test_ratio))

    train_data = data_values[:split_idx]
    test_data = data_values[split_idx:]

    X_train, y_train = create_lstm_dataset(train_data, lookback)
    X_test, y_test = create_lstm_dataset(test_data, lookback)

    # 重塑为LSTM输入格式 [samples, timesteps, features]
    X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))
    X_test = X_test.reshape((X_test.shape[0], X_test.shape[1], 1))

    try:
        # 构建LSTM模型
        model = keras.Sequential([
            layers.LSTM(64, activation='tanh', input_shape=(lookback, 1), return_sequences=True),
            layers.Dropout(0.2),
            layers.LSTM(32, activation='tanh'),
            layers.Dropout(0.2),
            layers.Dense(1)
        ])

        model.compile(optimizer='adam', loss='mse', metrics=['mae'])

        # 训练(抑制输出)
        history = model.fit(
            X_train, y_train,
            epochs=LSTM_EPOCHS,
            batch_size=LSTM_BATCH_SIZE,
            validation_split=0.1,
            verbose=0
        )

        # 预测
        preds_array = model.predict(X_test, verbose=0).flatten()

        # 创建对应的时间索引
        test_index = returns.index[split_idx + lookback:split_idx + lookback + len(preds_array)]
        preds = pd.Series(preds_array, index=test_index)

        y_test_series = pd.Series(y_test, index=test_index)
        metrics = evaluate_value(y_test_series, preds)

        print(f"  → LSTM模型训练完成, 最终loss: {history.history['loss'][-1]:.6f}")
        return {
            'model': f'LSTM(lookback={lookback})',
            'metrics': metrics,
            'preds': preds,
            'history': history.history,
            'model_obj': model
        }
    except Exception as e:
        print(f"  → LSTM模型训练失败: {e}")
        return None


def fit_ensemble_autoregression(X_train, X_test, y_train, y_test):
    """
    集成多种自回归模型
    """
    if not HAS_SKLEARN:
        print("警告: sklearn 未安装,跳过集成模型")
        return None

    print("  → 拟合集成自回归模型...")

    base_models = []

    # RandomForest
    try:
        rf = RandomForestRegressor(n_estimators=100, random_state=RANDOM_SEED, n_jobs=-1)
        rf.fit(X_train, y_train)
        base_models.append(('RandomForest', rf))
    except Exception:
        pass

    # XGBoost
    if HAS_XGBOOST:
        try:
            xgb = XGBRegressor(n_estimators=100, random_state=RANDOM_SEED)
            xgb.fit(X_train, y_train)
            base_models.append(('XGBoost', xgb))
        except Exception:
            pass

    # LightGBM
    if HAS_LIGHTGBM:
        try:
            lgbm = LGBMRegressor(n_estimators=100, random_state=RANDOM_SEED, verbose=-1)
            lgbm.fit(X_train, y_train)
            base_models.append(('LightGBM', lgbm))
        except Exception:
            pass

    if len(base_models) < 2:
        print("  → 集成模型需要至少2个基学习器,跳过")
        return None

    # 生成元特征
    meta_features_train = np.column_stack([model.predict(X_train) for _, model in base_models])
    meta_features_test = np.column_stack([model.predict(X_test) for _, model in base_models])

    # 元学习器: Ridge
    meta_learner = Ridge(alpha=1.0)
    meta_learner.fit(meta_features_train, y_train)

    # 预测
    preds_array = meta_learner.predict(meta_features_test)
    preds = pd.Series(preds_array, index=y_test.index)

    metrics = evaluate_value(y_test, preds)

    # 计算基学习器权重
    weights = pd.Series(meta_learner.coef_, index=[name for name, _ in base_models])

    print(f"  → 集成模型完成, 使用{len(base_models)}个基学习器")
    return {
        'model': 'EnsembleStacking',
        'metrics': metrics,
        'preds': preds,
        'base_models': [name for name, _ in base_models],
        'weights': weights
    }


def select_best_model(results, metric, higher_is_better=True):
    if not results:
        return None
    sorted_results = sorted(
        results,
        key=lambda x: x["metrics"].get(metric, -np.inf if higher_is_better else np.inf),
        reverse=higher_is_better,
    )
    return sorted_results[0]


def summarize_results(title, results, metric_keys):
    if not results:
        print(f"{title}: 无可用结果")
        return
    df = []
    for item in results:
        row = {"Model": item["model"]}
        for key in metric_keys:
            row[key] = item["metrics"].get(key, np.nan)
        df.append(row)
    df = pd.DataFrame(df)
    print(f"\n{title}")
    print(df.sort_values(metric_keys[0], ascending=False).head(10))


def plot_acf_pacf(acf_data, sign_acf_data, max_lag=MAX_LAG):
    lags = np.arange(max_lag + 1)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(lags, acf_data["acf"], color="steelblue")
    axes[0].axhline(0, color="black", linewidth=0.5)
    axes[0].axhline(acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    axes[0].axhline(-acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    axes[0].set_title("ACF (Returns)")
    axes[0].set_xlabel("Lag")
    axes[0].set_ylabel("ACF")

    axes[1].bar(lags, acf_data["pacf"], color="darkorange")
    axes[1].axhline(0, color="black", linewidth=0.5)
    axes[1].axhline(acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    axes[1].axhline(-acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    axes[1].set_title("PACF (Returns)")
    axes[1].set_xlabel("Lag")
    axes[1].set_ylabel("PACF")
    plt.tight_layout()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(lags, sign_acf_data["acf"], color="purple", alpha=0.7)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.axhline(sign_acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    ax.axhline(-sign_acf_data["conf_interval"], color="red", linestyle="--", linewidth=1)
    ax.set_title("Sign ACF (Direction)")
    ax.set_xlabel("Lag")
    ax.set_ylabel("ACF")
    plt.tight_layout()


def plot_model_comparison(results, metric, title):
    if not results:
        return
    results_sorted = sorted(results, key=lambda x: x["metrics"].get(metric, np.nan))
    names = [r["model"] for r in results_sorted]
    values = [r["metrics"].get(metric, np.nan) for r in results_sorted]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(names, values, color="teal")
    ax.set_title(title)
    ax.set_xlabel(metric)
    plt.tight_layout()


def plot_prediction(y_true, y_pred, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(y_true.index, y_true.values, label="Actual", linewidth=1)
    ax.plot(y_pred.index, y_pred.values, label="Predicted", linewidth=1)
    ax.set_title(title)
    ax.legend()
    plt.tight_layout()
    return fig


# ============================================================================
# 模块5: 可视化增强
# ============================================================================

def plot_influence_heatmap(influence_matrix, title="滞后期影响力热图"):
    """
    绘制滞后期影响力热图
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    # 标准化以便可视化
    influence_norm = (influence_matrix - influence_matrix.min()) / (influence_matrix.max() - influence_matrix.min() + 1e-10)

    sns.heatmap(influence_norm.T, cmap='YlOrRd', annot=False, cbar=True, ax=ax)
    ax.set_title(title, fontsize=14)
    ax.set_xlabel('滞后期 (Lag)', fontsize=12)
    ax.set_ylabel('度量方法', fontsize=12)

    plt.tight_layout()
    return fig


def plot_asymmetric_acf_comparison(pos_acf, neg_acf, conf_interval_pos, conf_interval_neg, max_lag=None):
    """
    正负收益率ACF对比图
    """
    if max_lag is None:
        max_lag = min(len(pos_acf), len(neg_acf)) - 1

    lags = np.arange(max_lag + 1)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 正收益率ACF
    axes[0].bar(lags, pos_acf[:max_lag+1], color='green', alpha=0.7)
    axes[0].axhline(0, color='black', linewidth=0.5)
    axes[0].axhline(conf_interval_pos, color='red', linestyle='--', linewidth=1)
    axes[0].axhline(-conf_interval_pos, color='red', linestyle='--', linewidth=1)
    axes[0].set_title('正收益率 ACF', fontsize=12)
    axes[0].set_xlabel('Lag')
    axes[0].set_ylabel('ACF')

    # 负收益率ACF
    axes[1].bar(lags, neg_acf[:max_lag+1], color='red', alpha=0.7)
    axes[1].axhline(0, color='black', linewidth=0.5)
    axes[1].axhline(conf_interval_neg, color='red', linestyle='--', linewidth=1)
    axes[1].axhline(-conf_interval_neg, color='red', linestyle='--', linewidth=1)
    axes[1].set_title('负收益率 ACF', fontsize=12)
    axes[1].set_xlabel('Lag')
    axes[1].set_ylabel('ACF')

    plt.tight_layout()
    return fig


def plot_transition_network(transition_prob, threshold=0.1):
    """
    状态转换网络图
    """
    if not HAS_NETWORKX:
        print("警告: networkx 未安装,跳过转换网络图")
        return None

    fig, ax = plt.subplots(figsize=(10, 8))

    # 创建有向图
    G = nx.DiGraph()

    # 添加节点
    states = transition_prob.index.tolist()
    G.add_nodes_from(states)

    # 添加边(只保留概率>threshold的)
    for i, state_from in enumerate(states):
        for j, state_to in enumerate(states):
            prob = transition_prob.iloc[i, j]
            if prob > threshold:
                G.add_edge(state_from, state_to, weight=prob)

    # 绘图
    pos = nx.spring_layout(G, k=2, iterations=50)

    # 绘制节点
    nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=2000, ax=ax)

    # 绘制标签
    nx.draw_networkx_labels(G, pos, font_size=10, ax=ax)

    # 绘制边,粗细代表概率
    edges = G.edges()
    weights = [G[u][v]['weight'] for u, v in edges]
    nx.draw_networkx_edges(G, pos, width=[w*5 for w in weights], arrows=True,
                           arrowsize=20, edge_color=weights, edge_cmap=plt.cm.Blues, ax=ax)

    ax.set_title(f'状态转换网络 (阈值>{threshold})', fontsize=14)
    ax.axis('off')

    plt.tight_layout()
    return fig


def plot_feature_importance_comparison(importance_df, top_n=20):
    """
    多模型特征重要性对比
    """
    fig, ax = plt.subplots(figsize=(12, 8))

    # 选择top_n特征
    importance_df_sorted = importance_df.mean(axis=1).sort_values(ascending=False).head(top_n)
    top_features = importance_df_sorted.index

    # 绘制堆叠柱状图
    importance_df.loc[top_features].plot(kind='bar', ax=ax, width=0.8)

    ax.set_title(f'Top {top_n} 特征重要性对比', fontsize=14)
    ax.set_xlabel('特征', fontsize=12)
    ax.set_ylabel('重要性', fontsize=12)
    ax.legend(title='模型', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(axis='y', alpha=0.3)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig


def plot_quantile_ar_coefficients(quantile_results):
    """
    分位数自回归系数图
    """
    if quantile_results is None:
        return None

    quantiles = sorted([float(k.replace('q', '')) for k in quantile_results.keys()])
    coefs = [quantile_results[f'q{q}']['coef'] for q in quantiles]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(quantiles, coefs, marker='o', linewidth=2, markersize=8)
    ax.axhline(0, color='red', linestyle='--', linewidth=1)
    ax.set_title('分位数自回归系数', fontsize=14)
    ax.set_xlabel('分位数', fontsize=12)
    ax.set_ylabel('AR(1)系数', fontsize=12)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def plot_directional_persistence(persistence_df, top_n=30):
    """
    方向持续性图表
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    lags = persistence_df['lag'].values[:top_n]

    # P(+|+)
    axes[0, 0].bar(lags, persistence_df['p_pos_given_pos'].values[:top_n], color='green', alpha=0.7)
    axes[0, 0].axhline(0.5, color='red', linestyle='--', label='随机水平')
    axes[0, 0].set_title('上涨后继续上涨概率 P(+|+)')
    axes[0, 0].set_xlabel('Lag')
    axes[0, 0].set_ylabel('概率')
    axes[0, 0].legend()
    axes[0, 0].grid(axis='y', alpha=0.3)

    # P(-|-)
    axes[0, 1].bar(lags, persistence_df['p_neg_given_neg'].values[:top_n], color='red', alpha=0.7)
    axes[0, 1].axhline(0.5, color='red', linestyle='--', label='随机水平')
    axes[0, 1].set_title('下跌后继续下跌概率 P(-|-)')
    axes[0, 1].set_xlabel('Lag')
    axes[0, 1].set_ylabel('概率')
    axes[0, 1].legend()
    axes[0, 1].grid(axis='y', alpha=0.3)

    # P(+|-)
    axes[1, 0].bar(lags, persistence_df['p_pos_given_neg'].values[:top_n], color='orange', alpha=0.7)
    axes[1, 0].axhline(0.5, color='red', linestyle='--', label='随机水平')
    axes[1, 0].set_title('下跌后反转上涨概率 P(+|-)')
    axes[1, 0].set_xlabel('Lag')
    axes[1, 0].set_ylabel('概率')
    axes[1, 0].legend()
    axes[1, 0].grid(axis='y', alpha=0.3)

    # P(-|+)
    axes[1, 1].bar(lags, persistence_df['p_neg_given_pos'].values[:top_n], color='purple', alpha=0.7)
    axes[1, 1].axhline(0.5, color='red', linestyle='--', label='随机水平')
    axes[1, 1].set_title('上涨后反转下跌概率 P(-|+)')
    axes[1, 1].set_xlabel('Lag')
    axes[1, 1].set_ylabel('概率')
    axes[1, 1].legend()
    axes[1, 1].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    return fig


# ============================================================================
# 模块6: 输出格式化
# ============================================================================

def create_output_directory(base_dir="btc_analysis_results"):
    """
    创建输出目录结构
    """
    base_path = Path(base_dir)
    figures_path = base_path / "figures"

    base_path.mkdir(exist_ok=True)
    figures_path.mkdir(exist_ok=True)

    print(f"✓ 输出目录创建: {base_path}")
    return {
        'base': str(base_path),
        'figures': str(figures_path)
    }


def save_to_csv(data, filename, output_dir):
    """
    保存数据到CSV
    """
    output_path = Path(output_dir) / filename

    if isinstance(data, pd.DataFrame):
        data.to_csv(output_path)
    elif isinstance(data, pd.Series):
        data.to_csv(output_path, header=True)
    elif isinstance(data, dict):
        pd.DataFrame([data]).to_csv(output_path, index=False)
    else:
        print(f"警告: 无法保存{filename},不支持的数据类型")
        return

    print(f"  ✓ 已保存: {filename}")


def save_all_figures(figures_dict, output_dir):
    """
    批量保存所有matplotlib图表
    """
    output_path = Path(output_dir)
    saved_count = 0

    for name, fig in figures_dict.items():
        if fig is not None:
            try:
                fig_path = output_path / f"{name}.png"
                fig.savefig(fig_path, dpi=300, bbox_inches='tight')
                saved_count += 1
            except Exception as e:
                print(f"  警告: 保存图表{name}失败: {e}")

    print(f"  ✓ 已保存{saved_count}个图表")


def generate_json_report(all_results, output_dir):
    """
    生成完整JSON报告
    """
    output_path = Path(output_dir) / "summary.json"

    # 转换不可序列化的对象
    def convert_to_serializable(obj):
        if isinstance(obj, (pd.DataFrame, pd.Series)):
            # 转换为列表格式,避免复杂的索引问题
            if isinstance(obj, pd.Series):
                return {str(k): convert_to_serializable(v) for k, v in obj.items()}
            else:
                return obj.to_dict(orient='records')
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (pd.Timestamp, pd.DatetimeIndex)):
            return str(obj)
        elif isinstance(obj, dict):
            # 确保字典的键也是可序列化的
            result = {}
            for k, v in obj.items():
                # 跳过一些已知会导致问题的键
                if k in ['states', 'model_obj', 'history', 'smoothed_probs', 'regime_transition']:
                    continue
                key_str = str(k) if not isinstance(k, (str, int, float, bool, type(None))) else k
                result[key_str] = convert_to_serializable(v)
            return result
        elif isinstance(obj, list):
            return [convert_to_serializable(item) for item in obj]
        elif obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        else:
            # 跳过无法序列化的对象
            return None

    try:
        serializable_results = convert_to_serializable(all_results)

        # 添加时间戳
        serializable_results['timestamp'] = datetime.now().isoformat()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)

        print(f"  ✓ 已保存JSON报告: summary.json")
    except Exception as e:
        print(f"  警告: JSON报告生成失败: {e}")
        print(f"  提示: 详细结果已保存在CSV文件和Markdown报告中")


def generate_markdown_report(all_results, output_dir):
    """
    生成Markdown分析报告
    """
    output_path = Path(output_dir) / "report.md"

    lines = []
    lines.append("# BTC自相关分析报告\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n\n")

    # 1. 执行摘要
    lines.append("## 1. 执行摘要\n\n")
    if 'data_info' in all_results:
        info = all_results['data_info']
        lines.append(f"- **数据集**: {info.get('ticker', 'N/A')}\n")
        lines.append(f"- **时间周期**: {info.get('period', 'N/A')}, 间隔: {info.get('interval', 'N/A')}\n")
        lines.append(f"- **观测数量**: {info.get('n_observations', 'N/A')}\n\n")

    # 2. 影响因素分析
    lines.append("## 2. 影响因素分析\n\n")
    if 'importance_analysis' in all_results and all_results['importance_analysis']:
        max_factors = all_results['importance_analysis'].get('max_factors')
        if max_factors:
            lines.append(f"**最大影响滞后期**: lag_{max_factors['max_influence_lag']}\n\n")
            lines.append(f"**影响力得分**: {max_factors['max_influence_score']:.4f}\n\n")

            if 'influence_ranking' in max_factors:
                lines.append("**Top 10 影响因素**:\n\n")
                ranking = max_factors['influence_ranking']
                for i, (lag, score) in enumerate(ranking.items(), 1):
                    lines.append(f"{i}. lag_{lag}: {score:.4f}\n")
                lines.append("\n")

    # 3. 正负收益率不对称性
    lines.append("## 3. 正负收益率不对称性\n\n")
    if 'asymmetric_analysis' in all_results and all_results['asymmetric_analysis']:
        asym = all_results['asymmetric_analysis'].get('asymmetric_acf')
        if asym:
            lines.append(f"**不对称指数**: {asym.get('asymmetry_index', 'N/A'):.4f}\n\n")
            lines.append(f"- 正收益率样本数: {asym.get('n_pos', 'N/A')}\n")
            lines.append(f"- 负收益率样本数: {asym.get('n_neg', 'N/A')}\n\n")

            if asym.get('asymmetry_index', 0) > 0:
                lines.append("**结论**: 负收益率表现出更强的持续性\n\n")
            else:
                lines.append("**结论**: 正收益率表现出更强的持续性\n\n")

    # 4. 模型性能对比
    lines.append("## 4. 模型性能对比\n\n")
    lines.append("请参阅 `figures/` 目录中的可视化图表\n\n")

    # 5. 附录
    lines.append("## 5. 附录\n\n")
    lines.append("详细数值结果请参阅:\n")
    lines.append("- `summary.json`: 完整结构化数据\n")
    lines.append("- `*.csv`: 各类分析结果表格\n")
    lines.append("- `figures/*.png`: 可视化图表\n")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"  ✓ 已保存Markdown报告: report.md")


def print_summary_to_console(all_results):
    """
    打印关键发现到控制台
    """
    print("\n" + "=" * 80)
    print("关键发现摘要")
    print("=" * 80)

    # 影响因素
    if 'importance_analysis' in all_results and all_results['importance_analysis']:
        max_factors = all_results['importance_analysis'].get('max_factors')
        if max_factors:
            print(f"\n【最大影响因素】")
            print(f"  滞后期: lag_{max_factors['max_influence_lag']}")
            print(f"  影响力得分: {max_factors['max_influence_score']:.4f}")

    # 不对称性
    if 'asymmetric_analysis' in all_results and all_results['asymmetric_analysis']:
        asym = all_results['asymmetric_analysis'].get('asymmetric_acf')
        if asym:
            print(f"\n【收益率不对称性】")
            print(f"  不对称指数: {asym.get('asymmetry_index', 'N/A'):.4f}")
            if asym.get('asymmetry_index', 0) > 0:
                print("  → 负收益率持续性更强")
            else:
                print("  → 正收益率持续性更强")

    print("\n" + "=" * 80)


def find_streak_thresholds(returns, min_n=STREAK_MIN_N, max_n=STREAK_MAX_N,
                           thresholds=STREAK_THRESHOLDS, min_samples=STREAK_MIN_SAMPLES):
    if isinstance(returns, pd.DataFrame):
        returns = returns.iloc[:, 0]
    returns = returns.dropna()
    directions = np.sign(returns)
    results = {"up": [], "down": [], "up_reversal": [], "down_reversal": []}

    for n in range(min_n, max_n + 1):
        for threshold in thresholds:
            for direction in (1, -1):
                hits = 0
                same_next = 0
                for idx in range(n, len(returns) - 1):
                    window_dirs = directions.iloc[idx - n:idx]
                    if (window_dirs == direction).all():
                        cum_return = returns.iloc[idx - n:idx].sum()
                        if direction == 1 and cum_return >= threshold:
                            hits += 1
                            same_next += int(directions.iloc[idx] == direction)
                        if direction == -1 and cum_return <= -threshold:
                            hits += 1
                            same_next += int(directions.iloc[idx] == direction)
                if hits >= min_samples:
                    prob = same_next / hits if hits > 0 else np.nan
                    row = {
                        "N": n,
                        "threshold": float(threshold),
                        "samples": hits,
                        "prob_same_direction": prob,
                    }
                    if direction == 1:
                        results["up"].append(row)
                        results["up_reversal"].append(
                            {
                                **row,
                                "prob_reverse_direction": 1 - row["prob_same_direction"],
                            }
                        )
                    else:
                        results["down"].append(row)
                        results["down_reversal"].append(
                            {
                                **row,
                                "prob_reverse_direction": 1 - row["prob_same_direction"],
                            }
                        )

    def pick_best(rows):
        if not rows:
            return None
        rows_sorted = sorted(
            rows,
            key=lambda x: (x["prob_same_direction"], x["samples"]),
            reverse=True,
        )
        return rows_sorted[0]

    def is_significant_above_half(prob, samples):
        if samples <= 0 or np.isnan(prob):
            return False
        se = np.sqrt(0.5 * 0.5 / samples)
        return prob - 0.5 >= STREAK_SIGNIFICANCE_Z * se

    def pick_best_reverse(rows):
        if not rows:
            return None
        rows = [
            row for row in rows
            if is_significant_above_half(row["prob_reverse_direction"], row["samples"])
        ]
        if not rows:
            return None
        rows_sorted = sorted(
            rows,
            key=lambda x: (x["prob_reverse_direction"], x["samples"]),
            reverse=True,
        )
        return rows_sorted[0]

    return (
        results,
        pick_best(results["up"]),
        pick_best(results["down"]),
        pick_best_reverse(results["up_reversal"]),
        pick_best_reverse(results["down_reversal"]),
    )


def main():
    """
    主函数 - 集成所有分析模块
    """
    warnings.filterwarnings("ignore")

    print("=" * 80)
    print("BTC自相关分析系统")
    print("=" * 80)

    # 0. 创建输出目录
    output_paths = create_output_directory()

    # 1. 加载数据
    print("\n[1/13] 加载数据...")
    returns = load_returns()
    print(f"  ✓ 加载{len(returns)}个观测值")

    # 2. 基础统计
    print("\n[2/13] 基础统计分析...")
    acf_data = None
    sign_acf_data = None
    if HAS_STATSMODELS:
        acf_data = compute_acf_pacf(returns)
        sign_acf_data = compute_sign_acf(returns)
        print(f"  ✓ ACF最大滞后: lag_{acf_data['max_acf_lag']}, PACF最大滞后: lag_{acf_data['max_pacf_lag']}")

    # 3. 高级统计分析
    print("\n[3/13] 高级统计分析...")
    arch_result = compute_conditional_heteroskedasticity(returns)

    # 4. 收益率正负分离分析
    print("\n[4/13] 收益率正负分离分析...")
    asymmetric_acf = compute_asymmetric_acf(returns, max_lag=50)
    transition_matrix = compute_transition_matrix(returns)
    quantile_ar = compute_quantile_autoregression(returns)
    directional_persist = compute_directional_persistence(returns, max_lag=50)

    # 5. 特征构建
    print("\n[5/13] 构建特征...")
    X, y_value, y_dir = make_feature_frame(returns)
    X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test = train_test_split_series(
        X, y_value, y_dir
    )
    print(f"  ✓ 特征数量: {X.shape[1]}, 训练集: {len(X_train)}, 测试集: {len(X_test)}")

    # 6. 影响因素重要性分析
    print("\n[6/13] 影响因素重要性分析...")
    importance_results = analyze_feature_importance_multi_model(X_train, y_value_train, y_dir_train)
    influence_matrix = compute_lag_influence_matrix(returns, max_lag=50)
    max_factors = identify_max_influence_factors(influence_matrix, top_n=10)

    # 7. 传统时间序列模型
    print("\n[7/13] 拟合传统时间序列模型...")
    linear_results = []
    arma_results = []
    arima_results = []
    if HAS_STATSMODELS:
        linear_results = fit_ar_models(returns)
        arma_results = fit_arma_models(returns)
        arima_results = fit_arima_models(returns)
        print(f"  ✓ AR模型: {len(linear_results)}, ARMA模型: {len(arma_results)}, ARIMA模型: {len(arima_results)}")

    tar_result = fit_threshold_ar(returns)
    star_result = fit_star_model(returns)
    garch_result = fit_garch_model(returns)

    # 8. 增强自回归模型
    print("\n[8/13] 拟合增强自回归模型...")
    ms_ar_result = fit_markov_switching_ar(returns)
    lstm_result = fit_lstm_autoregression(returns)
    ensemble_result = fit_ensemble_autoregression(X_train, X_test, y_value_train, y_value_test)

    # 9. 机器学习模型
    print("\n[9/13] 拟合机器学习模型...")
    ml_results = fit_ml_models(X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test)
    ml_value_results = ml_results["value"]
    ml_direction_results = ml_results["direction"]
    print(f"  ✓ 价值预测模型: {len(ml_value_results)}, 方向预测模型: {len(ml_direction_results)}")

    # 10. 汇总所有模型结果
    print("\n[10/13] 汇总模型结果...")
    nonlinear_results = [r for r in [tar_result, star_result] if r is not None]
    enhanced_results = [r for r in [ms_ar_result, lstm_result, ensemble_result] if r is not None]

    all_value_results = linear_results + arma_results + arima_results + nonlinear_results + enhanced_results + ml_value_results

    all_direction_results = []
    for item in all_value_results:
        if "preds" in item:
            preds_dir = (item["preds"] > 0).astype(int)
            common_index = y_dir_test.index.intersection(preds_dir.index)
            if not common_index.empty:
                metrics = evaluate_direction(
                    y_dir_test.loc[common_index], preds_dir.loc[common_index]
                )
                all_direction_results.append(
                    {"model": item["model"] + " (from value)", "metrics": metrics}
                )
    all_direction_results += ml_direction_results

    # 选择最优模型
    best_value_model = select_best_model(all_value_results, "rmse", higher_is_better=False)
    best_dir_model = select_best_model(all_direction_results, "f1", higher_is_better=True)

    print(f"  ✓ 总共{len(all_value_results)}个价值模型, {len(all_direction_results)}个方向模型")
    if best_value_model:
        print(f"  ✓ 最优价值模型: {best_value_model['model']}, RMSE={best_value_model['metrics']['rmse']:.6f}")
    if best_dir_model:
        print(f"  ✓ 最优方向模型: {best_dir_model['model']}, F1={best_dir_model['metrics']['f1']:.4f}")

    # 11. 汇总所有分析结果
    all_results = {
        'data_info': {
            'ticker': 'BTC-USD',
            'period': '10y',
            'interval': '1wk',
            'n_observations': len(returns),
        },
        'basic_stats': {
            'acf': acf_data,
            'sign_acf': sign_acf_data,
        },
        'advanced_stats': {
            'arch': arch_result,
        },
        'asymmetric_analysis': {
            'asymmetric_acf': asymmetric_acf,
            'transition_matrix': transition_matrix,
            'quantile_ar': quantile_ar,
            'directional_persistence': directional_persist,
        },
        'importance_analysis': {
            'feature_importance': importance_results,
            'influence_matrix': influence_matrix,
            'max_factors': max_factors,
        },
        'models': {
            'linear': linear_results,
            'arma': arma_results,
            'arima': arima_results,
            'tar': tar_result,
            'star': star_result,
            'garch': garch_result,
            'markov_switching': ms_ar_result,
            'lstm': lstm_result,
            'ensemble': ensemble_result,
            'ml': ml_results,
        },
        'best_models': {
            'value': best_value_model,
            'direction': best_dir_model,
        }
    }

    # 12. 生成可视化
    print("\n[11/13] 生成可视化图表...")
    figures = {}

    if acf_data and sign_acf_data:
        figures['01_acf_pacf'] = plot_acf_pacf(acf_data, sign_acf_data)

    if asymmetric_acf:
        figures['02_asymmetric_acf'] = plot_asymmetric_acf_comparison(
            asymmetric_acf['pos_acf'],
            asymmetric_acf['neg_acf'],
            asymmetric_acf['conf_interval_pos'],
            asymmetric_acf['conf_interval_neg'],
            max_lag=50
        )

    if influence_matrix is not None and not influence_matrix.empty:
        figures['03_influence_heatmap'] = plot_influence_heatmap(influence_matrix)

    if importance_results and importance_results['importance_df'] is not None:
        figures['04_feature_importance'] = plot_feature_importance_comparison(importance_results['importance_df'])

    if transition_matrix and transition_matrix['transition_prob'] is not None:
        figures['05_transition_network'] = plot_transition_network(transition_matrix['transition_prob'])

    if quantile_ar:
        figures['06_quantile_ar'] = plot_quantile_ar_coefficients(quantile_ar)

    if directional_persist is not None:
        figures['07_directional_persistence'] = plot_directional_persistence(directional_persist)

    if all_value_results:
        figures['08_model_comparison_rmse'] = plot_model_comparison(all_value_results, "rmse", "模型对比 (RMSE)")

    if all_direction_results:
        figures['09_model_comparison_f1'] = plot_model_comparison(all_direction_results, "f1", "模型对比 (F1)")

    if best_value_model and "preds" in best_value_model:
        pred_index = best_value_model["preds"].index
        common_index = y_value_test.index.intersection(pred_index)
        if not common_index.empty:
            figures['10_best_value_prediction'] = plot_prediction(
                y_value_test.loc[common_index],
                best_value_model["preds"].loc[common_index],
                f"最优价值模型: {best_value_model['model']}",
            )

    print(f"  ✓ 生成{len(figures)}个图表")

    # 13. 保存所有输出
    print("\n[12/13] 保存分析结果...")

    # 保存CSV文件
    if max_factors and 'influence_ranking' in max_factors:
        save_to_csv(max_factors['influence_ranking'], 'influence_factors.csv', output_paths['base'])

    if importance_results and 'importance_df' in importance_results:
        save_to_csv(importance_results['importance_df'], 'feature_importance.csv', output_paths['base'])

    if transition_matrix and 'transition_prob' in transition_matrix:
        save_to_csv(transition_matrix['transition_prob'], 'transition_matrix.csv', output_paths['base'])

    if directional_persist is not None:
        save_to_csv(directional_persist, 'directional_persistence.csv', output_paths['base'])

    # 保存图表
    save_all_figures(figures, output_paths['figures'])

    # 生成JSON报告
    generate_json_report(all_results, output_paths['base'])

    # 生成Markdown报告
    generate_markdown_report(all_results, output_paths['base'])

    # 14. 控制台输出关键发现
    print("\n[13/13] 生成摘要...")
    summarize_results("数值预测模型结果 (按RMSE排序)", all_value_results, ["rmse", "mae", "r2", "direction_acc"])
    summarize_results("方向预测模型结果 (按F1排序)", all_direction_results, ["f1", "accuracy", "precision", "recall"])

    print_summary_to_console(all_results)

    print("\n" + "=" * 80)
    print("分析完成!")
    print("=" * 80)
    print(f"\n所有结果已保存到: {output_paths['base']}")
    print(f"  - Markdown报告: report.md")
    print(f"  - JSON数据: summary.json")
    print(f"  - CSV文件: *.csv")
    print(f"  - 图表: figures/*.png")

    plt.show()


if __name__ == "__main__":
    main()
