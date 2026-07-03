#!/usr/bin/env python3
"""
Train the final v2 RQI model on ALL usable data and save a deployable artifact.

Adds over v1:
  - configurable feature recipe (which DINOv2 views/tokens + optional CLIP)
  - SVR-RBF head (the CV winner) with tuned hyperparameters
  - ordinal cut-points tuned on out-of-fold predictions (instead of fixed .5
    rounding), stored in the artifact
  - isotonic P(bad road) calibration fitted on out-of-fold predictions, so the
    artifact can answer "how sure are we this road is bad (RQI>=3)?" honestly
  - per-predicted-class empirical reliability table from CV (what the true
    class distribution looks like when the model outputs k)

The recipe is stored machine-readably in the artifact; inference code
(ml/predict.py, backend dino_service) builds features from it.

Usage:  .venv/bin/python ml/save_model_v2.py --recipe cls+patch [--head svr-rbf]
"""
import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import RidgeCV
from sklearn.metrics import (cohen_kappa_score, mean_absolute_error,
                             roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True
ROAD_PROB_MIN = 0.55
RQI_MIN, RQI_MAX = 1, 4
BAD_FROM = 3
N_SPLITS = 5
SEED = 42

# recipe -> (feature keys concatenated in order, needs_clip)
# keys refer to arrays in feats_v2_<backbone>.npz; "clip" comes from clip_v2.npz
RECIPES = {
    "cls": (["cls"], False),
    "cls+patch": (["cls", "patch"], False),
    "cls+patch+clip": (["cls", "patch", "clip"], True),
    "cls+patch flipavg": (["cls_avg", "patch_avg"], False),
    "all": (["cls_avg", "patch_avg", "patch_crop", "clip"], True),
}

HEADS = {
    "ridge": lambda: RidgeCV(alphas=[1, 3, 10, 30, 100, 300]),
    # tuned on 5-fold CV (ml/tune_svr.py): C=1, gamma=scale, eps=0.05
    "svr-rbf": lambda: SVR(C=1.0, gamma="scale", epsilon=0.05),
}

# backbone key -> full HF name written into the artifact (the backend loads this
# name). Must stay in sync with extract_features_v2.BACKBONES.
BACKBONE_NAMES = {
    "small": "facebook/dinov2-small",
    "base": "facebook/dinov2-base",
    "v3small": "facebook/dinov3-vits16-pretrain-lvd1689m",
    "v3base": "facebook/dinov3-vitb16-pretrain-lvd1689m",
}


def tune_thresholds(y_true, pred):
    """Greedy per-boundary search for the 3 ordinal cut-points, maximising QWK."""
    th = [1.5, 2.5, 3.5]
    for _ in range(3):
        for i in range(3):
            lo = th[i - 1] if i else 0.8
            hi = th[i + 1] if i < 2 else 4.2
            best_q, best_t = -1.0, th[i]
            for t in np.linspace(lo + 0.02, hi - 0.02, 60):
                cand = sorted(th[:i] + [t] + th[i + 1:])
                q = cohen_kappa_score(y_true, np.digitize(pred, cand) + 1,
                                      weights="quadratic", labels=[1, 2, 3, 4])
                if q > best_q:
                    best_q, best_t = q, t
            th[i] = best_t
            th = sorted(th)
    return [float(t) for t in th]


def build_features(recipe, backbone):
    F = np.load(os.path.join(CACHE, f"feats_v2_{backbone}.npz"))
    C = np.load(os.path.join(CACHE, "clip_v2.npz"))
    pool = {k: F[k] for k in F.files}
    pool["cls_avg"] = (pool["cls"] + pool["cls_flip"]) / 2
    pool["patch_avg"] = (pool["patch"] + pool["patch_flip"]) / 2
    pool["clip"] = C["clip"]
    keys, _ = RECIPES[recipe]
    return np.hstack([pool[k] for k in keys])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", choices=list(RECIPES), default="cls+patch")
    ap.add_argument("--head", choices=list(HEADS), default="svr-rbf")
    ap.add_argument("--backbone", choices=list(BACKBONE_NAMES), default="small")
    ap.add_argument("--out", default="rqi_model.joblib",
                    help="artifact filename under ml/cache/ (use a side name to "
                         "build a gate candidate without clobbering the champion)")
    args = ap.parse_args()

    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X_all = build_features(args.recipe, args.backbone)
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X_all[keep], df[keep].reset_index(drop=True)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    is_bad = (yc >= BAD_FROM).astype(int)

    # ---- honest CV pass: metrics + OOF predictions for calibration ----
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    oof = np.zeros(len(y))
    for tr, te in skf.split(X, yc):
        pipe = make_pipeline(StandardScaler(), HEADS[args.head]())
        pipe.fit(X[tr], y[tr])
        oof[te] = pipe.predict(X[te])

    # ordinal cut-points tuned on the pooled OOF predictions
    thresholds = tune_thresholds(yc, oof)
    yp = (np.digitize(oof, thresholds) + 1).astype(int)
    cv = {
        "mae": float(mean_absolute_error(yc, yp)),
        "exact_acc": float(np.mean(yc == yp)),
        "off_by_one_acc": float(np.mean(np.abs(yc - yp) <= 1)),
        "qwk": float(cohen_kappa_score(yc, yp, weights="quadratic",
                                       labels=list(range(RQI_MIN, RQI_MAX + 1)))),
        "bad_road_acc": float(np.mean((oof >= BAD_FROM - 0.5).astype(int) == is_bad)),
        "bad_road_auc": float(roc_auc_score(is_bad, oof)),
    }

    # ---- P(bad) calibration on OOF scores ----
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(oof, is_bad)

    # ---- reliability: when model says k, what is true class distribution ----
    reliability = {}
    for k in range(RQI_MIN, RQI_MAX + 1):
        sel = yp == k
        if sel.sum() == 0:
            continue
        dist = {int(c): float(np.mean(yc[sel] == c))
                for c in range(RQI_MIN, RQI_MAX + 1)}
        reliability[int(k)] = {"n": int(sel.sum()), "true_dist": dist}

    # ---- final fit on 100% ----
    pipe = make_pipeline(StandardScaler(), HEADS[args.head]())
    pipe.fit(X, y)

    keys, needs_clip = RECIPES[args.recipe]
    artifact = {
        "version": 2,
        "pipeline": pipe,
        "p_bad_calibrator": iso,
        "backbone": BACKBONE_NAMES[args.backbone],
        "feature_recipe": {"name": args.recipe, "keys": keys,
                           "needs_clip": needs_clip,
                           "crop_top": 0.35},
        "head": args.head,
        "thresholds": thresholds,
        "rqi_clip": [RQI_MIN, RQI_MAX],
        "bad_from": BAD_FROM,
        "road_prob_min": ROAD_PROB_MIN,
        "n_train": int(len(df)),
        "scale_meaning": "1=excellent .. 4=poor (lower=better road)",
        "cv_metrics": cv,
        "reliability": reliability,
    }
    out = os.path.join(CACHE, args.out)
    joblib.dump(artifact, out)
    print(f"Trained on {len(df)} images -> {out}")
    print(json.dumps({k: v for k, v in artifact.items()
                      if k not in ("pipeline", "p_bad_calibrator")}, indent=2))


if __name__ == "__main__":
    main()
