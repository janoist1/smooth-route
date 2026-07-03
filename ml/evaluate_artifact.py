#!/usr/bin/env python3
"""
Promotion gate: measure ANY saved RQI artifact on the official CV protocol and
decide whether it may go live.

This is the contract referenced by AGENTS.md and ml/README.md: a new/changed
`ml/cache/rqi_model.joblib` may only ship if it MEETS OR BEATS the current
champion on the same fixed 5-fold split (seed=42) as ml/experiments.py.

What it does (honest, no leakage):
  1. Load the artifact; read its feature_recipe + backbone; clone the trained
     head (last pipeline step) so we evaluate the SAME recipe/hyperparameters.
  2. Rebuild features from the cache and run 5-fold stratified CV, refitting the
     head on each train fold (the artifact's own fit is ignored — CV must be
     out-of-fold).
  3. Report MAE / exact / ±1 / QWK / bad-road acc+AUC, and PASS/FAIL vs the gate.

Exit code 0 = PASS (promotable), 1 = FAIL, 2 = error (missing cache etc.).

Usage:
  .venv/bin/python ml/evaluate_artifact.py                      # default artifact
  .venv/bin/python ml/evaluate_artifact.py path/to/other.joblib
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (cohen_kappa_score, mean_absolute_error,
                             roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Reuse the exact recipe/feature logic and CV constants the trainer uses.
from save_model_v2 import (BAD_FROM, DROP_RQI5, N_SPLITS, ROAD_PROB_MIN,
                           RQI_MAX, RQI_MIN, SEED, build_features)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")
DEFAULT_ARTIFACT = os.path.join(CACHE, "rqi_model.joblib")

# Champion gate (v2, 2026-07-03). A candidate must not regress beyond a small
# tolerance on any headline metric.
GATE = {"qwk": 0.889, "mae": 0.195, "bad_auc": 0.970}
TOL = {"qwk": 0.005, "mae": 0.005, "bad_auc": 0.005}  # allow tiny CV noise


def _backbone_key(name: str) -> str:
    # full HF backbone name -> feats_v2_<key>.npz cache key.
    return {
        "facebook/dinov2-small": "small",
        "facebook/dinov2-base": "base",
        "facebook/dinov3-vits16-pretrain-lvd1689m": "v3small",
        "facebook/dinov3-vitb16-pretrain-lvd1689m": "v3base",
    }.get(name, "small")


def _head_from_artifact(pipe):
    """Clone the head (final estimator) so we refit the same hyperparameters."""
    est = pipe.steps[-1][1] if hasattr(pipe, "steps") else pipe
    return clone(est)


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_ARTIFACT
    if not os.path.exists(path):
        print(f"ERROR: artifact not found: {path}")
        return 2

    art = joblib.load(path)
    recipe = art.get("feature_recipe", {}).get("name")
    if recipe is None:
        print("ERROR: artifact has no feature_recipe (v1 artifact?); cannot gate.")
        return 2
    backbone = _backbone_key(art.get("backbone", "facebook/dinov2-small"))
    head = _head_from_artifact(art["pipeline"])
    thresholds = art.get("thresholds")

    print(f"Artifact : {os.path.relpath(path, ROOT)}")
    print(f"Recipe   : {recipe}  |  backbone: {backbone}  |  head: "
          f"{type(head).__name__}")
    print(f"CV       : {N_SPLITS}-fold stratified, seed={SEED} "
          f"(same folds as experiments.py)\n")

    try:
        X_all = build_features(recipe, backbone)
    except FileNotFoundError as e:
        print(f"ERROR: feature cache missing ({e}). Run extract_features_v2.py.")
        return 2

    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X_all[keep], df[keep].reset_index(drop=True)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    is_bad = (yc >= BAD_FROM).astype(int)

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    oof = np.zeros(len(y))
    for tr, te in skf.split(X, yc):
        pipe = make_pipeline(StandardScaler(), clone(head)).fit(X[tr], y[tr])
        oof[te] = pipe.predict(X[te])

    if thresholds:
        yp = (np.digitize(oof, thresholds) + 1).astype(int)
    else:
        yp = np.clip(np.round(oof), RQI_MIN, RQI_MAX).astype(int)

    metrics = {
        "mae": float(mean_absolute_error(yc, yp)),
        "exact": float(np.mean(yc == yp)),
        "off1": float(np.mean(np.abs(yc - yp) <= 1)),
        "qwk": float(cohen_kappa_score(yc, yp, weights="quadratic",
                                       labels=list(range(RQI_MIN, RQI_MAX + 1)))),
        "bad_acc": float(np.mean((oof >= BAD_FROM - 0.5).astype(int) == is_bad)),
        "bad_auc": float(roc_auc_score(is_bad, oof)),
    }

    print(f"n={len(df)} images")
    print(f"  MAE      : {metrics['mae']:.3f}")
    print(f"  exact    : {metrics['exact']:.3f}")
    print(f"  ±1 acc   : {metrics['off1']:.3f}")
    print(f"  QWK      : {metrics['qwk']:.3f}")
    print(f"  bad acc  : {metrics['bad_acc']:.3f}")
    print(f"  bad AUC  : {metrics['bad_auc']:.3f}\n")

    # gate: higher-is-better for qwk/auc, lower-is-better for mae
    checks = {
        "qwk": metrics["qwk"] >= GATE["qwk"] - TOL["qwk"],
        "mae": metrics["mae"] <= GATE["mae"] + TOL["mae"],
        "bad_auc": metrics["bad_auc"] >= GATE["bad_auc"] - TOL["bad_auc"],
    }
    for k, ok in checks.items():
        arrow = "≥" if k != "mae" else "≤"
        print(f"  [{'PASS' if ok else 'FAIL'}] {k} {metrics[k]:.3f} "
              f"{arrow} gate {GATE[k]} (±{TOL[k]})")

    passed = all(checks.values())
    print(f"\n{'✅ PASS — promotable' if passed else '❌ FAIL — do NOT ship'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main(sys.argv))
