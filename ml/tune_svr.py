#!/usr/bin/env python3
"""
Focused tuning of the winning head (SVR-RBF) on the top feature variants,
plus ordinal cut-point tuning on top of the continuous predictions.

Grid: C x gamma x epsilon on {cls+patch, cls+patch flipavg} (and optionally
dinov2-base features). Same folds as experiments.py so results are comparable.

Cut-point tuning: instead of rounding at fixed .5 boundaries, learn the three
boundaries (1|2, 2|3, 3|4) that maximise QWK on each fold's TRAIN out-of-fold
predictions (inner 4-fold), then apply to the test fold. Honest, no leakage.

Usage:  .venv/bin/python ml/tune_svr.py [--backbone small|base]
"""
import argparse
import itertools
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, mean_absolute_error, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")
N_SPLITS, SEED, BAD_FROM = 5, 42, 3


def load(backbone):
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    F = np.load(os.path.join(CACHE, f"feats_v2_{backbone}.npz"))
    keep = (df["rqi"].values != 5) & (df["is_road_prob"].values >= 0.55)
    f = {k: F[k][keep] for k in F.files}
    df = df[keep].reset_index(drop=True)
    v = {
        "cls+patch": np.hstack([f["cls"], f["patch"]]),
        "cls+patch flipavg": np.hstack([(f["cls"] + f["cls_flip"]) / 2,
                                        (f["patch"] + f["patch_flip"]) / 2]),
    }
    return v, df


def metrics(yc, pred, thresholds=None):
    if thresholds is None:
        yp = np.clip(np.round(pred), 1, 4).astype(int)
    else:
        yp = np.digitize(pred, thresholds) + 1
    mae = mean_absolute_error(yc, yp)
    exact = np.mean(yc == yp)
    qwk = cohen_kappa_score(yc, yp, weights="quadratic", labels=[1, 2, 3, 4])
    return mae, exact, qwk, yp


def tune_thresholds(y_true, pred):
    """Greedy 1-D search per boundary, init at .5 midpoints."""
    th = [1.5, 2.5, 3.5]
    for it in range(3):
        for i in range(3):
            lo = th[i - 1] if i else 0.8
            hi = th[i + 1] if i < 2 else 4.2
            grid = np.linspace(lo + 0.02, hi - 0.02, 60)
            best_q, best_t = -1, th[i]
            for t in grid:
                cand = sorted(th[:i] + [t] + th[i + 1:])
                q = cohen_kappa_score(y_true, np.digitize(pred, cand) + 1,
                                      weights="quadratic", labels=[1, 2, 3, 4])
                if q > best_q:
                    best_q, best_t = q, t
            th[i] = best_t
            th = sorted(th)
    return th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", choices=["small", "base"], default="small")
    args = ap.parse_args()

    variants, df = load(args.backbone)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    is_bad = (yc >= BAD_FROM).astype(int)
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    folds = list(skf.split(np.zeros(len(yc)), yc))
    print(f"backbone=dinov2-{args.backbone}  n={len(df)}\n")

    grid = list(itertools.product([1, 3, 10, 30], ["scale", 3e-4, 1e-3],
                                  [0.05, 0.1, 0.2]))
    best = None
    for vname, X in variants.items():
        for C, gamma, eps in grid:
            oof = np.zeros(len(y))
            for tr, te in folds:
                sc = StandardScaler().fit(X[tr])
                m = SVR(C=C, gamma=gamma, epsilon=eps)
                m.fit(sc.transform(X[tr]), y[tr])
                oof[te] = m.predict(sc.transform(X[te]))
            mae, exact, qwk, _ = metrics(yc, oof)
            auc = roc_auc_score(is_bad, oof)
            tag = f"{vname:18s} C={C:<3} gamma={str(gamma):6s} eps={eps}"
            if best is None or qwk > best[1]:
                best = (tag, qwk, mae, exact, auc, vname, (C, gamma, eps), oof.copy())
            print(f"{tag}  MAE={mae:.3f} exact={exact:.3f} QWK={qwk:.4f} AUC={auc:.4f}")

    tag, qwk, mae, exact, auc, vname, params, oof = best
    print(f"\n=== best: {tag}  QWK={qwk:.4f} MAE={mae:.3f} exact={exact:.3f} ===")

    # honest nested threshold tuning for the best config
    C, gamma, eps = params
    X = variants[vname]
    oof_t = np.zeros(len(y))
    for tr, te in folds:
        sc = StandardScaler().fit(X[tr])
        m = SVR(C=C, gamma=gamma, epsilon=eps).fit(sc.transform(X[tr]), y[tr])
        # inner OOF on the training part for threshold fitting
        inner = StratifiedKFold(4, shuffle=True, random_state=SEED)
        inner_oof = np.zeros(len(tr))
        for itr, ite in inner.split(np.zeros(len(tr)), yc[tr]):
            isc = StandardScaler().fit(X[tr][itr])
            im = SVR(C=C, gamma=gamma, epsilon=eps).fit(
                isc.transform(X[tr][itr]), y[tr][itr])
            inner_oof[ite] = im.predict(isc.transform(X[tr][ite]))
        th = tune_thresholds(yc[tr], inner_oof)
        pred = m.predict(sc.transform(X[te]))
        oof_t[te] = np.digitize(pred, th) + 1  # store the CLASS this time

    yp = oof_t.astype(int)
    mae_t = mean_absolute_error(yc, yp)
    exact_t = np.mean(yc == yp)
    qwk_t = cohen_kappa_score(yc, yp, weights="quadratic", labels=[1, 2, 3, 4])
    print(f"with nested tuned thresholds: MAE={mae_t:.3f} exact={exact_t:.3f} "
          f"QWK={qwk_t:.4f}")


if __name__ == "__main__":
    main()
