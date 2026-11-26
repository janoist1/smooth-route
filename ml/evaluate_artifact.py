#!/usr/bin/env python3
"""
Promotion gate: measure ANY saved RQI artifact on the official SPATIAL CV
protocol and decide whether it may go live.

This is the contract referenced by AGENTS.md and ml/README.md: a new/changed
`ml/cache/rqi_model.joblib` may only ship if it MEETS OR BEATS the current
champion on the same spatially grouped 5-fold split (1 km grid cells,
StratifiedGroupKFold, seed=42) as ml/experiments.py — see ml/spatial_cv.py.

Why spatial: Street View frames are ~10 m apart. The old random 5-fold put
near-identical neighbours of a test frame into the training set and reported
QWK 0.895; on streets the model has never seen the same champion scores ~0.77.
The gate now measures the latter, honest number.

What it does (no leakage):
  1. Load the artifact; read its feature_recipe + backbone; clone the trained
     head (last pipeline step) so we evaluate the SAME recipe/hyperparameters.
  2. Rebuild features from the cache and run spatial 5-fold CV, refitting the
     head on each train fold (the artifact's own fit is ignored).
  3. Ordinal cut-points are tuned per outer fold on INNER spatial OOF
     predictions (the artifact's stored thresholds are NOT used — they were
     tuned on all labels, so using them here would leak).
  4. Report MAE / exact / ±1 / QWK / bad-road acc+AUC, fold spread and a
     per-area breakdown, and PASS/FAIL vs the gate.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
# Reuse the exact recipe/feature logic the trainer uses.
from save_model_v2 import (DROP_RQI5, ROAD_PROB_MIN,  # noqa: E402
                           build_features)

ROOT = S.ROOT
# RQI_ML_CACHE: see save_model_v2.py. The champion is <cache>/rqi_model.joblib
# (ml/retrain.py links it there).
CACHE = os.environ.get("RQI_ML_CACHE") or os.path.join(ROOT, "ml", "cache")
DEFAULT_ARTIFACT = os.path.join(CACHE, "rqi_model.joblib")

# Champion gate — v2 (DINOv2-small cls+patch + SVR-RBF) re-measured on the
# spatial protocol, 2026-11-18. A candidate must not regress beyond TOL on any
# headline metric. The official folds are deterministic (with km-scale cells
# StratifiedGroupKFold ignores the seed), so champion and candidate are
# compared on IDENTICAL folds and TOL only absorbs tiny refit noise. For scale:
# shifting the grid origin moves the champion by std QWK 0.011 / MAE 0.022 /
# AUC 0.001, and the cell-bootstrap 95% CI is QWK [0.694, 0.833] — so passing
# the gate means "not worse"; "measurably better" is the paired Δ check below.
GATE = {"qwk": 0.774, "mae": 0.405, "bad_auc": 0.934}
TOL = {"qwk": 0.005, "mae": 0.005, "bad_auc": 0.003}


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

    print(f"Artifact : {os.path.relpath(path, ROOT)}")
    print(f"Recipe   : {recipe}  |  backbone: {backbone}  |  head: "
          f"{type(head).__name__}")
    print(f"CV       : spatial {S.N_SPLITS}-fold StratifiedGroupKFold, "
          f"{S.CELL_M} m grid cells, seed={S.SEED}; cut-points nested "
          f"(inner {S.INNER_SPLITS}-fold spatial)\n")

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
    try:
        coords = S.load_coords(df["image_filename"])
    except (KeyError, ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 2
    groups = S.grid_cells(coords["lat"].values, coords["lon"].values)

    res = S.nested_spatial_cv(X, y, yc, groups, lambda: clone(head))
    metrics = S.ordinal_metrics(yc, res["pred"], res["oof"])
    spread = S.per_fold_std(yc, res)
    ci = S.cluster_bootstrap_ci(yc, res, groups)

    print(f"n={len(df)} images in {len(np.unique(groups))} cells")
    print(f"  MAE      : {metrics['mae']:.3f}   (fold std {spread['mae']:.3f})")
    print(f"  exact    : {metrics['exact']:.3f}")
    print(f"  ±1 acc   : {metrics['off1']:.3f}")
    print(f"  QWK      : {metrics['qwk']:.3f}   (fold std {spread['qwk']:.3f})")
    print(f"  bad acc  : {metrics['bad_acc']:.3f}")
    print(f"  bad AUC  : {metrics['bad_auc']:.3f}   (fold std {spread['bad_auc']:.3f})")
    print("  95% CI (cell bootstrap): " + "  ".join(
        f"{k} [{a:.3f}, {b:.3f}]" for k, (a, b) in ci.items()) + "\n")

    print("  per area (same OOF predictions; informational, not gated):")
    area = coords["area"].values
    for a, label in S.AREA_LABELS.items():
        s = area == a
        if not s.any():
            continue
        m = S.ordinal_metrics(yc[s], res["pred"][s], res["oof"][s])
        print(f"    {label:22s} n={m['n']:>4}  QWK={m['qwk']:.3f}  "
              f"MAE={m['mae']:.3f}  exact={m['exact']:.3f}  AUC={m['bad_auc']:.3f}")
    print()

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

    # Candidate vs champion, paired on the same folds: is it MEASURABLY better?
    if (os.path.abspath(path) != os.path.abspath(DEFAULT_ARTIFACT)
            and os.path.exists(DEFAULT_ARTIFACT)):
        champ = joblib.load(DEFAULT_ARTIFACT)
        cX = build_features(champ["feature_recipe"]["name"],
                            _backbone_key(champ.get("backbone", "")))[keep]
        chead = _head_from_artifact(champ["pipeline"])
        cres = S.nested_spatial_cv(cX, y, yc, groups, lambda: clone(chead))
        delta = S.paired_bootstrap_delta(yc, cres, res, groups)
        print("\n  vs live champion (candidate − champion, paired cell bootstrap):")
        for k, (dv, a, b) in delta.items():
            print(f"    Δ{k:8s} {dv:+.3f}  95% CI [{a:+.3f}, {b:+.3f}]")
        better = (delta["qwk"][1] > 0 and delta["mae"][2] < 0.02
                  and delta["bad_auc"][1] > -0.01)
        print("  → measurably better (ΔQWK CI > 0): "
              f"{'YES' if better else 'NO — keep the champion'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
