#!/usr/bin/env python3
"""
Model-improvement experiments on the enlarged labelled set.

Grid: feature variants (CLS / +patch tokens / +flip averaging / +bottom-crop /
+CLIP concat) x heads (Ridge, Huber, SVR-RBF, HistGB, MLP). Every cell uses the
SAME 5-fold stratified split, so numbers are directly comparable.

Reports, per cell: MAE, exact acc, +-1 acc, QWK — plus binary good(1-2) vs
bad(3-4) accuracy/AUC, since the product question is "is this road good or bad".

Usage:  .venv/bin/python ml/experiments.py [--backbone small|base] [--quick]
"""
import argparse
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, Ridge, RidgeCV
from sklearn.metrics import (cohen_kappa_score, confusion_matrix,
                             mean_absolute_error, roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True
ROAD_PROB_MIN = 0.55
N_SPLITS = 5
SEED = 42
BAD_FROM = 3  # rqi >= 3 counts as "bad road" for the binary view


def load(backbone):
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    F = np.load(os.path.join(CACHE, f"feats_v2_{backbone}.npz"))
    C = np.load(os.path.join(CACHE, "clip_v2.npz"))
    keep = np.ones(len(df), dtype=bool)
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    keep &= df["is_road_prob"].values >= ROAD_PROB_MIN
    feats = {k: F[k][keep] for k in F.files}
    feats["clip"] = C["clip"][keep]
    return feats, df[keep].reset_index(drop=True)


def variants(f):
    """name -> feature matrix. flipavg averages original+flip (TTA baked in)."""
    cls_avg = (f["cls"] + f["cls_flip"]) / 2
    patch_avg = (f["patch"] + f["patch_flip"]) / 2
    return {
        "cls (baseline)": f["cls"],
        "patch": f["patch"],
        "cls+patch": np.hstack([f["cls"], f["patch"]]),
        "cls+patch flipavg": np.hstack([cls_avg, patch_avg]),
        "cls+patch+crop": np.hstack([f["cls"], f["patch"], f["patch_crop"]]),
        "cls+patch+clip": np.hstack([f["cls"], f["patch"], f["clip"]]),
        "all": np.hstack([cls_avg, patch_avg, f["patch_crop"], f["clip"]]),
    }


def heads(quick=False):
    h = {
        "ridge": lambda: RidgeCV(alphas=[1, 3, 10, 30, 100, 300]),
        "huber": lambda: HuberRegressor(alpha=1e-3, max_iter=500),
    }
    if not quick:
        h["svr-rbf"] = lambda: SVR(C=3.0)
        h["histgb"] = lambda: HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.06, max_depth=None,
            l2_regularization=1.0, random_state=SEED)
        h["mlp"] = lambda: MLPRegressor(
            hidden_layer_sizes=(256,), alpha=1e-3, batch_size=64,
            learning_rate_init=1e-3, max_iter=400, early_stopping=True,
            n_iter_no_change=20, random_state=SEED)
    return h


def eval_fold(y_true_c, pred_cont, classes):
    lo, hi = classes.min(), classes.max()
    yp = np.clip(np.round(pred_cont), lo, hi).astype(int)
    mae = mean_absolute_error(y_true_c, yp)
    exact = np.mean(y_true_c == yp)
    off1 = np.mean(np.abs(y_true_c - yp) <= 1)
    qwk = cohen_kappa_score(y_true_c, yp, weights="quadratic",
                            labels=list(range(lo, hi + 1)))
    return mae, exact, off1, qwk, yp


def run_cell(X, y, yc, classes, head_fn, folds):
    m = {"mae": [], "exact": [], "off1": [], "qwk": []}
    oof_pred = np.zeros(len(y))
    for tr, te in folds:
        sc = StandardScaler().fit(X[tr])
        model = head_fn()
        model.fit(sc.transform(X[tr]), y[tr])
        pred = model.predict(sc.transform(X[te]))
        oof_pred[te] = pred
        mae, exact, off1, qwk, _ = eval_fold(yc[te], pred, classes)
        for k, v in zip(("mae", "exact", "off1", "qwk"), (mae, exact, off1, qwk)):
            m[k].append(v)
    # binary good/bad on pooled out-of-fold continuous predictions
    is_bad = (yc >= BAD_FROM).astype(int)
    bin_acc = np.mean(((oof_pred >= BAD_FROM - 0.5).astype(int)) == is_bad)
    auc = roc_auc_score(is_bad, oof_pred)
    return {k: (np.mean(v), np.std(v)) for k, v in m.items()} | {
        "bin_acc": (bin_acc, 0.0), "auc": (auc, 0.0)}, oof_pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", choices=["small", "base"], default="small")
    ap.add_argument("--quick", action="store_true", help="ridge+huber only")
    args = ap.parse_args()

    feats, df = load(args.backbone)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    classes = np.unique(yc)
    print(f"Dataset: {len(df)} images  classes={list(classes)}  "
          f"counts={dict(pd.Series(yc).value_counts().sort_index())}")
    print(f"Backbone: dinov2-{args.backbone}   CV: {N_SPLITS}-fold stratified "
          f"(seed {SEED})\n")

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    folds = list(skf.split(np.zeros(len(yc)), yc))

    results = []
    best = None
    for vname, X in variants(feats).items():
        for hname, hfn in heads(args.quick).items():
            metrics, oof = run_cell(X, y, yc, classes, hfn, folds)
            results.append((vname, hname, metrics))
            q = metrics["qwk"][0]
            if best is None or q > best[2]["qwk"][0]:
                best = (vname, hname, metrics, oof)
            print(f"{vname:22s} {hname:8s} "
                  f"MAE={metrics['mae'][0]:.3f}  exact={metrics['exact'][0]:.3f}  "
                  f"±1={metrics['off1'][0]:.3f}  QWK={metrics['qwk'][0]:.3f}  "
                  f"| bad: acc={metrics['bin_acc'][0]:.3f} AUC={metrics['auc'][0]:.3f}")

    vname, hname, metrics, oof = best
    print(f"\n=== BEST by QWK: {vname} + {hname} ===")
    for k in ("mae", "exact", "off1", "qwk"):
        mu, sd = metrics[k]
        print(f"  {k:6s}: {mu:.3f} ± {sd:.3f}")
    print(f"  binary bad-road: acc={metrics['bin_acc'][0]:.3f}  "
          f"AUC={metrics['auc'][0]:.3f}")

    lo, hi = classes.min(), classes.max()
    yp = np.clip(np.round(oof), lo, hi).astype(int)
    print("\nPooled OOF confusion matrix (rows=true, cols=pred):")
    cm = confusion_matrix(yc, yp, labels=list(classes))
    print("      " + "".join(f"{c:>6}" for c in classes))
    for c, row in zip(classes, cm):
        print(f"  t{c}: " + "".join(f"{v:>6}" for v in row))

    out = os.path.join(CACHE, f"experiments_{args.backbone}.csv")
    pd.DataFrame(
        [(v, h, *(m[k][0] for k in ("mae", "exact", "off1", "qwk", "bin_acc", "auc")))
         for v, h, m in results],
        columns=["variant", "head", "mae", "exact", "off1", "qwk", "bin_acc", "auc"],
    ).to_csv(out, index=False)
    print(f"\nSaved full grid -> {out}")


if __name__ == "__main__":
    main()
