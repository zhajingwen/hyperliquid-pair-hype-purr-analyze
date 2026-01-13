import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller


class CointegrationHealthMonitor:
    """
    Cointegration Health Monitor
    - 4H level structure monitor
    - Outputs health score (0-100) + state
    """

    # ===== 状态枚举 =====
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DANGER = "DANGER"
    DEAD = "DEAD"

    def __init__(
        self,
        window=200,
        beta_window=20,
        adf_history=10,
        max_halflife=30,
        min_halflife=5,
        state_thresholds=(80, 60, 40),
    ):
        self.window = window
        self.beta_window = beta_window
        self.adf_history = adf_history
        self.max_halflife = max_halflife
        self.min_halflife = min_halflife
        self.state_thresholds = state_thresholds

        # 历史缓存
        self.beta_history = []
        self.adf_pass_history = []

    # ==========================================================
    # 主入口
    # ==========================================================
    def update(self, logA: pd.Series, logB: pd.Series):
        """
        Update with latest 4H window data
        """
        if len(logA) < self.window or len(logB) < self.window:
            raise ValueError("Not enough data for rolling window")

        logA = logA[-self.window:]
        logB = logB[-self.window:]

        beta, spread = self._estimate_beta_and_spread(logA, logB)

        adf_score, adf_pvalue = self._adf_strength_score(spread)
        halflife_score, halflife = self._halflife_score(spread)
        stability_score = self._stability_score(spread, beta)

        health_score = (
            0.4 * adf_score
            + 0.3 * halflife_score
            + 0.3 * stability_score
        )

        state = self._state_from_score(health_score)

        return {
            "health_score": round(health_score, 2),
            "state": state,
            "adf_pvalue": adf_pvalue,
            "halflife": round(halflife, 2),
            "beta": beta,
            "scores": {
                "adf": round(adf_score, 2),
                "halflife": round(halflife_score, 2),
                "stability": round(stability_score, 2),
            },
        }

    # ==========================================================
    # 内部组件
    # ==========================================================
    def _estimate_beta_and_spread(self, logA, logB):
        X = sm.add_constant(logB)
        model = sm.OLS(logA, X).fit()
        beta = model.params.iloc[1]

        spread = logA - beta * logB

        self.beta_history.append(beta)
        self.beta_history = self.beta_history[-self.beta_window:]

        return beta, spread

    # ---------------- ADF 强度 ----------------
    def _adf_strength_score(self, spread):
        adf_stat, pvalue, *_ = adfuller(spread, autolag="AIC")

        adf_pass = pvalue < 0.05
        self.adf_pass_history.append(int(adf_pass))
        self.adf_pass_history = self.adf_pass_history[-self.adf_history:]

        if pvalue > 0.1:
            score = 0
        elif pvalue < 0.01:
            score = 40
        else:
            score = 40 * (0.1 - pvalue) / (0.1 - 0.01)

        return score, pvalue

    # ---------------- 半衰期 ----------------
    def _halflife_score(self, spread):
        spread_lag = spread.shift(1).iloc[1:]
        delta = spread.diff().iloc[1:]

        model = sm.OLS(delta, sm.add_constant(spread_lag)).fit()
        phi = model.params.iloc[1]

        if phi >= 0:
            halflife = np.inf
        else:
            halflife = np.log(2) / -np.log(1 + phi)

        if halflife <= self.min_halflife:
            score = 30
        elif halflife >= self.max_halflife:
            score = 0
        else:
            score = 30 * (
                (self.max_halflife - halflife)
                / (self.max_halflife - self.min_halflife)
            )

        return score, halflife

    # ---------------- 稳定性 ----------------
    def _stability_score(self, spread, beta):
        score = 0

        # --- β 稳定性 (0–10) ---
        if len(self.beta_history) >= 5:
            beta_cv = np.std(self.beta_history) / abs(np.mean(self.beta_history))
            if beta_cv < 0.05:
                score += 10
            elif beta_cv < 0.15:
                score += 5

        # --- 均值漂移 (0–10) ---
        recent_mean = spread[-20:].mean()
        old_mean = spread[:20].mean()
        spread_std = spread.std()

        mean_shift = abs(recent_mean - old_mean) / spread_std
        if mean_shift < 0.5:
            score += 10
        elif mean_shift < 1.5:
            score += 5

        # --- ADF 持续性 (0–10) ---
        if len(self.adf_pass_history) > 0:
            score += 10 * (sum(self.adf_pass_history) / len(self.adf_pass_history))

        return score

    # ---------------- 状态机 ----------------
    def _state_from_score(self, score):
        high, mid, low = self.state_thresholds

        if score >= high:
            return self.HEALTHY
        elif score >= mid:
            return self.WARNING
        elif score >= low:
            return self.DANGER
        else:
            return self.DEAD
