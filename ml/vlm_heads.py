"""
Era 9 candidate head: champion SVR score stacked with VLM attributes.

X = [DINOv2-small cls+patch (n_base cols) | encoded VLM attributes]. The base
model is exactly the champion head (SVR-RBF C=1, eps=0.05) on the DINO block;
a ridge stacker then maps [base score, attributes] -> RQI.

The stacker must never see in-sample base scores (an SVR fits its own training
frames far better than new ones), so the base is CROSS-FITTED inside fit():
KFold without shuffling, i.e. contiguous row blocks. dataset_v2 rows are in
route order, so a block is a few km of consecutive road — a cheap stand-in for
spatial groups (the head never receives coordinates). The final base model is
then refit on all rows for predict().

Used via save_model_v2.py --recipe cls+patch+vlm --head stack-vlm; gated by
ml/evaluate_artifact.py like any other head. Inference needs the VLM
attributes of the frame (ml/vlm_attribute_prompt.md) — see MODEL_EXPERIMENTS
Era 9.
"""
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR


class StackedVLMHead(BaseEstimator, RegressorMixin):
    def __init__(self, n_base=768, C=1.0, epsilon=0.05, n_folds=5,
                 alphas=(0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)):
        self.n_base = n_base
        self.C = C
        self.epsilon = epsilon
        self.n_folds = n_folds
        self.alphas = alphas

    def _svr(self):
        return SVR(C=self.C, gamma="scale", epsilon=self.epsilon)

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        Xb, A = X[:, :self.n_base], X[:, self.n_base:]
        oof = np.zeros(len(y))
        for tr, te in KFold(self.n_folds, shuffle=False).split(Xb):
            oof[te] = self._svr().fit(Xb[tr], y[tr]).predict(Xb[te])
        self.base_ = self._svr().fit(Xb, y)
        Z = np.column_stack([oof, A])
        self.scaler_ = StandardScaler().fit(Z)
        self.stack_ = RidgeCV(alphas=list(self.alphas)).fit(
            self.scaler_.transform(Z), y)
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        s = self.base_.predict(X[:, :self.n_base])
        Z = np.column_stack([s, X[:, self.n_base:]])
        return self.stack_.predict(self.scaler_.transform(Z))
