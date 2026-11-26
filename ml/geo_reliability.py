#!/usr/bin/env python3
"""
T-41: does GEOGRAPHY predict segment error where appearance (novelty, T-33)
did not?

Under the official spatial protocol (ml/spatial_cv.py via ml/segment_eval.py:
champion OOF, 1 km cells, StratifiedGroupKFold 5, seed 42, nested cut-points;
200 m segments, median score, 3 cut phases) every test segment gets
geographic features computed from the TRAINING folds only:

  dist_km     distance from the segment centroid to the nearest training frame
  n_1km/n_3km training frames within 1 / 3 km (label density)
  classes_3km distinct human classes among those training frames (coverage)
  loc_err_3km inner-OOF error rate of the training frames within 3 km
              (how wrong the model already is around here, in-fold)

and two error targets: wrong class (pred != median human class) and wrong
good/bad. Reports the length-weighted AUC of each feature (oriented so that
"far / sparse / uncovered" = more error), error rates by distance bin, and
whether geography adds anything to the existing segment confidence
(cross-fold logistic regression: confidence vs confidence + geography).

Usage: /Users/i/Dev/smooth-route/.venv/bin/python ml/geo_reliability.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segment_eval as E  # noqa: E402
import spatial_cv as S  # noqa: E402

LENGTH_M = 200
KIND = "median_score"
CONF = {"n_ref": 0.5, "spread_ref": 2.0, "margin_ref": 0.6}  # segment_aggregation.json
DIST_BINS = [0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, np.inf]


def xy(lat, lon):
    return np.stack([np.asarray(lon) * 111.32 * np.cos(np.radians(47.0)),
                     np.asarray(lat) * 111.32], 1)        # km


def main():
    fr, inner, inner_p, _ = E.champion_oof()
    chain, pos, fp, rank = E.build_chains(fr)
    segsets = []
    for ph in E.PHASES:
        seg = E.cut_segments(chain, fp, rank, LENGTH_M, ph)
        segsets.append((seg, E.segment_table(seg, fr, fp)))
    ev = E.evaluate(fr, inner, inner_p, segsets, KIND)
    ths = ev["ths"]

    P = xy(fr["lat"], fr["lon"])
    lab = fr["human_rqi"].values
    fold = fr["fold"].values
    # inner-OOF frame error of training frames, per outer fold
    inner_err = np.full(inner.shape, np.nan)
    for k in range(S.N_SPLITS):
        tr = fold != k
        cls = np.digitize(inner[k, tr], ths[k]) + 1
        inner_err[k, tr] = (cls != lab[tr]).astype(float)
    trees = {k: cKDTree(P[fold != k]) for k in range(S.N_SPLITS)}

    rows = []
    score = fr["score"].values
    for ph, ((seg, st), run) in enumerate(zip(segsets, ev["runs"])):
        cen = pd.DataFrame(P).groupby(seg, sort=True).mean().values
        frames = pd.Series(np.arange(len(seg))).groupby(seg, sort=True).apply(
            lambda s: s.values)
        for s, idx in enumerate(frames):
            k = int(st["fold"].values[s])
            tr_idx = np.flatnonzero(fold != k)
            t = trees[k]
            d, _ = t.query(cen[s])
            near1 = t.query_ball_point(cen[s], 1.0)
            near3 = t.query_ball_point(cen[s], 3.0)
            n3 = tr_idx[near3]
            v = score[idx]
            a = float(np.median(v))
            gt, pred = int(st["gt"].values[s]), int(run["pred"][s])
            rows.append({
                "phase": ph, "fold": k, "area": st["area"].values[s],
                "w": float(st["length"].values[s]) / len(segsets),
                "dist_km": float(d), "n_1km": len(near1), "n_3km": len(near3),
                "classes_3km": len(np.unique(lab[n3])) if len(n3) else 0,
                "loc_err_3km": (float(np.nanmean(inner_err[k, n3]))
                                if len(n3) else np.nan),
                "conf": float(E.confidence(len(v), E.iqr_of(v),
                                           np.min(np.abs(np.asarray(ths[k]) - a)),
                                           **CONF)),
                "wrong": float(pred != gt),
                "wrong_gb": float((pred >= S.BAD_FROM) != (gt >= S.BAD_FROM)),
            })
    r = pd.DataFrame(rows)
    print(f"{len(r)} segment rows ({len(r) // len(segsets)} segments x "
          f"{len(segsets)} phases), {LENGTH_M} m, {KIND}; wrong class "
          f"{np.average(r.wrong, weights=r.w):.1%}, wrong good/bad "
          f"{np.average(r.wrong_gb, weights=r.w):.1%}")
    print("distance to nearest TRAIN frame (km): "
          + " ".join(f"p{q}={np.percentile(r.dist_km, q):.2f}"
                     for q in (10, 25, 50, 75, 90, 99)))

    feats = {"dist_km": 1, "n_1km": -1, "n_3km": -1, "classes_3km": -1,
             "loc_err_3km": 1, "conf (existing, reference)": -1}
    print("\nLength-weighted AUC (0.5 = no signal; oriented: far/sparse/"
          "uncovered/locally-wrong/low-confidence = error)")
    for f, sign in feats.items():
        col = f.split(" ")[0]
        m = r[col].notna()
        out = []
        for tgt in ("wrong", "wrong_gb"):
            out.append(roc_auc_score(r[tgt][m], sign * r[col][m],
                                     sample_weight=r.w[m]))
        print(f"  {f:28s} wrong class {out[0]:.3f}   wrong good/bad {out[1]:.3f}")

    print("\nError by distance bin (length-weighted)")
    r["bin"] = pd.cut(r.dist_km, DIST_BINS, right=False)
    for b, g in r.groupby("bin", observed=True):
        print(f"  {str(b):14s} n={len(g):4d}  wrong class "
              f"{np.average(g.wrong, weights=g.w):.1%}  wrong good/bad "
              f"{np.average(g.wrong_gb, weights=g.w):.1%}  mean conf "
              f"{np.average(g.conf, weights=g.w):.2f}")

    print("\nDoes geography add to the existing confidence? (cross-fold "
          "logistic regression, AUC on held-out folds)")
    r["log_d"] = np.log1p(r.dist_km * 10)
    r["log_n3"] = np.log1p(r.n_3km)
    r["loc"] = r.loc_err_3km.fillna(r.loc_err_3km.mean())
    for tgt in ("wrong", "wrong_gb"):
        for name, cols in [("conf", ["conf"]),
                           ("conf + dist + density", ["conf", "log_d", "log_n3"]),
                           ("conf + dist + density + loc_err",
                            ["conf", "log_d", "log_n3", "loc"])]:
            p = np.zeros(len(r))
            for k in range(S.N_SPLITS):
                te = r.fold == k
                lr = LogisticRegression(C=1.0).fit(r.loc[~te, cols], r[tgt][~te],
                                                   sample_weight=r.w[~te])
                p[te] = lr.predict_proba(r.loc[te, cols])[:, 1]
            print(f"  {tgt:9s} {name:34s} AUC {roc_auc_score(r[tgt], p, sample_weight=r.w):.3f}")

    print("\nPer area (distance + error)")
    for a, g in r.groupby("area"):
        print(f"  {a:15s} median dist {g.dist_km.median():.2f} km  wrong class "
              f"{np.average(g.wrong, weights=g.w):.1%}  AUC(dist->wrong) "
              + (f"{roc_auc_score(g.wrong, g.dist_km, sample_weight=g.w):.3f}"
                 if 0 < g.wrong.sum() < len(g) else "n/a"))
    out = os.path.join(E.CACHE, "geo_reliability_rows.csv")
    r.drop(columns=["bin"]).to_csv(out, index=False)
    print(f"\nrows -> {os.path.relpath(out, S.ROOT)}")


if __name__ == "__main__":
    main()
