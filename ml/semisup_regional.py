#!/usr/bin/env python3
"""
Era 10: can UNLABELLED frames fix regional generalisation?

Two cheap, cached-feature experiments on the champion recipe (DINOv2-small
cls+patch, StandardScaler + SVR-RBF C=1 eps=0.05), each measured under
  - the official spatial protocol (ml/spatial_cv.py: 1 km cells,
    StratifiedGroupKFold 5, seed 42, nested cut-points), and
  - leave-one-area-out (LORO: train on 3 collection areas, test on the 4th;
    cut-points nested on 1 km cells of the training areas),
paired against the champion on identical folds (cell bootstrap of ΔQWK).

1. Self-training. Per outer fold, the champion fitted on the training labels
   scores the unlabelled frames (ml/cache/frame_feats_v2.npz, ~15.7k frames);
   frames whose score is >= MARGIN from every cut-point AND whose
   neighbours within NEIGH_M agree on the class are added with their
   predicted class as target and weight W < 1. Pool rules:
     strict        never a frame in a test cell (spatial) / the test area (LORO)
     transductive  (LORO only) also the test area's UNLABELLED frames: they are
                   available at deploy time for a new region; no test label used
2. Regional feature normalisation. Subtract (optionally divide by) the
   feature mean/std of ALL frames (labelled + unlabelled; no labels involved,
   so legitimate at test time) in the frame's neighbourhood:
     area     the collection area
     r<k>km   frames within k km of the frame
   Variants: replace x by x - mu, or concatenate [x, x - mu].

Reports QWK / MAE / AUC, class-2 recall, Budapest QWK/AUC and per-area bias
(mean predicted − mean true score) — the regional offset we want to remove.

Inputs: ml/cache/{dataset_v2.csv, feats_v2_small.npz, frame_feats_v2.npz,
frame_meta.csv (id, lat, lon, image_url from Postgres)}.
Usage: /Users/i/Dev/smooth-route/.venv/bin/python ml/semisup_regional.py [--only norm|self]
       (norm ~10 min, self ~25 min on CPU; frame_meta.csv: see Era 10 in
       docs/MODEL_EXPERIMENTS.md for the one-line Postgres export)
Result (2026-11-26): neither helps; see docs/MODEL_EXPERIMENTS.md "Era 10".
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.metrics import recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from build_coords import assign_area  # noqa: E402
from save_model_v2 import DROP_RQI5, ROAD_PROB_MIN, build_features  # noqa: E402

warnings.filterwarnings("ignore")
CACHE = os.path.join(S.ROOT, "ml", "cache")
AREAS = list(S.AREA_LABELS)
MARGIN = 0.35        # pseudo-label: |score - nearest cut-point| >= MARGIN
NEIGH_M = 40.0       # ... and the neighbours within 40 m agree on the class
MAX_PSEUDO = 2000    # cap per fold (class-balanced subsample)


def head():
    return SVR(C=1.0, gamma="scale", epsilon=0.05)


def km_xy(lat, lon):
    return np.stack([np.asarray(lon) * 111.32 * np.cos(np.radians(47.0)),
                     np.asarray(lat) * 111.32], 1)


def cell_keys(lat, lon):
    """Raw 1 km grid keys (same formula as spatial_cv.grid_cells)."""
    ky = np.floor(np.asarray(lat) * 111_320.0 / S.CELL_M).astype(np.int64)
    kx = np.floor(np.asarray(lon) * 111_320.0 * np.cos(np.radians(47.0))
                  / S.CELL_M).astype(np.int64)
    return ky * 1_000_000 + kx


# --------------------------------------------------------------------------
def load():
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X_all = build_features("cls+patch", "small")
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= ~np.isin(df["rqi"].values, S.DROPPED_LEVELS)
    X, df = X_all[keep], df[keep].reset_index(drop=True)
    c = S.load_coords(df["image_filename"])
    lab = {"X": X, "y": df["manual_rqi"].values.astype(float),
           "yc": df["rqi"].values.astype(int), "lat": c["lat"].values,
           "lon": c["lon"].values, "area": c["area"].values,
           "files": df["image_filename"].values}
    lab["groups"] = S.grid_cells(lab["lat"], lab["lon"])
    lab["ckey"] = cell_keys(lab["lat"], lab["lon"])

    z = np.load(os.path.join(CACHE, "frame_feats_v2.npz"), allow_pickle=True)
    meta = pd.read_csv(os.path.join(CACHE, "frame_meta.csv")).set_index("id")
    ids = z["ids"].astype(int)
    ok = z["usable"] & np.isin(ids, meta.index.values)
    m = meta.loc[ids[ok]]
    fname = m["image_url"].fillna("").str.replace("images/", "", regex=False).values
    unl = ~np.isin(fname, lab["files"])          # labelled frames are not "unlabelled"
    U = {"X": z["feats"][ok][unl].astype(np.float32),
         "lat": m["lat"].values[unl], "lon": m["lon"].values[unl]}
    U["area"] = assign_area(U["lat"], U["lon"])
    U["ckey"] = cell_keys(U["lat"], U["lon"])
    return lab, U


def folds(lab, kind):
    if kind == "spatial":
        return S.spatial_folds(lab["yc"], lab["groups"])
    return [(np.flatnonzero(lab["area"] != a), np.flatnonzero(lab["area"] == a))
            for a in AREAS]


def fit_predict(Xtr, ytr, Xte, w=None):
    m = make_pipeline(StandardScaler(), head())
    m.fit(Xtr, ytr, svr__sample_weight=w)
    return m.predict(Xte)


def inner_thresholds(lab, X, tr, extra=None):
    """Cut-points tuned on inner spatial OOF of the training labels (as the
    gate); ``extra`` = (Xp, yp, wp) pseudo rows added to every inner fit."""
    ioof = np.zeros(len(tr))
    for itr, ite in S.spatial_folds(lab["yc"][tr], lab["groups"][tr], S.INNER_SPLITS):
        Xa, ya, wa = X[tr][itr], lab["y"][tr][itr], np.ones(len(itr))
        if extra is not None:
            Xa = np.vstack([Xa, extra[0]])
            ya = np.r_[ya, extra[1]]
            wa = np.r_[wa, extra[2]]
        ioof[ite] = fit_predict(Xa, ya, X[tr][ite], wa)
    return S.tune_thresholds(lab["yc"][tr], ioof)


def run(lab, X, kind, pseudo=None):
    """Outer CV. pseudo(k, tr, te, ths) -> (Xp, yp, wp) or None."""
    n = len(lab["y"])
    oof, pred, fold = np.zeros(n), np.zeros(n, int), np.zeros(n, int)
    npseudo = []
    for k, (tr, te) in enumerate(folds(lab, kind)):
        extra = None
        if pseudo is not None:
            ths0 = inner_thresholds(lab, X, tr)
            extra = pseudo(k, tr, te, ths0)
            npseudo.append(0 if extra is None else len(extra[1]))
        Xa, ya, wa = X[tr], lab["y"][tr], np.ones(len(tr))
        if extra is not None:
            Xa, ya, wa = np.vstack([Xa, extra[0]]), np.r_[ya, extra[1]], np.r_[wa, extra[2]]
        oof[te] = fit_predict(Xa, ya, X[te], wa)
        pred[te] = np.digitize(oof[te], inner_thresholds(lab, X, tr, extra)) + 1
        fold[te] = k
    return {"oof": oof, "pred": pred, "fold": fold, "n_pseudo": npseudo}


# --------------------------------------------------------------------------
def make_pseudo(lab, U, kind, weight, transductive=False):
    xy_u = km_xy(U["lat"], U["lon"]) * 1000.0
    tree = cKDTree(xy_u)
    neigh = tree.query_ball_point(xy_u, NEIGH_M)
    rng = np.random.default_rng(S.SEED)

    def fn(k, tr, te, ths):
        if kind == "spatial":
            allowed = ~np.isin(U["ckey"], lab["ckey"][te])
        else:
            test_area = lab["area"][te][0]
            allowed = np.ones(len(U["X"]), bool) if transductive else U["area"] != test_area
        score = fit_predict(lab["X"][tr], lab["y"][tr], U["X"])
        cls = np.digitize(score, ths) + 1
        margin = np.min(np.abs(score[:, None] - np.asarray(ths)[None, :]), 1)
        agree = np.array([len(nb) >= 3 and np.all(cls[nb] == cls[i])
                          for i, nb in enumerate(neigh)])
        pick = np.flatnonzero(allowed & (margin >= MARGIN) & agree)
        if len(pick) == 0:
            return None
        # class-balanced cap: at most MAX_PSEUDO / n_classes per class
        per = MAX_PSEUDO // len(S.RQI_LABELS)
        sel = np.concatenate([rng.permutation(pick[cls[pick] == c])[:per]
                              for c in S.RQI_LABELS])
        return U["X"][sel], cls[sel].astype(float), np.full(len(sel), weight)
    return fn


def region_norm(lab, U, group, mode):
    """Features minus (and /) the mean (std) of ALL frames in the group."""
    XA = np.vstack([lab["X"], U["X"]])
    if group == "area":
        ga = np.r_[lab["area"], U["area"]]
        mu = {a: XA[ga == a].mean(0) for a in np.unique(ga)}
        sd = {a: XA[ga == a].std(0) + 1e-6 for a in np.unique(ga)}
        MU = np.stack([mu[a] for a in lab["area"]])
        SD = np.stack([sd[a] for a in lab["area"]])
    else:
        r_km = float(group[1:-2])
        P = km_xy(np.r_[lab["lat"], U["lat"]], np.r_[lab["lon"], U["lon"]])
        nb = cKDTree(P).query_ball_point(P[:len(lab["X"])], r_km)
        MU = np.stack([XA[i].mean(0) for i in nb])
        SD = np.stack([XA[i].std(0) + 1e-6 for i in nb])
    Z = lab["X"] - MU
    if mode == "white":
        Z = Z / SD
    if mode == "concat":
        Z = np.hstack([lab["X"], Z])
    return Z


# --------------------------------------------------------------------------
def report(name, lab, res, ref, kind):
    yc = lab["yc"]
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    rec2 = recall_score(yc, res["pred"], labels=[2], average=None)[0]
    b = lab["area"] == "budapest"
    mb = S.ordinal_metrics(yc[b], res["pred"][b], res["oof"][b])
    bias = {a: res["oof"][lab["area"] == a].mean() - lab["y"][lab["area"] == a].mean()
            for a in AREAS}
    d = S.paired_bootstrap_delta(yc, ref, res, lab["groups"]) if ref is not None else None
    dq = (f" | ΔQWK {d['qwk'][0]:+.3f} [{d['qwk'][1]:+.3f},{d['qwk'][2]:+.3f}]"
          f" ΔMAE {d['mae'][0]:+.3f} ΔAUC {d['bad_auc'][0]:+.3f}"
          f"{'  *' if d['qwk'][1] > 0 else ''}") if d else ""
    extra = f" pseudo/fold~{int(np.mean(res['n_pseudo']))}" if res.get("n_pseudo") else ""
    print(f"  [{kind:7s}] {name:34s} QWK={m['qwk']:.3f} MAE={m['mae']:.3f} "
          f"AUC={m['bad_auc']:.3f} rec2={rec2:.2f} | BP QWK={mb['qwk']:.3f} "
          f"AUC={mb['bad_auc']:.3f} | bias " + " ".join(
              f"{a[:4]}{v:+.2f}" for a, v in bias.items()) + dq + extra, flush=True)
    return {"name": name, "kind": kind, **{k: m[k] for k in ("qwk", "mae", "bad_auc")},
            "rec2": rec2, "bp_qwk": mb["qwk"], "bp_auc": mb["bad_auc"],
            **{f"bias_{a}": v for a, v in bias.items()},
            **({"dqwk": d["qwk"][0], "dqwk_lo": d["qwk"][1], "dqwk_hi": d["qwk"][2],
                "dmae": d["mae"][0], "dauc": d["bad_auc"][0]} if d else {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["norm", "self"], default=None)
    args = ap.parse_args()
    lab, U = load()
    print(f"labelled {len(lab['y'])} frames; unlabelled pool {len(U['X'])} frames "
          f"({pd.Series(U['area']).value_counts().to_dict()})\n")
    rows = []
    for kind in ("spatial", "loro"):
        ref = run(lab, lab["X"], kind)
        rows.append(report("champion", lab, ref, None, kind))
        if args.only in (None, "norm"):
            for group in ("area", "r1km", "r3km"):
                for mode in ("center", "white", "concat"):
                    Z = region_norm(lab, U, group, mode)
                    rows.append(report(f"norm {group} {mode}", lab,
                                       run(lab, Z, kind), ref, kind))
        if args.only in (None, "self"):
            for w in (0.3,):
                rows.append(report(f"self-train strict w={w}", lab,
                                   run(lab, lab["X"], kind,
                                       make_pseudo(lab, U, kind, w)), ref, kind))
            if kind == "loro":
                rows.append(report("self-train TRANSDUCTIVE w=0.3", lab,
                                   run(lab, lab["X"], kind,
                                       make_pseudo(lab, U, kind, 0.3, True)), ref, kind))
        print()
    out = os.path.join(CACHE, "experiments_semisup_regional"
                       + (f"_{args.only}" if args.only else "") + ".csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"-> {os.path.relpath(out, S.ROOT)}")


if __name__ == "__main__":
    main()
