import warnings

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

HAS_STATSMODELS = True
try:
    from statsmodels.tsa.stattools import acf, pacf
    from statsmodels.tsa.ar_model import AutoReg
    from statsmodels.tsa.arima.model import ARIMA
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
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import Pipeline
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
except Exception:
    HAS_SCIPY = False


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
    warnings.filterwarnings("ignore")
    returns = load_returns()

    if HAS_STATSMODELS:
        acf_data = compute_acf_pacf(returns)
        sign_acf_data = compute_sign_acf(returns)
        print("=" * 80)
        print("最大绝对值 ACF 滞后期:")
        print(f"数值 ACF: lag={acf_data['max_acf_lag']} value={acf_data['acf'][acf_data['max_acf_lag']]:.4f}")
        print(f"数值 PACF: lag={acf_data['max_pacf_lag']} value={acf_data['pacf'][acf_data['max_pacf_lag']]:.4f}")
        print(f"符号 ACF: lag={sign_acf_data['max_acf_lag']} value={sign_acf_data['acf'][sign_acf_data['max_acf_lag']]:.4f}")
        print("=" * 80)
        plot_acf_pacf(acf_data, sign_acf_data)
    else:
        print("statsmodels 未安装，跳过 ACF/PACF 分析")

    X, y_value, y_dir = make_feature_frame(returns)
    X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test = train_test_split_series(
        X, y_value, y_dir
    )

    linear_results = []
    arma_results = []
    arima_results = []
    if HAS_STATSMODELS:
        print("开始拟合线性模型...")
        linear_results = fit_ar_models(returns)
        arma_results = fit_arma_models(returns)
        arima_results = fit_arima_models(returns)

    tar_result = fit_threshold_ar(returns)
    star_result = fit_star_model(returns)
    garch_result = fit_garch_model(returns)

    nonlinear_results = [r for r in [tar_result, star_result] if r is not None]

    ml_results = fit_ml_models(X_train, X_test, y_value_train, y_value_test, y_dir_train, y_dir_test)
    ml_value_results = ml_results["value"]
    ml_direction_results = ml_results["direction"]

    all_value_results = linear_results + arma_results + arima_results + nonlinear_results + ml_value_results
    all_direction_results = []
    for item in all_value_results:
        if "preds" in item:
            preds_dir = (item["preds"] > 0).astype(int)
            common_index = y_dir_test.index.intersection(preds_dir.index)
            if common_index.empty:
                continue
            metrics = evaluate_direction(
                y_dir_test.loc[common_index], preds_dir.loc[common_index]
            )
            all_direction_results.append(
                {"model": item["model"] + " (from value)", "metrics": metrics}
            )
    all_direction_results += ml_direction_results

    summarize_results("数值预测模型结果 (按RMSE排序)", all_value_results, ["rmse", "mae", "r2", "direction_acc"])
    summarize_results("方向预测模型结果 (按F1排序)", all_direction_results, ["f1", "accuracy", "precision", "recall"])

    best_value_model = select_best_model(all_value_results, "rmse", higher_is_better=False)
    best_dir_model = select_best_model(all_direction_results, "f1", higher_is_better=True)

    if best_value_model:
        print("\n最优数值预测模型:")
        print(best_value_model["model"])
        print(best_value_model["metrics"])
        pred_index = best_value_model["preds"].index
        common_index = y_value_test.index.intersection(pred_index)
        if not common_index.empty:
            plot_prediction(
                y_value_test.loc[common_index],
                best_value_model["preds"].loc[common_index],
                "Best Value Model",
            )

    if best_dir_model:
        print("\n最优方向预测模型:")
        print(best_dir_model["model"])
        print(best_dir_model["metrics"])

    if garch_result:
        print("\nGARCH(1,1) 模型结果（波动率建模）:")
        print(garch_result["metrics"])

    plot_model_comparison(all_value_results, "rmse", "模型对比（RMSE）")
    plot_model_comparison(all_direction_results, "f1", "模型对比（F1）")

    (
        streak_results,
        best_up,
        best_down,
        best_up_reversal,
        best_down_reversal,
    ) = find_streak_thresholds(returns)
    print("\n连续上涨/下跌N周 + 阈值X后的方向概率（>= 最小样本数）")
    if best_up:
        print(f"最佳上涨组合: N={best_up['N']}, X>={best_up['threshold']}, "
              f"samples={best_up['samples']}, P(继续上涨)={best_up['prob_same_direction']:.2%}")
    else:
        print("上涨组合: 未找到满足样本数阈值的组合")
    if best_down:
        print(f"最佳下跌组合: N={best_down['N']}, X>={best_down['threshold']}, "
              f"samples={best_down['samples']}, P(继续下跌)={best_down['prob_same_direction']:.2%}")
    else:
        print("下跌组合: 未找到满足样本数阈值的组合")

    print("\n信号反转关系（连续单边趋势后出现反转）")
    if best_up_reversal:
        print(f"上涨后反转: N={best_up_reversal['N']}, X>={best_up_reversal['threshold']}, "
              f"samples={best_up_reversal['samples']}, P(转为下跌)={best_up_reversal['prob_reverse_direction']:.2%}")
    else:
        print("上涨后反转: 未找到满足样本数阈值的组合")
    if best_down_reversal:
        print(f"下跌后反转: N={best_down_reversal['N']}, X>={best_down_reversal['threshold']}, "
              f"samples={best_down_reversal['samples']}, P(转为上涨)={best_down_reversal['prob_reverse_direction']:.2%}")
    else:
        print("下跌后反转: 未找到满足样本数阈值的组合")

    print("\n所有 N/X 组合的概率表（连续趋势延续）")
    if streak_results["up"]:
        df_up = pd.DataFrame(streak_results["up"]).sort_values(["N", "threshold"])
        print("\n上涨延续组合：")
        print(df_up.to_string(index=False))
    else:
        print("上涨延续组合：无")

    if streak_results["down"]:
        df_down = pd.DataFrame(streak_results["down"]).sort_values(["N", "threshold"])
        print("\n下跌延续组合：")
        print(df_down.to_string(index=False))
    else:
        print("下跌延续组合：无")

    print("\n所有 N/X 组合的概率表（趋势反转）")
    if streak_results["up_reversal"]:
        df_up_rev = pd.DataFrame(streak_results["up_reversal"]).sort_values(["N", "threshold"])
        print("\n上涨后反转组合：")
        print(df_up_rev.to_string(index=False))
    else:
        print("上涨后反转组合：无")

    if streak_results["down_reversal"]:
        df_down_rev = pd.DataFrame(streak_results["down_reversal"]).sort_values(["N", "threshold"])
        print("\n下跌后反转组合：")
        print(df_down_rev.to_string(index=False))
    else:
        print("下跌后反转组合：无")

plt.show()


if __name__ == "__main__":
    main()
