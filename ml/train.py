#!/usr/bin/env python3
"""
Honest cross-validated baseline for RQI (1-5, lower = better road).

Uses the cached frozen DINOv2 features (ml/cache/features.npz) + labels.
Trains a small ordinal head as *regression* on the continuous RQI, evaluated
with 5-fold stratified CV. Reports the metrics that matter for an ordinal
scale (MAE, off-by-one accuracy, quadratic weighted kappa) against naive
baselines, plus a pooled confusion matrix.

Usage:  .venv/bin/python ml/train.py
"""
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import cohen_kappa_score, confusion_matrix, mean_absolute_error
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True          # only 3 present, partly non-road junk
ROAD_PROB_MIN = 0.55      # drop obvious non-road panoramas
N_SPLITS = 5
SEED = 42


def load():
    df = pd.read_csv(os.path.join(CACHE, "dataset.csv"))
    X = np.load(os.path.join(CACHE, "features.npz"))["dinov2"]
    keep = np.ones(len(df), dtype=bool)
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    keep &= df["is_road_prob"].values >= ROAD_PROB_MIN
    return X[keep], df[keep].reset_index(drop=True)


def evaluate(y_true, y_pred_cont, classes):
    lo, hi = classes.min(), classes.max()
    y_pred = np.clip(np.round(y_pred_cont), lo, hi).astype(int)
    mae = mean_absolute_error(y_true, y_pred)
    off1 = np.mean(np.abs(y_true - y_pred) <= 1)
    exact = np.mean(y_true == y_pred)
    qwk = cohen_kappa_score(y_true, y_pred, weights="quadratic",
                            labels=list(range(lo, hi + 1)))
    return mae, exact, off1, qwk, y_pred


def main():
    X, df = load()
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    classes = np.unique(yc)
    print(f"Training set: {len(df)} images, classes {list(classes)}")
    print("Class counts:", dict(pd.Series(yc).value_counts().sort_index()))
    print(f"CV: {N_SPLITS}-fold stratified, backbone=DINOv2-small (frozen)\n")

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    maes, exacts, off1s, qwks = [], [], [], []
    all_true, all_pred = [], []

    for fold, (tr, te) in enumerate(skf.split(X, yc), 1):
        scaler = StandardScaler().fit(X[tr])
        Xtr, Xte = scaler.transform(X[tr]), scaler.transform(X[te])
        model = Ridge(alpha=10.0).fit(Xtr, y[tr])
        pred = model.predict(Xte)
        mae, exact, off1, qwk, yp = evaluate(yc[te], pred, classes)
        maes.append(mae); exacts.append(exact); off1s.append(off1); qwks.append(qwk)
        all_true.extend(yc[te]); all_pred.extend(yp)
        print(f"  fold {fold}: MAE={mae:.3f}  exact={exact:.3f}  "
              f"±1={off1:.3f}  QWK={qwk:.3f}")

    print("\n=== DINOv2 + Ridge (5-fold CV mean ± std) ===")
    print(f"  MAE        : {np.mean(maes):.3f} ± {np.std(maes):.3f}")
    print(f"  exact acc  : {np.mean(exacts):.3f} ± {np.std(exacts):.3f}")
    print(f"  ±1 acc     : {np.mean(off1s):.3f} ± {np.std(off1s):.3f}")
    print(f"  QWK        : {np.mean(qwks):.3f} ± {np.std(qwks):.3f}")

    # naive baselines for context
    maj = pd.Series(yc).mode()[0]
    mae_maj = mean_absolute_error(yc, np.full_like(yc, maj))
    mae_mean = mean_absolute_error(yc, np.full(len(yc), round(y.mean())))
    print("\n=== naive baselines ===")
    print(f"  predict majority class ({maj}): MAE={mae_maj:.3f}")
    print(f"  predict rounded mean        : MAE={mae_mean:.3f}")

    print("\n=== pooled confusion matrix (rows=true, cols=pred) ===")
    cm = confusion_matrix(all_true, all_pred, labels=list(classes))
    hdr = "      " + "".join(f"{c:>6}" for c in classes)
    print(hdr)
    for c, row in zip(classes, cm):
        print(f"  t{c}: " + "".join(f"{v:>6}" for v in row))


if __name__ == "__main__":
    main()
