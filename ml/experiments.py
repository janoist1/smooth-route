#!/usr/bin/env python3
"""
Model-improvement experiment grid on the OFFICIAL spatial CV protocol.

Grid: feature variants (CLS / +patch tokens / +flip averaging / +bottom-crop /
+CLIP concat) x heads (Ridge, SVR-RBF at a few C values, proportional-odds
ordinal logistic; --full adds Huber, HistGB, MLP). Every cell uses the SAME
spatially grouped folds as the promotion gate (ml/spatial_cv.py: 1 km grid
cells, StratifiedGroupKFold, seed=42) and the same NESTED cut-point tuning, so
a cell's numbers are directly comparable with `evaluate_artifact.py`.

`--cv random` reproduces the legacy (leaky) random stratified 5-fold, for
old-vs-new comparison only — never decide on it.

Reports per cell: MAE, exact, ±1, QWK, bad-road (RQI>=3) acc + AUC, and the
fold-to-fold std of QWK.

Usage:  .venv/bin/python ml/experiments.py [--backbone small|base|v3small]
                                           [--cv spatial|random] [--full]
"""
import argparse
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, RidgeCV
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPRegressor
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from heads import OrdinalLogistic  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = S.ROOT
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True
ROAD_PROB_MIN = 0.55
SEED = S.SEED


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


def heads(full=False):
    h = {
        "ridge": lambda: RidgeCV(alphas=[1, 3, 10, 30, 100, 300, 1000, 3000]),
        # champion head (C=1, eps=0.05) plus a stronger/weaker regularisation
        "svr C=0.3": lambda: SVR(C=0.3, gamma="scale", epsilon=0.05),
        "svr C=1": lambda: SVR(C=1.0, gamma="scale", epsilon=0.05),
        "svr C=3": lambda: SVR(C=3.0, gamma="scale", epsilon=0.05),
        "ordlogit": lambda: OrdinalLogistic(alpha=300.0),
    }
    if full:
        h["huber"] = lambda: HuberRegressor(alpha=1e-3, max_iter=500)
        h["histgb"] = lambda: HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.06, max_depth=None,
            l2_regularization=1.0, random_state=SEED)
        h["mlp"] = lambda: MLPRegressor(
            hidden_layer_sizes=(256,), alpha=1e-3, batch_size=64,
            learning_rate_init=1e-3, max_iter=400, early_stopping=True,
            n_iter_no_change=20, random_state=SEED)
    return h


def run_random(X, y, yc, make_model):
    """Legacy random stratified CV with nested cut-points (comparison only)."""
    skf = StratifiedKFold(n_splits=S.N_SPLITS, shuffle=True, random_state=SEED)
    oof = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    fold = np.zeros(len(y), dtype=int)
    for k, (tr, te) in enumerate(skf.split(X, yc)):
        oof[te] = S._fit_predict(make_model, X[tr], y[tr], X[te])
        fold[te] = k
        inner = StratifiedKFold(S.INNER_SPLITS, shuffle=True, random_state=SEED)
        ioof = np.zeros(len(tr))
        for itr, ite in inner.split(X[tr], yc[tr]):
            ioof[ite] = S._fit_predict(make_model, X[tr][itr], y[tr][itr],
                                       X[tr][ite])
        pred[te] = np.digitize(oof[te], S.tune_thresholds(yc[tr], ioof)) + 1
    return {"oof": oof, "pred": pred, "fold": fold}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone",
                    choices=["small", "base", "v3small", "v3base"], default="small")
    ap.add_argument("--cv", choices=["spatial", "random"], default="spatial")
    ap.add_argument("--full", action="store_true",
                    help="also run huber/histgb/mlp heads (slow, never won)")
    ap.add_argument("--variants", default="",
                    help="comma-separated subset of feature variants")
    args = ap.parse_args()

    feats, df = load(args.backbone)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    coords = S.load_coords(df["image_filename"])
    groups = S.grid_cells(coords["lat"].values, coords["lon"].values)
    print(f"Dataset: {len(df)} images  counts="
          f"{dict(pd.Series(yc).value_counts().sort_index())}")
    proto = (f"spatial {S.N_SPLITS}-fold, {S.CELL_M} m cells "
             f"({len(np.unique(groups))} cells)" if args.cv == "spatial"
             else f"RANDOM {S.N_SPLITS}-fold (legacy, leaky)")
    print(f"Backbone: {args.backbone}   CV: {proto}, seed {SEED}, "
          f"nested cut-points\n")

    want = [v.strip() for v in args.variants.split(",") if v.strip()]
    results, best = [], None
    for vname, X in variants(feats).items():
        if want and vname not in want:
            continue
        for hname, hfn in heads(args.full).items():
            t0 = time.time()
            if args.cv == "spatial":
                res = S.nested_spatial_cv(X, y, yc, groups, hfn)
            else:
                res = run_random(X, y, yc, hfn)
            m = S.ordinal_metrics(yc, res["pred"], res["oof"])
            m["qwk_fold_std"] = S.per_fold_std(yc, res)["qwk"]
            results.append((vname, hname, m))
            if best is None or m["qwk"] > best[2]["qwk"]:
                best = (vname, hname, m, res)
            print(f"{vname:20s} {hname:10s} MAE={m['mae']:.3f}  "
                  f"exact={m['exact']:.3f}  ±1={m['off1']:.3f}  "
                  f"QWK={m['qwk']:.3f}±{m['qwk_fold_std']:.3f}  "
                  f"| bad: acc={m['bad_acc']:.3f} AUC={m['bad_auc']:.3f}"
                  f"  [{time.time() - t0:.0f}s]", flush=True)

    vname, hname, m, res = best
    print(f"\n=== BEST by QWK: {vname} + {hname} ===")
    for k in ("mae", "exact", "off1", "qwk", "bad_acc", "bad_auc"):
        print(f"  {k:8s}: {m[k]:.3f}")
    print("\nPooled OOF confusion matrix (rows=true, cols=pred):")
    cm = confusion_matrix(yc, res["pred"], labels=S.RQI_LABELS)
    print("      " + "".join(f"{c:>6}" for c in S.RQI_LABELS))
    for c, row in zip(S.RQI_LABELS, cm):
        print(f"  t{c}: " + "".join(f"{v:>6}" for v in row))

    out = os.path.join(CACHE, f"experiments_{args.cv}_{args.backbone}.csv")
    cols = ["mae", "exact", "off1", "qwk", "qwk_fold_std", "bad_acc", "bad_auc"]
    pd.DataFrame([(v, h, *(mm[k] for k in cols)) for v, h, mm in results],
                 columns=["variant", "head", *cols]).to_csv(out, index=False)
    print(f"\nSaved full grid -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
