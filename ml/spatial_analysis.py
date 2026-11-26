#!/usr/bin/env python3
"""
Spatial-leakage diagnostics for the RQI model (reproduces the numbers in
docs/MODEL_EXPERIMENTS.md, "Térbeli CV" section).

Sections:
  1. label variogram   — how fast RQI similarity decays with distance
                         (picks the grid-cell size for spatial CV)
  2. cell-size curve   — champion recipe under random CV vs grid cells of
                         200 m / 500 m / 1 km / 2 km / 3 km, plus
                         leave-one-area-out; several seeds for the spread
  3. "GPS-only" baseline — a model that only sees coordinates (k-NN on lat/lon).
                         If it scores well under a protocol, that protocol
                         leaks location.
  4. error analysis at the official protocol (1 km cells): per area,
                         Budapest vs vidék, per class (confusion + recall).

Usage:
  .venv/bin/python ml/spatial_analysis.py [--backbone small] [--seeds 5]
       [--out ml/cache/spatial_analysis.json]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.metrics.pairwise import haversine_distances
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from save_model_v2 import DROP_RQI5, ROAD_PROB_MIN, build_features  # noqa: E402

CACHE = os.path.join(S.ROOT, "ml", "cache")
CHAMP = lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)  # noqa: E731


def load(backbone, recipe="cls+patch"):
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X = build_features(recipe, backbone)
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= ~np.isin(df["rqi"].values, S.DROPPED_LEVELS)
    df = df[keep].reset_index(drop=True)
    c = S.load_coords(df["image_filename"])
    df["lat"], df["lon"], df["area"] = c["lat"], c["lon"], c["area"]
    return X[keep], df


def variogram(df):
    X = np.radians(df[["lat", "lon"]].values)
    D = haversine_distances(X) * 6_371_000
    y = df["rqi"].values.astype(float)
    iu = np.triu_indices(len(y), 1)
    d, g = D[iu], 0.5 * (y[iu[0]] - y[iu[1]]) ** 2
    bins = [0, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10_000, 1e9]
    rows = []
    for a, b in zip(bins[:-1], bins[1:]):
        s = (d >= a) & (d < b)
        rows.append({"from_m": a, "to_m": b, "pairs": int(s.sum()),
                     "semivar": float(g[s].mean())})
    return rows, float(y.var())


def random_cv(X, y, yc, make_model, seed):
    """Legacy protocol (random stratified 5-fold) with nested cut-points."""
    skf = StratifiedKFold(n_splits=S.N_SPLITS, shuffle=True, random_state=seed)
    oof, pred = np.zeros(len(y)), np.zeros(len(y), dtype=int)
    for tr, te in skf.split(X, yc):
        oof[te] = S._fit_predict(make_model, X[tr], y[tr], X[te])
        inner = StratifiedKFold(S.INNER_SPLITS, shuffle=True, random_state=seed)
        ioof = np.zeros(len(tr))
        for itr, ite in inner.split(X[tr], yc[tr]):
            ioof[ite] = S._fit_predict(make_model, X[tr][itr], y[tr][itr],
                                       X[tr][ite])
        pred[te] = np.digitize(oof[te], S.tune_thresholds(yc[tr], ioof)) + 1
    return S.ordinal_metrics(yc, pred, oof)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", default="small")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(CACHE, "spatial_analysis.json"))
    args = ap.parse_args()

    X, df = load(args.backbone)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    lat, lon, area = df["lat"].values, df["lon"].values, df["area"].values
    report = {}

    # ---- 1. variogram ----
    vg, var = variogram(df)
    report["variogram"] = {"bins": vg, "total_var": var}
    print("== 1. RQI variogram (semivariance vs distance) ==")
    for r in vg:
        print(f"  {r['from_m']:>7.0f}-{r['to_m']:<9.0f} m  pairs={r['pairs']:>8}"
              f"  γ={r['semivar']:.3f}")
    print(f"  total variance={var:.3f}\n")

    # ---- 2. cell-size curve (champion recipe) ----
    seeds = [S.SEED] + [s for s in range(args.seeds * 2) if s != S.SEED][: args.seeds - 1]
    # perturbation per repeat: random CV -> fold seed; spatial -> fold seed AND
    # a random grid-origin offset (repeat 0 = the official seed-42, offset 0).
    offsets = [(0.0, 0.0)] + [tuple(np.random.default_rng(s).random(2))
                              for s in seeds[1:]]
    print(f"== 2. Cell-size curve: cls+patch + SVR (champion), "
          f"{len(seeds)} repeats (fold seed + grid offset) ==")
    curve = {}
    protos = ["random"] + [f"{m}m" for m in (200, 500, 1000, 2000, 3000)]
    for p in protos:
        ms = []
        for sd, off in zip(seeds, offsets):
            if p == "random":
                m = random_cv(X, y, yc, CHAMP, sd)
            else:
                g = S.grid_cells(lat, lon, int(p[:-1]), off)
                r = S.nested_spatial_cv(X, y, yc, g, CHAMP, seed=sd)
                m = S.ordinal_metrics(yc, r["pred"], r["oof"])
            ms.append(m)
        agg = {k: (float(np.mean([m[k] for m in ms])),
                   float(np.std([m[k] for m in ms])))
               for k in ("qwk", "mae", "exact", "bad_auc")}
        agg["seed42"] = ms[0]
        if p != "random":
            agg["n_cells"] = int(len(np.unique(S.grid_cells(lat, lon, int(p[:-1])))))
        curve[p] = agg
        print(f"  {p:>7}  cells={agg.get('n_cells', '-'):>4}  "
              f"QWK={agg['qwk'][0]:.3f}±{agg['qwk'][1]:.3f}  "
              f"MAE={agg['mae'][0]:.3f}±{agg['mae'][1]:.3f}  "
              f"exact={agg['exact'][0]:.3f}  AUC={agg['bad_auc'][0]:.3f}"
              f"±{agg['bad_auc'][1]:.3f}   (official QWK={ms[0]['qwk']:.3f})")
    report["cell_curve"] = curve

    # leave-one-area-out
    print("\n  leave-one-area-out (train on 3 areas, test on the 4th):")
    lo = {}
    pooled_pred, pooled_oof = np.zeros(len(y), int), np.zeros(len(y))
    g1k = S.grid_cells(lat, lon, S.CELL_M)
    for a in S.AREA_LABELS:
        te = area == a
        tr = ~te
        oof_te = S._fit_predict(CHAMP, X[tr], y[tr], X[te])
        inner = S.spatial_folds(yc[tr], g1k[tr], S.INNER_SPLITS, S.SEED)
        ioof = np.zeros(tr.sum())
        for itr, ite in inner:
            ioof[ite] = S._fit_predict(CHAMP, X[tr][itr], y[tr][itr], X[tr][ite])
        pred_te = np.digitize(oof_te, S.tune_thresholds(yc[tr], ioof)) + 1
        pooled_pred[te], pooled_oof[te] = pred_te, oof_te
        m = S.ordinal_metrics(yc[te], pred_te, oof_te)
        m["true_dist"] = {int(k): int(v) for k, v in
                          zip(*np.unique(yc[te], return_counts=True))}
        m["pred_dist"] = {int(k): int(v) for k, v in
                          zip(*np.unique(pred_te, return_counts=True))}
        m["mean_true"] = float(y[te].mean())
        m["mean_pred"] = float(oof_te.mean())
        lo[a] = m
        print(f"    {S.AREA_LABELS[a]:22s} n={m['n']:>4}  QWK={m['qwk']:.3f}  "
              f"MAE={m['mae']:.3f}  exact={m['exact']:.3f}  AUC={m['bad_auc']:.3f}"
              f"  mean true/pred={m['mean_true']:.2f}/{m['mean_pred']:.2f}")
    lo["pooled"] = S.ordinal_metrics(yc, pooled_pred, pooled_oof)
    print(f"    {'pooled':22s} n={len(y):>4}  QWK={lo['pooled']['qwk']:.3f}  "
          f"MAE={lo['pooled']['mae']:.3f}  exact={lo['pooled']['exact']:.3f}  "
          f"AUC={lo['pooled']['bad_auc']:.3f}")
    report["leave_one_area_out"] = lo

    # ---- 3. GPS-only baseline ----
    print("\n== 3. GPS-only baseline (k-NN on lat/lon, no image at all) ==")
    XY = np.c_[lat * 111.32, lon * 111.32 * np.cos(np.radians(47.0))]  # km
    gps = {}
    for p in ("random", "1000m"):
        knn = lambda: KNeighborsRegressor(n_neighbors=5)  # noqa: E731
        if p == "random":
            m = random_cv(XY, y, yc, knn, S.SEED)
        else:
            r = S.nested_spatial_cv(XY, y, yc, g1k, knn)
            m = S.ordinal_metrics(yc, r["pred"], r["oof"])
        gps[p] = m
        print(f"  {p:>7}: QWK={m['qwk']:.3f}  MAE={m['mae']:.3f}  "
              f"exact={m['exact']:.3f}  AUC={m['bad_auc']:.3f}")
    report["gps_only"] = gps

    # ---- 4. error analysis at the official protocol ----
    print(f"\n== 4. Error analysis — official protocol ({S.CELL_M} m cells, seed {S.SEED}) ==")
    r = S.nested_spatial_cv(X, y, yc, g1k, CHAMP)
    overall = S.ordinal_metrics(yc, r["pred"], r["oof"])
    overall["ci95"] = S.cluster_bootstrap_ci(yc, r, g1k)
    print(f"  overall: QWK={overall['qwk']:.3f}  MAE={overall['mae']:.3f}  "
          f"exact={overall['exact']:.3f}  AUC={overall['bad_auc']:.3f}")
    print(f"  cell-bootstrap 95% CI: " + "  ".join(
        f"{k}=[{a:.3f}, {b:.3f}]" for k, (a, b) in overall["ci95"].items()))
    ea = {"overall": overall, "per_area": {}, "per_class": {}}
    regions = {**{a: area == a for a in S.AREA_LABELS},
               "budapest_city": area == "budapest",
               "videk_plus_agglo": area != "budapest"}
    for name, s in regions.items():
        m = S.ordinal_metrics(yc[s], r["pred"][s], r["oof"][s])
        m["bias"] = float(np.mean(r["pred"][s] - yc[s]))
        ea["per_area"][name] = m
        print(f"  {name:18s} n={m['n']:>4}  QWK={m['qwk']:.3f}  MAE={m['mae']:.3f}"
              f"  exact={m['exact']:.3f}  AUC={m['bad_auc']:.3f}  "
              f"bias(pred-true)={m['bias']:+.2f}")
    cm = confusion_matrix(yc, r["pred"], labels=S.RQI_LABELS)
    print("\n  confusion (rows=true, cols=pred):")
    print("        " + "".join(f"{c:>6}" for c in S.RQI_LABELS) + "  recall")
    for c, row in zip(S.RQI_LABELS, cm):
        rec = row[c - 1] / max(row.sum(), 1)
        prec = cm[c - 1, c - 1] / max(cm[:, c - 1].sum(), 1)
        ea["per_class"][c] = {"n": int(row.sum()), "recall": float(rec),
                              "precision": float(prec),
                              "mean_abs_err": float(np.mean(np.abs(
                                  r["pred"][yc == c] - c)))}
        print(f"   t{c}:  " + "".join(f"{v:>6}" for v in row) + f"  {rec:.2f}")
    ea["confusion"] = cm.tolist()
    print("  precision: " + "  ".join(
        f"{c}:{ea['per_class'][c]['precision']:.2f}" for c in S.RQI_LABELS))
    report["error_analysis"] = ea

    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, default=float)
    print(f"\nSaved -> {os.path.relpath(args.out, S.ROOT)}")


if __name__ == "__main__":
    main()
