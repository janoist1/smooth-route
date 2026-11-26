#!/usr/bin/env python3
"""
Novelty score: how unlike the labelled training frames is a frame?

The RQI model (frozen DINOv2-small CLS+patch -> StandardScaler -> SVR) is
reliable on roads like the ones that were labelled and unreliable on quite
different ones (leave-region-out QWK 0.66). Novelty = mean distance of a
frame's feature vector to its k nearest labelled training frames, in the same
StandardScaler space the SVR sees. Variants are compared in `validate`.

  validate   Honest check: each OOF frame's novelty is measured against its
             TRAIN folds only, then we ask whether higher novelty predicts a
             larger OOF error (error by novelty decile, AUC for
             |class error| >= 1, added value over the cut-point margin).
             --cv spatial (default): the official 1 km spatial CV.
             --cv region: leave-one-region-out (the "new region" case).

Result (2026-11-26, T-33): NOT predictive enough to drive map confidence.
AUC(|err|>=1) 0.56-0.60 under spatial CV, 0.53-0.62 leave-region-out,
the best variant differs per protocol, the error rate is flat over novelty
deciles 2-9, and novelty adds nothing over the cut-point margin (logistic AUC
0.625 -> 0.613-0.633). Only the lowest decile (near-copies of training frames)
is clearly easier. So no analysis_metadata.novelty is written.

Usage (PY = /Users/i/Dev/smooth-route/.venv/bin/python):
  PY ml/novelty.py validate [--cv spatial|region]
"""
import argparse
import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml"))
import spatial_cv as S  # noqa: E402
from save_model_v2 import DROP_RQI5, ROAD_PROB_MIN, build_features  # noqa: E402

CACHE = os.path.join(ROOT, "ml", "cache")
ARTIFACT = os.path.join(CACHE, "rqi_model.joblib")
OUT_DIR = os.path.join(CACHE, "novelty")
VALIDATION_JSON = os.path.join(OUT_DIR, "validation.json")

K = 10
PCA_DIM = 64            # Mahalanobis variant: whitened top-PCA space of the train set
METHOD = "knn10_cosine"  # variant used for the familiar/unfamiliar split printout


# ---------------------------------------------------------------------------
# Novelty variants. fit(X_train) -> callable(X_query, exclude_self=False)
# ---------------------------------------------------------------------------
def _knn(metric, k=K):
    def fit(Xtr):
        sc = StandardScaler().fit(Xtr)
        Z = sc.transform(Xtr)
        nn = NearestNeighbors(n_neighbors=k + 1, metric=metric).fit(Z)

        def score(Xq, exclude_self=False):
            d, _ = nn.kneighbors(sc.transform(Xq), n_neighbors=k + (1 if exclude_self else 0))
            return d[:, 1:].mean(1) if exclude_self else d.mean(1)
        return score
    return fit


def _mahalanobis(dim=PCA_DIM):
    def fit(Xtr):
        from sklearn.decomposition import PCA
        sc = StandardScaler().fit(Xtr)
        pca = PCA(n_components=dim, whiten=True, random_state=0).fit(sc.transform(Xtr))

        def score(Xq, exclude_self=False):
            return np.linalg.norm(pca.transform(sc.transform(Xq)), axis=1)
        return score
    return fit


VARIANTS = {
    "knn10_euclid": _knn("euclidean"),
    "knn10_cosine": _knn("cosine"),
    "mahalanobis_pca64": _mahalanobis(),
}


# ---------------------------------------------------------------------------
def labelled_set():
    """Same data, filters and head as ml/evaluate_artifact.py."""
    art = joblib.load(ARTIFACT)
    recipe = art["feature_recipe"]["name"]
    X = build_features(recipe, "small")
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X[keep], df[keep].reset_index(drop=True)
    head = art["pipeline"].steps[-1][1]
    return X, df, head, art


def auc(y, s):
    return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float("nan")


