"""
Extra regression heads for the RQI experiments (sklearn-compatible).

OrdinalLogistic — proportional-odds (cumulative-logit, "all-threshold")
ordinal regression with an L2 penalty, the classic statistical model for an
ordered 1..K scale:  P(y <= k | x) = sigmoid(c_k - w·x),  c_1 < ... < c_{K-1}.
``predict`` returns the expected class E[y | x] as a continuous score, so it
plugs into the same cut-point tuning / AUC code as the regression heads.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.base import BaseEstimator, RegressorMixin


class OrdinalLogistic(BaseEstimator, RegressorMixin):
    def __init__(self, alpha=10.0, max_iter=500):
        self.alpha = alpha
        self.max_iter = max_iter

    @staticmethod
    def _cuts(t):
        return np.concatenate([[t[0]], t[0] + np.cumsum(np.exp(t[1:]))])

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        yk = np.rint(np.asarray(y)).astype(int)
        self.classes_ = np.unique(yk)
        K = len(self.classes_)
        k = np.searchsorted(self.classes_, yk)  # 0..K-1
        n, d = X.shape

        def unpack(p):
            return p[:d], p[d:]

        def f(p):
            w, t = unpack(p)
            c = self._cuts(t)
            cext = np.concatenate([[-np.inf], c, [np.inf]])
            eta = X @ w
            a, b = cext[k + 1] - eta, cext[k] - eta
            Fa, Fb = expit(a), expit(b)
            P = np.clip(Fa - Fb, 1e-12, None)
            fa, fb = Fa * (1 - Fa), Fb * (1 - Fb)
            nll = -np.log(P).sum() + 0.5 * self.alpha * (w @ w)
            g_eta = (fa - fb) / P
            g_w = X.T @ g_eta + self.alpha * w
            g_c = np.zeros(K - 1)
            for j in range(K - 1):
                g_c[j] = -(fa[k == j] / P[k == j]).sum() \
                    + (fb[k == j + 1] / P[k == j + 1]).sum()
            # chain rule through c = t0 + cumsum(exp(t1..))
            g_t = np.zeros(K - 1)
            g_t[0] = g_c.sum()
            for j in range(1, K - 1):
                g_t[j] = np.exp(t[j]) * g_c[j:].sum()
            return nll, np.concatenate([g_w, g_t])

        prior = np.cumsum(np.bincount(k, minlength=K))[:-1] / n
        c0 = np.log(prior / (1 - prior))
        t0 = np.concatenate([[c0[0]], np.log(np.maximum(np.diff(c0), 1e-3))])
        p0 = np.concatenate([np.zeros(d), t0])
        res = minimize(f, p0, jac=True, method="L-BFGS-B",
                       options={"maxiter": self.max_iter})
        self.coef_, t = unpack(res.x)
        self.cuts_ = self._cuts(t)
        return self

    def predict_proba(self, X):
        eta = np.asarray(X, dtype=float) @ self.coef_
        F = expit(self.cuts_[None, :] - eta[:, None])
        F = np.hstack([np.zeros((len(eta), 1)), F, np.ones((len(eta), 1))])
        return np.diff(F, axis=1)

    def predict(self, X):
        return self.predict_proba(X) @ self.classes_.astype(float)