def cmd_validate(args):
    X, df, head, _ = labelled_set()
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    coords = S.load_coords(df["image_filename"])
    groups = S.grid_cells(coords["lat"].values, coords["lon"].values)
    area = coords["area"].values

    t0 = time.time()
    if args.cv == "region":
        res = leave_region_out(X, y, yc, df, area, head)
    else:
        res = S.nested_spatial_cv(X, y, yc, groups, lambda: clone(head))
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    print(f"[validate] {args.cv} CV: QWK {m['qwk']:.3f}  MAE {m['mae']:.3f}  "
          f"AUC {m['bad_auc']:.3f}  ({time.time() - t0:.0f} s)")

    nov = {v: np.zeros(len(y)) for v in VARIANTS}
    margin = np.zeros(len(y))
    for k in range(res["fold"].max() + 1):
        te, tr = res["fold"] == k, res["fold"] != k
        for v, fit in VARIANTS.items():
            nov[v][te] = fit(X[tr])(X[te])
        th = np.asarray(res["thresholds"][k])
        margin[te] = np.abs(res["oof"][te][:, None] - th[None, :]).min(1)

    err = np.abs(res["pred"] - yc)
    big = (err >= 1).astype(int)
    cerr = np.abs(res["oof"] - y)
    out = {"n": int(len(y)), "error_rate": float(big.mean()), "variants": {}}
    print(f"[validate] n={len(y)}, OOF |class error| >= 1: {big.mean():.1%}")
    print(f"  baseline  margin to nearest cut-point: AUC(|err|>=1) = {auc(big, -margin):.3f}")
    for v, s in nov.items():
        rho = pd.Series(s).corr(pd.Series(cerr), method="spearman")
        dec = pd.qcut(s, 10, labels=False)
        rate = pd.Series(big).groupby(dec).mean().values
        mae = pd.Series(cerr).groupby(dec).mean().values
        # within-area AUC: does novelty still rank errors when the region is fixed?
        within = {a: auc(big[area == a], s[area == a]) for a in np.unique(area)}
        # does novelty add to the cut-point margin? (logistic, spatial CV)
        add = _added_value(big, margin, s, groups, yc)
        out["variants"][v] = {
            "auc": auc(big, s), "spearman_abs_err": float(rho),
            "decile_error_rate": [round(float(r), 3) for r in rate],
            "decile_mae": [round(float(r), 3) for r in mae],
            "within_area_auc": {a: round(x, 3) for a, x in within.items()},
            "auc_margin_only": add[0], "auc_margin_plus_novelty": add[1],
        }
        print(f"\n  {v}: AUC(|err|>=1) {auc(big, s):.3f}   Spearman vs |score err| {rho:.3f}")
        print("    error rate by novelty decile (low -> high): " + " ".join(f"{r:.2f}" for r in rate))
        print("    MAE        by novelty decile (low -> high): " + " ".join(f"{r:.2f}" for r in mae))
        print("    within-area AUC: " + ", ".join(f"{a} {x:.3f}" for a, x in within.items()))
        print(f"    logistic (spatial CV) AUC: margin only {add[0]:.3f} -> margin + novelty {add[1]:.3f}")

    # calibration of the familiar flag for the production variant
    s = nov[METHOD]
    cal = {}
    for q in (0.8, 0.9, 0.95):
        t = float(np.quantile(s, q))
        hi = s > t
        acc_f, acc_u = 1 - big[~hi].mean(), 1 - big[hi].mean()
        cal[str(q)] = {"threshold": t, "exact_familiar": float(acc_f), "exact_unfamiliar": float(acc_u),
                       "mae_familiar": float(cerr[~hi].mean()), "mae_unfamiliar": float(cerr[hi].mean()),
                       "off2_unfamiliar": float((err[hi] >= 2).mean())}
        print(f"  [{METHOD}] unfamiliar = top {1 - q:.0%} (novelty > {t:.4f}): exact "
              f"{acc_f:.1%} familiar vs {acc_u:.1%} unfamiliar; MAE {cerr[~hi].mean():.3f} vs "
              f"{cerr[hi].mean():.3f}")
    out["calibration"] = cal
    out["by_area_mean_novelty"] = {a: float(s[area == a].mean()) for a in np.unique(area)}
    os.makedirs(OUT_DIR, exist_ok=True)
    pd.DataFrame({"image_filename": df["image_filename"], "area": area, "fold": res["fold"],
                  "y": y, "oof": res["oof"], "pred": res["pred"], "margin": margin,
                  **{f"nov_{v}": s for v, s in nov.items()}}).to_csv(
        os.path.join(OUT_DIR, f"validation_oof_{args.cv}.csv"), index=False)
    with open(VALIDATION_JSON.replace(".json", f"_{args.cv}.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"\n[validate] -> {VALIDATION_JSON.replace('.json', f'_{args.cv}.json')}")


def leave_region_out(X, y, yc, df, area, head):
    """One fold per collection region; cut-points tuned by inner spatial CV
    on the training regions only."""
    oof, pred, fold = np.zeros(len(y)), np.zeros(len(y), dtype=int), np.zeros(len(y), dtype=int)
    ths = []
    for k, a in enumerate(np.unique(area)):
        te, tr = area == a, area != a
        c = S.load_coords(df["image_filename"][tr])
        g = S.grid_cells(c["lat"].values, c["lon"].values)
        inner = S.nested_spatial_cv(X[tr], y[tr], yc[tr], g, lambda: clone(head), tune=False)
        th = S.tune_thresholds(yc[tr], inner["oof"])
        oof[te] = S._fit_predict(lambda: clone(head), X[tr], y[tr], X[te])
        pred[te] = np.digitize(oof[te], th) + 1
        fold[te] = k
        ths.append(th)
    return {"oof": oof, "pred": pred, "fold": fold, "thresholds": ths}


def _added_value(big, margin, nov, groups, yc):
    from sklearn.linear_model import LogisticRegression
    p1, p2 = np.zeros(len(big)), np.zeros(len(big))
    for tr, te in S.spatial_folds(yc, groups):
        for cols, p in (([margin], p1), ([margin, np.log(nov + 1e-9)], p2)):
            Z = np.c_[tuple(cols)]
            sc = StandardScaler().fit(Z[tr])
            lr = LogisticRegression().fit(sc.transform(Z[tr]), big[tr])
            p[te] = lr.predict_proba(sc.transform(Z[te]))[:, 1]
    return round(auc(big, p1), 3), round(auc(big, p2), 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--cv", choices=["spatial", "region"], default="spatial")
    v.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
