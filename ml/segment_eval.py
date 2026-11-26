#!/usr/bin/env python3
"""
Segment-level evaluation: how to turn noisy per-frame RQI predictions into a
reliable ROAD-SEGMENT quality, measured honestly (spatially grouped).

One command prints every table of docs/MODEL_EXPERIMENTS.md "Era 7":

  .venv/bin/python ml/segment_eval.py                 # evaluate + print (~6 min)
  .venv/bin/python ml/segment_eval.py --write-recipe  # also (re)write ml/segment_recipe.json
  .venv/bin/python ml/segment_eval.py --length 100    # sections 5-8 for another length
  .venv/bin/python ml/segment_eval.py --age-check     # optional: image age in the local DB

What it does (nothing here ever sees a test label before predicting it):
  1. Champion out-of-fold predictions under the OFFICIAL spatial protocol
     (ml/spatial_cv.py: 1 km cells, StratifiedGroupKFold 5, seed 42, nested
     cut-points) -> ml/cache/oof_spatial_champion.csv. P(bad) = isotonic on
     the score (the artifact's approach), fitted per outer fold on that fold's
     INNER spatial OOF scores.
  2. Chains: frames ordered by capture sequence; a chain breaks at a gap
     > GAP_M, at a turn > TURN_DEG between consecutive steps, and at a 1 km
     cell border (so a chain — and every segment cut from it — lies in exactly
     one CV group and never straddles train/test).
  3. Segments: each chain is cut into round(length / L) equal pieces,
     L in {1 frame, 50, 100, 150, 200, 300 m}. Segment truth = median human
     label (half-way ties go towards the segment mean, then to the worse
     class). Every length is cut three ways (cuts shifted by 0, 1/3, 2/3 of a
     segment) so that no number hinges on where the cuts happen to fall.
  4. Aggregators per L: median / mean / trimmed-mean score, mean P(bad),
     majority vote; plus per-frame Gaussian smoothing along the chain. The
     score -> class cut-points are RE-TUNED for every aggregated score, nested:
     on the training folds' inner-OOF frame scores aggregated the same way.
  5. Length-weighted segment metrics with cell-bootstrap 95% CIs and the paired
     gain over the single frame.
  6. Confidence = clamp((1-exp(-n/n_ref)) * exp(-(iqr/spread_ref)^2)
                        * (0.5 + 0.5*min(1, margin/margin_ref)), 0, 1)
     parameters fitted (Brier score vs "segment class correct") and checked
     cross-fold: fitted on four folds' segments, tabulated on the fifth.
  7. Frame spacing: keep every 2nd/3rd/5th/10th frame and re-measure.
  8. Per-region bias before/after aggregation, and the recipe JSON (plus a
     fallback for frames that only store the integer class: mean frame class).

Reads ml/cache/{feats_v2_small.npz, dataset_v2.csv}, ml/image_coords.csv and,
read-only, ml/cache/rqi_model.joblib (the two recipe knobs that act on values
the live artifact produces — P(bad) and the integer frame class — are tuned
through its calibrator / frame cut-points). It never writes the artifact.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import trim_mean
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from save_model_v2 import (DROP_RQI5, HEADS, ROAD_PROB_MIN,  # noqa: E402
                           build_features)

ROOT = S.ROOT
CACHE = os.path.join(ROOT, "ml", "cache")
OOF_CSV = os.path.join(CACHE, "oof_spatial_champion.csv")
RECIPE_JSON = os.path.join(ROOT, "ml", "segment_recipe.json")
ARTIFACT = os.path.join(CACHE, "rqi_model.joblib")   # read-only, optional

# the live champion (ml/README.md): DINOv2-small CLS+patch-mean + SVR-RBF
CHAMPION = {"recipe": "cls+patch", "backbone": "small", "head": "svr-rbf"}

GAP_M = 40.0          # chain breaks at a larger gap between consecutive frames
TURN_DEG = 45.0       # ... and at a sharper turn between consecutive steps
NOMINAL_STEP_M = 10.0  # footprint of a frame that has no neighbour
LENGTHS = [None, 50, 100, 150, 200, 300]   # None = single frame
SIGMAS = [25, 50, 100]
TRIM = 0.2            # trimmed mean: fraction cut from EACH end
PHASES = [0.0, 1 / 3, 2 / 3]    # shifted segmentations of the same chains
SUBSAMPLE_N = [1, 2, 3, 5, 8]   # confidence: thin a segment to n frames
SUBSAMPLE_DRAWS = 2
SPACING_STEPS = [1, 2, 3, 5, 10]   # keep every k-th frame (~10 m apart)
ALTERNATIVES = [100, 150, 200]     # lengths summarised next to the recipe

# ---- the recommended recipe (picked from the nested tables this script
# ---- prints; see docs/MODEL_EXPERIMENTS.md "Era 7" for the reasoning) ----
RECOMMENDED = {"segment_length_m": 200, "aggregator": "median_score",
               "min_images": 2, "frame_spacing_m": 30,
               "high": 0.80, "medium": 0.55}

AGG_LABEL = {"median_score": "median score", "mean_score": "mean score",
             "trimmed_mean_score": f"trimmed mean ({TRIM:.0%}/side)",
             "mean_p_bad": "mean P(bad)", "majority_vote": "majority vote",
             # fallback for rows that only store the integer frame class
             "mean_class": "mean frame class"}
ALL_KINDS = list(AGG_LABEL)
KEYS = ("qwk", "mae", "exact", "off1", "bad_auc", "bad_acc")
LEVELS = ["low", "medium", "high"]


# --------------------------------------------------------------------------
# 1. champion OOF under the official spatial protocol
# --------------------------------------------------------------------------
def champion_oof():
    """Frame table with OOF score/class/P(bad) + inner-OOF matrices.

    inner[k, i]   = inner spatial OOF score of frame i when fold k is the test
                    fold (NaN if frame i is in test fold k). Used to tune
                    anything "inside the fold".
    inner_p[k, i] = the same through fold k's P(bad) calibrator (the
                    calibrator was fitted on these very scores, so the
                    training-side P(bad) is in-sample for that 1-D map; it
                    only feeds the cut-points of the mean-P(bad) aggregator).
    """
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X_all = build_features(CHAMPION["recipe"], CHAMPION["backbone"])
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X_all[keep], df[keep].reset_index(drop=True)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    coords = S.load_coords(df["image_filename"])
    groups = S.grid_cells(coords["lat"].values, coords["lon"].values)

    res = S.nested_spatial_cv(X, y, yc, groups, HEADS[CHAMPION["head"]],
                              return_inner=True)
    is_bad = (yc >= S.BAD_FROM).astype(int)
    n = len(yc)
    p_bad = np.zeros(n)
    inner = np.full((S.N_SPLITS, n), np.nan)
    inner_p = np.full((S.N_SPLITS, n), np.nan)
    for k, (tr, ioof) in enumerate(res["inner"]):
        te = res["fold"] == k
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(ioof, is_bad[tr])
        p_bad[te] = iso.predict(res["oof"][te])
        inner[k, tr] = ioof
        inner_p[k, tr] = iso.predict(ioof)

    fr = pd.DataFrame({
        "image_filename": df["image_filename"].values,
        "lat": coords["lat"].values, "lon": coords["lon"].values,
        "area": coords["area"].values, "human_rqi": yc,
        "score": res["oof"], "pred_rqi": res["pred"], "p_bad": p_bad,
        "fold": res["fold"],
    })
    fr.to_csv(OOF_CSV, index=False, float_format="%.6f")
    fr["seq"] = coords["seq"].values
    fr["coord_source"] = coords["coord_source"].values
    fr["cell"] = groups
    return fr, inner, inner_p, res["thresholds"]


# --------------------------------------------------------------------------
# 2. chains and segments
# --------------------------------------------------------------------------
def build_chains(fr):
    """Chain id, along-chain position (m) and footprint (m) for every frame.

    Frames are ordered by (coord_source, seq): the filename index of the
    collection track, or the DB row id of the sv_* frames. A new chain starts
    when the source changes, the step is longer than GAP_M, the 1 km CV cell
    changes, or the heading turns by more than TURN_DEG between two steps.
    footprint = the stretch of road a frame stands for (half the distance to
    each neighbour in its chain); it is the length weight of every metric.
    """
    order = np.lexsort((fr["seq"].values, fr["coord_source"].values))
    lat, lon = fr["lat"].values[order], fr["lon"].values[order]
    x = lon * 111_320.0 * np.cos(np.radians(47.0))
    y = lat * 111_320.0
    dx, dy = np.diff(x), np.diff(y)
    step = np.hypot(dx, dy)
    brg = np.degrees(np.arctan2(dx, dy))
    src = fr["coord_source"].values[order]
    cell = fr["cell"].values[order]

    brk = (src[1:] != src[:-1]) | (step > GAP_M) | (cell[1:] != cell[:-1])
    turn = np.abs((np.diff(brg) + 180.0) % 360.0 - 180.0)
    # turn[j] = heading change at frame j+1 (between steps j and j+1); the
    # corner frame stays with the street it came from, the next one starts anew
    sharp = (turn > TURN_DEG) & (step[:-1] > 3.0) & (step[1:] > 3.0) & ~brk[:-1]
    brk[1:] |= sharp

    chain_o = np.concatenate([[0], np.cumsum(brk)])
    n = len(order)
    pos_o, fp_o = np.zeros(n), np.zeros(n)
    for c in np.unique(chain_o):
        i = np.flatnonzero(chain_o == c)          # contiguous in order
        if len(i) == 1:
            fp_o[i] = NOMINAL_STEP_M
            continue
        d = step[i[:-1]]
        pos_o[i] = np.concatenate([[0.0], np.cumsum(d)])
        before = np.concatenate([[d[0]], d])
        after = np.concatenate([d, [d[-1]]])
        fp_o[i] = (before + after) / 2.0
    chain, pos, fp = (np.zeros(n, dtype=int), np.zeros(n), np.zeros(n))
    chain[order], pos[order], fp[order] = chain_o, pos_o, fp_o
    rank = np.zeros(n, dtype=int)
    rank[order] = np.arange(n)
    return chain, pos, fp, rank


def cut_segments(chain, fp, rank, length_m, phase=0.0):
    """Segment id per frame: every chain is cut into round(len / L) equal
    pieces (>= 1). length_m=None -> every frame is its own segment.

    phase (0..1) shifts every cut by that fraction of a piece: a different but
    equally valid segmentation of the same chains, used to see how much a
    number depends on where the cuts happen to fall. The short leftover at one
    chain end is merged into its neighbour, so the piece count stays the same.
    """
    n = len(chain)
    if length_m is None:
        return np.arange(n)
    seg = np.zeros(n, dtype=int)
    nxt = 0
    for c in np.unique(chain):
        i = np.flatnonzero(chain == c)
        i = i[np.argsort(rank[i])]
        total = fp[i].sum()
        k = max(1, int(np.floor(total / length_m + 0.5)))
        mid = np.cumsum(fp[i]) - fp[i] / 2.0
        if phase == 0:
            piece = np.floor(mid / (total / k)).astype(int)
        else:
            piece = np.floor(mid / (total / k) - phase).astype(int) + 1
            if phase <= 0.5:      # short first piece -> merge into the next
                piece -= 1
        seg[i] = nxt + np.clip(piece, 0, k - 1)
        nxt += k
    # ids must be 0..S-1 with no holes: tables are indexed by segment id
    return np.unique(seg, return_inverse=True)[1].ravel()


def median_class(labels):
    """Median human label as an integer class. A half-way median (even count,
    two different middle labels) goes towards the segment mean; an exact tie
    goes to the worse (higher) class."""
    m = float(np.median(labels))
    if m == int(m):
        return int(m)
    return int(np.ceil(m)) if labels.mean() >= m else int(np.floor(m))


def segment_table(seg, fr, fp):
    """One row per segment: truth, length, frame count, cell, fold, spread."""
    g = pd.DataFrame({"seg": seg, "lab": fr["human_rqi"].values, "fp": fp,
                      "cell": fr["cell"].values, "fold": fr["fold"].values,
                      "area": fr["area"].values}).groupby("seg", sort=True)
    # a segment never straddles a CV cell, hence never train/test
    assert (g["fold"].nunique() == 1).all() and (g["cell"].nunique() == 1).all()
    t = pd.DataFrame({
        "gt": g["lab"].apply(lambda s: median_class(s.values)),
        "length": g["fp"].sum(), "n": g.size(),
        "cell": g["cell"].first(), "fold": g["fold"].first(),
        "area": g["area"].first(),
        "lab_mean": g["lab"].mean(),
        "lab_range": g["lab"].max() - g["lab"].min(),
        "mixed": g["lab"].apply(lambda s: (s.min() <= 2) & (s.max() >= 3)),
    })
    dev = pd.Series(np.abs(fr["human_rqi"].values - t["gt"].values[seg])
                    ).groupby(seg, sort=True)
    t["purity"] = dev.apply(lambda s: (s == 0).mean()).values
    t["mad"] = dev.mean().values
    return t


# --------------------------------------------------------------------------
# 3. aggregators + nested cut-points
# --------------------------------------------------------------------------
def aggregate(v, seg, kind):
    """Per-segment aggregate of a frame vector (NaN-only segments stay NaN)."""
    g = pd.Series(v).groupby(seg, sort=True)
    if kind == "median_score":
        return g.median().values
    if kind in ("mean_score", "mean_p_bad", "mean_class"):
        return g.mean().values
    if kind == "trimmed_mean_score":
        return g.agg(lambda s: trim_mean(s.values, TRIM)).values
    raise ValueError(kind)


def majority(classes, seg):
    """Most frequent frame class; ties -> the tied class nearest the mean class."""
    def vote(s):
        c = np.bincount(s.values, minlength=5)
        best = np.flatnonzero(c == c.max())
        return int(best[np.argmin(np.abs(best - s.mean()))])
    return pd.Series(classes).groupby(seg, sort=True).agg(vote).values


def gaussian_smooth(v, chain, pos, sigma):
    """Per-frame Gaussian-weighted mean of v along its own chain."""
    out = np.full(len(v), np.nan)
    for c in np.unique(chain):
        i = np.flatnonzero(chain == c)
        if np.isnan(v[i]).any():
            continue
        w = np.exp(-0.5 * ((pos[i][:, None] - pos[i][None, :]) / sigma) ** 2)
        out[i] = (w @ v[i]) / w.sum(1)
    return out


def nested_cutpoints(parts):
    """Cut-points tuned inside the fold. parts = one (truth, weight, fold,
    agg_inner) tuple per segmentation, agg_inner[k] = the units' aggregated
    inner-OOF score for outer fold k. For test fold k the cut-points are tuned
    on the TRAINING units only (pooled over the segmentations)."""
    ths = []
    for k in range(S.N_SPLITS):
        gt = np.concatenate([g[f != k] for g, w, f, a in parts])
        ww = np.concatenate([w[f != k] for g, w, f, a in parts])
        aa = np.concatenate([a[k][f != k] for g, w, f, a in parts])
        ths.append(S.tune_thresholds(gt, aa, sample_weight=ww))
    return ths


def apply_cutpoints(score, fold, ths):
    pred = np.zeros(len(score), dtype=int)
    for k in range(S.N_SPLITS):
        pred[fold == k] = np.digitize(score[fold == k], ths[k]) + 1
    return pred


def best_p_threshold(is_bad, p, w, tol=0.005):
    """P(bad) threshold for the good/bad flag: the middle of the plateau
    around the best length-weighted accuracy (everything within ``tol`` of
    it counts as the plateau — steadier than the single best grid point)."""
    grid = np.linspace(0.10, 0.90, 81)
    acc = np.array([np.average((p >= t).astype(int) == is_bad, weights=w)
                    for t in grid])
    top = int(np.argmax(acc))
    lo = hi = top
    while lo > 0 and acc[lo - 1] >= acc[top] - tol:
        lo -= 1
    while hi < len(grid) - 1 and acc[hi + 1] >= acc[top] - tol:
        hi += 1
    return float(grid[(lo + hi) // 2])


def evaluate(fr, inner, inner_p, segsets, kind, fixed_ths=None,
             inner_cls=None):
    """One aggregator on one segment length. segsets = [(seg, table), ...],
    one per segmentation (PHASES). Returns the per-fold nested cut-points and,
    per segmentation, the predicted class / score / metrics.
    fixed_ths: per-fold cut-points to apply as they are (no re-tuning).
    inner_cls: inner-OOF frame classes (for kind="mean_class")."""
    tabs = [(st["gt"].values, st["length"].values, st["fold"].values)
            for _, st in segsets]
    ths, flags = None, [None] * len(segsets)
    if kind == "majority_vote":
        scores = [pd.Series(fr["pred_rqi"].values.astype(float)).groupby(
            seg, sort=True).mean().values for seg, _ in segsets]
        preds = [majority(fr["pred_rqi"].values, seg) for seg, _ in segsets]
    else:
        src, src_in = {
            "mean_p_bad": (fr["p_bad"].values, inner_p),
            "mean_class": (fr["pred_rqi"].values.astype(float), inner_cls),
        }.get(kind, (fr["score"].values, inner))
        scores = [aggregate(src, seg, kind) for seg, _ in segsets]
        # 4 classes from mean P(bad): cut-points are searched on 1 + 3*p
        lift = (lambda a: 1 + 3 * a) if kind == "mean_p_bad" else (lambda a: a)
        if fixed_ths is not None:
            ths = fixed_ths
        else:
            agg_in = [[aggregate(src_in[k], seg, kind)
                       for k in range(S.N_SPLITS)] for seg, _ in segsets]
            ths = nested_cutpoints([(g, w, f, [lift(a) for a in ai])
                                    for (g, w, f), ai in zip(tabs, agg_in)])
        preds = [apply_cutpoints(lift(sc), f, ths)
                 for sc, (g, w, f) in zip(scores, tabs)]
        if kind == "mean_p_bad":   # good/bad flag: nested P(bad) threshold
            flags = [np.zeros(len(g), dtype=int) for g, w, f in tabs]
            for k in range(S.N_SPLITS):
                t = best_p_threshold(
                    np.concatenate([(g[f != k] >= S.BAD_FROM).astype(int)
                                    for g, w, f in tabs]),
                    np.concatenate([ai[k][f != k]
                                    for (g, w, f), ai in zip(tabs, agg_in)]),
                    np.concatenate([w[f != k] for g, w, f in tabs]))
                for fl, sc, (g, w, f) in zip(flags, scores, tabs):
                    fl[f == k] = sc[f == k] >= t
    runs = [{"pred": p, "score": sc, "bad_flag": fl,
             "m": wmetrics(g, p, sc, w, fl)}
            for p, sc, fl, (g, w, f) in zip(preds, scores, flags, tabs)]
    return {"ths": ths, "runs": runs}


# --------------------------------------------------------------------------
# 4. metrics + cell bootstrap
# --------------------------------------------------------------------------
def wmetrics(gt, pred, score, w, bad_flag=None):
    m = S.ordinal_metrics(gt, pred, score, sample_weight=w)
    if bad_flag is not None:
        m["bad_acc"] = float(np.average(
            bad_flag == (gt >= S.BAD_FROM).astype(int), weights=w))
    return m


def boot_matrix(cell, gt, pred, score, w, picks, bad_flag=None):
    """Metrics on every cell-resample (rows aligned across configs because
    all use the same ``picks`` -> paired differences are valid)."""
    by_cell = {c: np.flatnonzero(cell == c) for c in np.unique(cell)}
    empty = np.zeros(0, dtype=int)
    out = np.zeros((len(picks), len(KEYS)))
    for b, pick in enumerate(picks):
        idx = np.concatenate([by_cell.get(c, empty) for c in pick])
        m = wmetrics(gt[idx], pred[idx], score[idx], w[idx],
                     None if bad_flag is None else bad_flag[idx])
        out[b] = [m[k] for k in KEYS]
    return out


def ci(a):
    return np.nanpercentile(a, 2.5, axis=0), np.nanpercentile(a, 97.5, axis=0)


# --------------------------------------------------------------------------
# 5. confidence
# --------------------------------------------------------------------------
def confidence(n, iqr, margin, n_ref, spread_ref, margin_ref):
    """The functional form the backend implements (parameters tuned below)."""
    c = ((1.0 - np.exp(-np.asarray(n, float) / n_ref))
         * np.exp(-(np.asarray(iqr, float) / spread_ref) ** 2)
         * (0.5 + 0.5 * np.minimum(1.0, np.asarray(margin, float) / margin_ref)))
    return np.clip(c, 0.0, 1.0)


def iqr_of(v):
    """Interquartile range, linear-interpolated percentiles (numpy default);
    0 for a single value. The backend must use the same definition."""
    return float(np.subtract(*np.percentile(v, [75, 25])))


CONF_GRID = {
    "n_ref": [0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0],
    "spread_ref": [0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0],
    "margin_ref": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5],
}
BRIER_TOL = 0.001


def fit_confidence(rows):
    """Grid-search the three parameters: minimise the length-weighted Brier
    score of confidence vs "segment class is correct".

    Fits within BRIER_TOL of the best are indistinguishable, so among them the
    most cautious one wins: the largest n_ref (few frames -> less sure), then
    the smallest spread_ref (scattered scores -> less sure), then the best
    margin_ref. The labelled runs are dense and curated; this keeps the two
    terms they can hardly test (very few frames, wildly scattered scores) from
    being switched off entirely.
    Returns (chosen params, its Brier, unconstrained best params, its Brier).
    """
    n, iqr, mg = rows["n"].values, rows["iqr"].values, rows["margin"].values
    y, w = rows["correct"].values, rows["w"].values
    cand = []
    for a in CONF_GRID["n_ref"]:
        for b in CONF_GRID["spread_ref"]:
            for c in CONF_GRID["margin_ref"]:
                conf = confidence(n, iqr, mg, a, b, c)
                cand.append((float(np.average((conf - y) ** 2, weights=w)),
                             a, b, c))
    best = min(cand)
    ok = [x for x in cand if x[0] <= best[0] + BRIER_TOL]
    a = max(x[1] for x in ok)
    ok = [x for x in ok if x[1] == a]
    b = min(x[2] for x in ok)
    pick = min(x for x in ok if x[2] == b)
    return pick[1:], pick[0], best[1:], best[0]


def aggregate_one(v, kind):
    if kind == "median_score":
        return float(np.median(v))
    if kind == "trimmed_mean_score":
        return float(trim_mean(v, TRIM))
    return float(np.mean(v))


def segment_row(v, th, gt, lab_mean, kind):
    """n / iqr / margin / class / errors of one segment from frame scores v."""
    a = aggregate_one(v, kind)
    pred = int(np.digitize(a, th) + 1)
    return {"n": len(v), "iqr": iqr_of(v), "agg": a,
            "margin": float(np.min(np.abs(np.asarray(th) - a))),
            "pred": pred, "gt": gt, "correct": float(pred == gt),
            "err": abs(pred - gt),
            "bad_wrong": float((pred >= S.BAD_FROM) != (gt >= S.BAD_FROM)),
            "score_err": abs(a - lab_mean)}


def confidence_rows(segsets, fr, kind, ths_by_fold, rng):
    """Evaluation rows for the confidence fit: every segment as measured
    (all its frames) plus thinned copies with only n frames (SUBSAMPLE_N,
    random subsets) — the labelled runs are dense (~10 m), production
    segments will often hold fewer images. Truth stays the segment's full
    human median; cut-points are the segment's own fold's (nested). Rows of
    all segmentations are pooled (each weighted 1/len(segsets))."""
    score = fr["score"].values
    rows = []
    for ph, (seg, st) in enumerate(segsets):
        frames = pd.Series(np.arange(len(seg))).groupby(seg, sort=True).apply(
            lambda s: s.values)
        for s, idx in enumerate(frames):
            fold = int(st["fold"].values[s])
            th = ths_by_fold[fold]
            gt = int(st["gt"].values[s])
            lab_mean = float(st["lab_mean"].values[s])
            length = float(st["length"].values[s]) / len(segsets)
            variants = [("all", idx, 1.0)]
            for k in SUBSAMPLE_N:
                if k < len(idx):
                    variants += [(str(k), rng.choice(idx, k, replace=False),
                                  1.0 / SUBSAMPLE_DRAWS)
                                 for _ in range(SUBSAMPLE_DRAWS)]
            for tag, ii, wmul in variants:
                r = segment_row(score[ii], th, gt, lab_mean, kind)
                r.update(phase=ph, seg=s, variant=tag, fold=fold,
                         w=length * wmul, area=st["area"].values[s])
                rows.append(r)
    return pd.DataFrame(rows)


def calib_table(rows, conf, edges, names=None):
    out = []
    for j, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        s = (conf >= lo) & ((conf < hi) if hi < 1 else (conf <= hi))
        if s.sum() == 0:
            continue
        w = rows["w"].values[s]
        avg = lambda v: float(np.average(v[s], weights=w))  # noqa: E731
        out.append({
            "level" if names else "confidence": names[j] if names
            else f"{lo:.2f}–{hi:.2f}",
            "rows": int(s.sum()),
            "share": float(w.sum() / rows["w"].sum()),
            "mean conf": float(np.average(conf[s], weights=w)),
            "P(correct)": avg(rows["correct"].values),
            "P(|err|>=1)": 1.0 - avg(rows["correct"].values),
            "P(|err|>=2)": avg((rows["err"].values >= 2).astype(float)),
            "P(good/bad wrong)": avg(rows["bad_wrong"].values),
            "class MAE": avg(rows["err"].values.astype(float)),
        })
    return pd.DataFrame(out)


def confidence_study(segsets, fr, kind, ths_by_fold):
    """Rows + cross-fold confidences + final parameters for one recipe."""
    crow = confidence_rows(segsets, fr, kind, ths_by_fold,
                           np.random.default_rng(S.SEED))
    conf_cv = np.zeros(len(crow))
    fold_par = []
    for k in range(S.N_SPLITS):
        te = crow["fold"].values == k
        par, _, _, _ = fit_confidence(crow[~te])
        fold_par.append(par)
        conf_cv[te] = confidence(crow["n"].values[te], crow["iqr"].values[te],
                                 crow["margin"].values[te], *par)
    par, brier, par_free, brier_free = fit_confidence(crow)
    return {"rows": crow, "conf_cv": conf_cv, "fold_par": fold_par,
            "par": par, "brier": brier, "par_free": par_free,
            "brier_free": brier_free,
            "conf": confidence(crow["n"].values, crow["iqr"].values,
                               crow["margin"].values, *par),
            "full": crow["variant"].values == "all"}


def final_cutpoints(fr, segsets, kind):
    """Deployed cut-points: tuned on ALL spatial-OOF segments (the three
    segmentations pooled), with the chosen aggregator."""
    return S.tune_thresholds(
        np.concatenate([st["gt"].values for _, st in segsets]),
        np.concatenate([aggregate(fr["score"].values, seg, kind)
                        for seg, _ in segsets]),
        sample_weight=np.concatenate([st["length"].values for _, st in segsets]))


# --------------------------------------------------------------------------
# 6. frame spacing (how dense must the frames be?)
# --------------------------------------------------------------------------
def spacing_eval(fr, chain, rank, segsets, kind, ths_by_fold, par, levels,
                 picks=None):
    """Keep every k-th frame of each chain (k = SPACING_STEPS, every offset)
    and re-evaluate the recipe: same segments, same truth (the full human
    median), same cut-points; only the frames used shrink. Point estimates
    are the mean over the segmentations and the k offsets; the bootstrap
    matrices (if ``picks``) are for the unshifted segmentation."""
    score = fr["score"].values
    in_chain = (pd.Series(rank).groupby(chain).rank(method="first")
                .astype(int).values - 1)
    med_t, hi_t = levels
    out, boots = [], {}
    for step in SPACING_STEPS:
        acc, bsum = [], 0.0
        for ph, (seg, st) in enumerate(segsets):
            gt, w = st["gt"].values, st["length"].values
            cell, fold = st["cell"].values, st["fold"].values
            lab_mean = st["lab_mean"].values
            for offset in range(step):
                keep = np.flatnonzero(in_chain % step == offset)
                rows = []
                for s, ii in pd.Series(keep).groupby(seg[keep], sort=True):
                    r = segment_row(score[ii.values], ths_by_fold[int(fold[s])],
                                    int(gt[s]), float(lab_mean[s]), kind)
                    r.update(seg=s, w=float(w[s]))
                    rows.append(r)
                d = pd.DataFrame(rows)
                dw, dn = d["w"].values, d["n"].values
                conf = confidence(dn, d["iqr"].values, d["margin"].values, *par)
                m = wmetrics(d["gt"].values, d["pred"].values, d["agg"].values, dw)
                if picks is not None and ph == 0:
                    bsum = bsum + boot_matrix(
                        cell[d["seg"].values], d["gt"].values, d["pred"].values,
                        d["agg"].values, dw, picks)
                lvl = np.where(conf >= hi_t, 2, np.where(conf >= med_t, 1, 0))
                row = {k: m[k] for k in KEYS}
                if ph == 0:
                    row.update({f"{k}_0": m[k] for k in KEYS})
                row.update({
                    "frames/seg": float(np.average(dn, weights=dw)),
                    "covered": dw.sum() / w.sum(),
                    "n>=min_images":
                        dw[dn >= RECOMMENDED["min_images"]].sum() / w.sum(),
                    "mean conf": float(np.average(conf, weights=dw)),
                })
                for j, name in enumerate(LEVELS):
                    sel = lvl == j
                    row[f"{name} share"] = dw[sel].sum() / dw.sum()
                    row[f"P(correct|{name})"] = (
                        float(np.average(d["correct"].values[sel],
                                         weights=dw[sel]))
                        if sel.any() else np.nan)
                    row[f"P(good/bad wrong|{name})"] = (
                        float(np.average(d["bad_wrong"].values[sel],
                                         weights=dw[sel]))
                        if sel.any() else np.nan)
                acc.append(row)
        mean = pd.DataFrame(acc).mean().to_dict()
        mean["step"] = step
        out.append(mean)
        boots[step] = bsum / step
    return pd.DataFrame(out), boots


# --------------------------------------------------------------------------
# 7. image age (optional, needs the local Postgres)
# --------------------------------------------------------------------------
def age_check():
    """Can an "old image" penalty be learned from our data? Read-only look at
    street_view_images: how old the frames are, and — for spots that were
    captured on two different dates — whether the model's class differs more
    when the dates are further apart. (Labels cannot answer this: a label
    describes the image, not today's road.)"""
    import psycopg2

    from build_coords import DB_URL
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*), count(capture_date) "
                        "FROM street_view_images")
            total, dated = cur.fetchone()
            cur.execute("SELECT latitude, longitude, heading, capture_date, "
                        "dino_rqi_score FROM street_view_images WHERE "
                        "capture_date IS NOT NULL AND dino_rqi_score IS NOT NULL")
            df = pd.DataFrame(cur.fetchall(),
                              columns=["lat", "lon", "heading", "date", "cls"])
    except Exception as e:  # noqa: BLE001 - optional section, any DB problem
        print(f"   image-age check skipped (DB not reachable: {e})")
        return 2
    rule(f"Image age: capture_date is set on {dated} of {total} frames")
    if df.empty:
        print("   no frame has both a capture date and a model class")
        return 0
    df["t"] = pd.to_datetime(df["date"])
    age = (pd.Timestamp.today() - df["t"]).dt.days / 365.25
    print("   age today, years (5 / 50 / 95 / 99% quantile): "
          + " / ".join(f"{q:.1f}" for q in np.percentile(age, [5, 50, 95, 99]))
          + f"; older than 3 y: {(age > 3).mean():.1%}, than 5 y: "
          f"{(age > 5).mean():.1%}")
    df["kx"] = (df["lon"] * 111_320.0 * np.cos(np.radians(47.0)) / 15).round()
    df["ky"] = (df["lat"] * 111_320.0 / 15).round()
    pairs = []
    for _, g in df.groupby(["kx", "ky"]):
        if g["t"].nunique() < 2:
            continue
        a = g.groupby("t").agg(c=("cls", "mean"), h=("heading", "mean")).sort_index()
        for i in range(len(a) - 1):
            for j in range(i + 1, len(a)):
                dh = abs((a["h"].iloc[j] - a["h"].iloc[i] + 180) % 360 - 180)
                if min(dh, 180 - dh) <= 30:      # same street, either direction
                    pairs.append(((a.index[j] - a.index[i]).days / 365.25,
                                  a["c"].iloc[j] - a["c"].iloc[i]))
    p = pd.DataFrame(pairs, columns=["gap", "d"])
    print(f"   {len(p)} pairs of captures of the same spot (15 m, same street "
          "direction) on different dates; model class of the later minus the "
          "earlier capture:")
    if len(p):
        t = p.groupby(pd.cut(p["gap"], [0, 1, 2, 4, 30]), observed=True)["d"].agg(
            pairs="size", mean_drift="mean",
            differ_by_1_or_more=lambda v: (v.abs() >= 1).mean()).reset_index()
        t = t.rename(columns={"gap": "years apart"})
        t["years apart"] = t["years apart"].astype(str)
        print_df(t)
    return 0


# --------------------------------------------------------------------------
# printing helpers
# --------------------------------------------------------------------------
def lname(length_m):
    return "1 frame" if length_m is None else f"{length_m} m"


def fmt_ci(v, lo, hi, d=3):
    return f"{v:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def fmt_d(v, lo, hi, d=3):
    return f"{v:+.{d}f} [{lo:+.{d}f}, {hi:+.{d}f}]"


def fmt_th(th):
    return "[" + ", ".join(f"{t:.2f}" for t in th) + "]"


def print_df(df, floatfmt="%.3f"):
    print(df.to_string(index=False, float_format=lambda x: floatfmt % x))
    print()


def rule(title):
    print("=" * 110)
    print(title)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--write-recipe", action="store_true",
                    help=f"write {os.path.relpath(RECIPE_JSON, ROOT)}")
    ap.add_argument("--length", type=int, choices=LENGTHS[1:],
                    help="explore another segment length in sections 5-8 "
                         "(default: the recommended one)")
    ap.add_argument("--aggregator", choices=["median_score", "mean_score",
                                             "trimmed_mean_score"],
                    help="explore another aggregator in sections 5-8")
    ap.add_argument("--age-check", action="store_true",
                    help="only run the optional image-age look at the local "
                         "Postgres (docker compose up -d db) and exit")
    args = ap.parse_args()
    if args.age_check:
        return age_check()
    if args.length:
        RECOMMENDED["segment_length_m"] = args.length
    if args.aggregator:
        RECOMMENDED["aggregator"] = args.aggregator
    if (args.length or args.aggregator) and args.write_recipe:
        ap.error("--write-recipe writes the RECOMMENDED recipe only; change "
                 "RECOMMENDED in the script to recommend something else")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    Lr, kr = RECOMMENDED["segment_length_m"], RECOMMENDED["aggregator"]
    hi_t, med_t = RECOMMENDED["high"], RECOMMENDED["medium"]
    lv_edges = np.array([0, med_t, hi_t, 1.0])

    # ---------------- 1. OOF ----------------
    fr, inner, inner_p, frame_ths = champion_oof()
    yc = fr["human_rqi"].values
    off = S.ordinal_metrics(yc, fr["pred_rqi"].values, fr["score"].values)
    rule("1) Champion OOF, official spatial protocol "
         f"-> {os.path.relpath(OOF_CSV, ROOT)}")
    print(f"   n={off['n']} frames, {fr['cell'].nunique()} cells | per-frame, "
          f"UNWEIGHTED (must match the gate): QWK={off['qwk']:.3f} "
          f"MAE={off['mae']:.3f} exact={off['exact']:.3f} "
          f"±1={off['off1']:.3f} bad-AUC={off['bad_auc']:.3f} "
          f"bad-acc={off['bad_acc']:.3f}")
    isb = (yc >= S.BAD_FROM).astype(int)
    print(f"   P(bad) (isotonic, fitted inside folds): Brier="
          f"{np.mean((fr['p_bad'].values - isb) ** 2):.3f}, "
          f"mean P={fr['p_bad'].mean():.3f} vs bad share {isb.mean():.3f}\n")

    # ---------------- 2. chains + segments ----------------
    chain, pos, fp, rank = build_chains(fr)
    cl = pd.Series(fp).groupby(chain).sum()
    cn = pd.Series(fp).groupby(chain).size()
    rule(f"2) Chains: {len(cl)} chains from {len(fr)} frames (break: gap > "
         f"{GAP_M:.0f} m, turn > {TURN_DEG:.0f}°, 1 km cell border); total "
         f"{cl.sum() / 1000:.1f} km")
    print(f"   frame spacing median {np.median(fp):.1f} m; frames/chain median "
          f"{cn.median():.0f}; {int((cn == 1).sum())} isolated frames; share of "
          "the total length in chains of < 50 m: "
          f"{cl[cl < 50].sum() / cl.sum():.1%}, 50–200 m: "
          f"{cl[(cl >= 50) & (cl < 200)].sum() / cl.sum():.1%}, 200–500 m: "
          f"{cl[(cl >= 200) & (cl < 500)].sum() / cl.sum():.1%}, >= 500 m: "
          f"{cl[cl >= 500].sum() / cl.sum():.1%}\n")

    segsets = {None: [(np.arange(len(fr)),
                       segment_table(np.arange(len(fr)), fr, fp))]}
    for L in LENGTHS[1:]:
        segsets[L] = []
        for ph in PHASES:
            seg = cut_segments(chain, fp, rank, L, ph)
            segsets[L].append((seg, segment_table(seg, fr, fp)))
    rows = []
    for L in LENGTHS:
        st = segsets[L][0][1]
        w = st["length"].values
        gtc = np.bincount(st["gt"].values, weights=w, minlength=5)[1:5] / w.sum()
        rows.append({
            "L": lname(L), "segments": len(st),
            "frames/seg": np.average(st["n"], weights=w),
            "length m": np.average(st["length"], weights=w),
            "all labels identical": np.average(st["lab_range"] == 0, weights=w),
            "label range >= 2": np.average(st["lab_range"] >= 2, weights=w),
            "good+bad mixed": np.average(st["mixed"], weights=w),
            "frames == seg truth": np.average(st["purity"], weights=w),
            "frame MAE vs seg truth": np.average(st["mad"], weights=w),
            "truth 1/2/3/4 %": "/".join(f"{100 * x:.0f}" for x in gtc),
        })
    print("   How homogeneous are real segments? HUMAN labels inside a segment "
          "(length-weighted; frames/seg and length = what a metre of road sits in):")
    print_df(pd.DataFrame(rows))

    # why averaging frames buys less than sqrt(n): errors of neighbours agree
    resid = fr["score"].values - yc
    o = np.lexsort((rank, chain))
    r_o, c_o = resid[o], chain[o]
    lags = []
    for lag in (1, 2, 3, 5, 10, 20):
        same = c_o[lag:] == c_o[:-lag]
        lags.append({"lag frames": lag, "≈ m": lag * 10, "pairs": int(same.sum()),
                     "error correlation": np.corrcoef(r_o[lag:][same],
                                                      r_o[:-lag][same])[0, 1]})
    print("   Model error (score − human label) of two frames of the same "
          "chain, by distance:")
    print_df(pd.DataFrame(lags))
    rows = []
    for L in LENGTHS[1:]:
        g = pd.Series(resid).groupby(segsets[L][0][0])
        shared = np.average((g.transform("mean") - resid.mean()) ** 2, weights=fp)
        rows.append({"L": lname(L),
                     "error variance shared by the whole segment":
                         shared / np.average((resid - resid.mean()) ** 2, weights=fp)})
    print("   Share of the frame-error variance that is COMMON to all frames "
          "of a segment (aggregation cannot remove it):")
    print_df(pd.DataFrame(rows))

    # ---------------- 3+4. aggregators, nested cut-points, metrics ----------
    rng = np.random.default_rng(S.SEED)
    cells = np.unique(fr["cell"].values)
    picks = rng.choice(cells, size=(args.n_boot, len(cells)), replace=True)

    def boot_of(L, run):
        st = segsets[L][0][1]
        return boot_matrix(st["cell"].values, st["gt"].values, run["pred"],
                           run["score"], st["length"].values, picks,
                           run["bad_flag"])

    # inner-OOF frame classes: fold k's own frame cut-points on its inner scores
    inner_cls = np.stack([np.where(np.isnan(inner[k]), np.nan,
                                   np.digitize(inner[k], frame_ths[k]) + 1.0)
                          for k in range(S.N_SPLITS)])
    results = {(None, "median_score"):
               evaluate(fr, inner, inner_p, segsets[None], "median_score")}
    for L in LENGTHS[1:]:
        for kind in ALL_KINDS:
            results[(L, kind)] = evaluate(fr, inner, inner_p, segsets[L], kind,
                                          inner_cls=inner_cls)
    for key, r in results.items():
        r["boot"] = boot_of(key[0], r["runs"][0])
    base = results[(None, "median_score")]
    base_m, base_boot = base["runs"][0]["m"], base["boot"]

    rule("3+4) Segment-level metrics, length-weighted; cut-points re-tuned per "
         "aggregator INSIDE the spatial folds")
    print(f"     [..] = 95% CI, cell bootstrap ({args.n_boot} resamples of the "
          f"{len(cells)} cells); Δ = paired gain vs the single frame;")
    print(f"     'shifted' = mean ± sd over {len(PHASES)} segmentations of the "
          "same chains (cuts moved by 0, 1/3, 2/3 of a segment); the main "
          "columns are the unshifted one\n")
    rows = []
    for (L, kind), r in results.items():
        lo, hi = ci(r["boot"])
        dlo, dhi = ci(r["boot"] - base_boot)
        m = r["runs"][0]["m"]
        row = {"L": lname(L),
               "aggregator": "(single frame)" if L is None else AGG_LABEL[kind],
               "segs": len(r["runs"][0]["pred"]),
               "QWK": fmt_ci(m["qwk"], lo[0], hi[0]),
               "MAE": fmt_ci(m["mae"], lo[1], hi[1]),
               "exact": f"{m['exact']:.3f}", "±1": f"{m['off1']:.3f}",
               "bad AUC": fmt_ci(m["bad_auc"], lo[4], hi[4]),
               "bad acc": f"{m['bad_acc']:.3f}",
               "ΔQWK": fmt_d(m["qwk"] - base_m["qwk"], dlo[0], dhi[0]),
               "ΔMAE": fmt_d(m["mae"] - base_m["mae"], dlo[1], dhi[1]),
               "ΔAUC": fmt_d(m["bad_auc"] - base_m["bad_auc"], dlo[4], dhi[4])}
        sh = pd.DataFrame([x["m"] for x in r["runs"]])
        r["shifted"] = sh.mean().to_dict()
        row["QWK shifted"] = ("–" if L is None else
                              f"{sh['qwk'].mean():.3f} ± {sh['qwk'].std(ddof=0):.3f}")
        rows.append(row)
    print_df(pd.DataFrame(rows))

    print(f"   Mean over the {len(PHASES)} segmentations — the steadier read "
          "of each cell: QWK / MAE / exact / bad AUC / bad acc")
    piv = pd.DataFrame([
        {"aggregator": AGG_LABEL[kind], "L": lname(L),
         "v": " / ".join(f"{r['shifted'][k]:.3f}"
                         for k in ("qwk", "mae", "exact", "bad_auc", "bad_acc"))}
        for (L, kind), r in results.items() if L is not None])
    print(piv.pivot(index="aggregator", columns="L", values="v")
          .reindex(index=[AGG_LABEL[k] for k in ALL_KINDS],
                   columns=[lname(L) for L in LENGTHS[1:]]).to_string())
    print("   single frame: " + " / ".join(
        f"{base_m[k]:.3f}" for k in ("qwk", "mae", "exact", "bad_auc", "bad_acc"))
        + "\n")

    # does re-tuning the cut-points for the aggregated score pay off?
    print(f"   Re-tuned cut-points vs the single-frame cut-points applied to the "
          f"aggregated score ({AGG_LABEL[kr]}; mean of the "
          f"{len(PHASES)} segmentations):")
    rows = []
    for L in LENGTHS[1:]:
        fx = evaluate(fr, inner, inner_p, segsets[L], kr, fixed_ths=frame_ths)
        b = pd.DataFrame([x["m"] for x in fx["runs"]]).mean()
        a = results[(L, kr)]["shifted"]
        rows.append({"L": lname(L),
                     "QWK re-tuned": a["qwk"], "QWK frame cut-points": b["qwk"],
                     "MAE re-tuned": a["mae"], "MAE frame cut-points": b["mae"],
                     "bad acc re-tuned": a["bad_acc"],
                     "bad acc frame cut-points": b["bad_acc"]})
    print_df(pd.DataFrame(rows))

    # confusion matrix of the recommended recipe
    rec = results[(Lr, kr)]
    seg_r, st_r = segsets[Lr][0]
    run_r = rec["runs"][0]
    print(f"   Confusion of {lname(Lr)} + {AGG_LABEL[kr]}, in km of road; "
          "rows = segment truth, cols = predicted:")
    cm = pd.crosstab(st_r["gt"].values, run_r["pred"], st_r["length"].values,
                     aggfunc="sum").reindex(index=S.RQI_LABELS,
                                            columns=S.RQI_LABELS).fillna(0) / 1000
    prec = np.diag(cm.values) / cm.values.sum(axis=0)
    cm["recall"] = np.diag(cm.values) / cm.values.sum(axis=1)
    cm.index.name, cm.columns.name = "truth", "pred"
    print(cm.round(2).to_string())
    print("precision " + "  ".join(f"{p:.2f}" for p in prec) + "\n")

    # frame-level view: every frame shows its segment's class
    print("   Frame-level view — every frame shows its SEGMENT's class and is "
          "judged against its OWN human label")
    print(f"   (aggregator: {AGG_LABEL[kr]}); plus per-frame Gaussian smoothing "
          "along the chain, cut-points re-tuned nested:")
    rows = []
    fold_f, cell_f = fr["fold"].values, fr["cell"].values

    def frame_row(name, pred_f, score_f):
        m = wmetrics(yc, pred_f, score_f, fp)
        b = boot_matrix(cell_f, yc, pred_f, score_f, fp, picks)
        lo, hi = ci(b)
        dlo, dhi = ci(b - base_boot)
        rows.append({"method": name,
                     "QWK": fmt_ci(m["qwk"], lo[0], hi[0]),
                     "MAE": fmt_ci(m["mae"], lo[1], hi[1]),
                     "exact": f"{m['exact']:.3f}", "±1": f"{m['off1']:.3f}",
                     "bad AUC": fmt_ci(m["bad_auc"], lo[4], hi[4]),
                     "bad acc": f"{m['bad_acc']:.3f}",
                     "ΔQWK": fmt_d(m["qwk"] - base_m["qwk"], dlo[0], dhi[0]),
                     "ΔMAE": fmt_d(m["mae"] - base_m["mae"], dlo[1], dhi[1])})

    frame_row("single frame", base["runs"][0]["pred"], base["runs"][0]["score"])
    for L in LENGTHS[1:]:
        r, seg = results[(L, kr)]["runs"][0], segsets[L][0][0]
        frame_row(f"segment {L} m", r["pred"][seg], r["score"][seg])
    for sg in SIGMAS:
        sm = gaussian_smooth(fr["score"].values, chain, pos, sg)
        sm_in = [gaussian_smooth(inner[k], chain, pos, sg)
                 for k in range(S.N_SPLITS)]
        ths_s = nested_cutpoints([(yc, fp, fold_f, sm_in)])
        frame_row(f"Gaussian σ={sg} m", apply_cutpoints(sm, fold_f, ths_s), sm)
    print_df(pd.DataFrame(rows))

    # ---------------- 5. confidence ----------------
    rule(f"5) Confidence — {lname(Lr)} + {AGG_LABEL[kr]}; conf = "
         "(1-exp(-n/n_ref)) * exp(-(iqr/spread_ref)^2) * "
         "(0.5+0.5*min(1,margin/margin_ref))")
    print(f"   rows = segments of the {len(PHASES)} segmentations pooled "
          "(shares are length-weighted)")
    cs = confidence_study(segsets[Lr], fr, kr, rec["ths"])
    crow, full = cs["rows"], cs["full"]

    def by(col, bins, sel, label):
        d = crow[sel]
        out = []
        for key, g in d.groupby(pd.cut(d[col], bins, include_lowest=True),
                                observed=True):
            out.append({label: str(key), "rows": len(g),
                        "share": g["w"].sum() / d["w"].sum(),
                        "P(correct)": np.average(g["correct"], weights=g["w"]),
                        "P(|err|>=2)": np.average(g["err"] >= 2, weights=g["w"]),
                        "P(good/bad wrong)": np.average(g["bad_wrong"], weights=g["w"])})
        return pd.DataFrame(out)

    print("   What predicts a correct segment class? (a) number of frames used "
          "— segments thinned to n random frames, truth = full human median:")
    rows = []
    for tag in [str(k) for k in SUBSAMPLE_N] + ["all"]:
        g = crow[crow["variant"].values == tag]
        rows.append({"frames used": tag, "rows": len(g),
                     "P(correct)": np.average(g["correct"], weights=g["w"]),
                     "P(|err|>=2)": np.average(g["err"] >= 2, weights=g["w"]),
                     "P(good/bad wrong)": np.average(g["bad_wrong"], weights=g["w"]),
                     "class MAE": np.average(g["err"], weights=g["w"])})
    print_df(pd.DataFrame(rows))
    print("   (b) margin = |aggregated score − nearest cut-point| (full segments):")
    print_df(by("margin", [0, .1, .2, .3, .4, .5, .7, 3], full, "margin"))
    print("   (c) IQR of the frame scores (full segments with >= 4 frames):")
    print_df(by("iqr", [0, .1, .15, .2, .3, .4, 3], full & (crow["n"].values >= 4),
                "iqr"))

    t23 = np.array([rec["ths"][f][1] for f in crow["fold"].values])
    crow["d23"] = np.abs(crow["agg"].values - t23)
    print("   (d) for the good/bad call alone: distance of the aggregated score "
          "to the good|bad cut-point t23 (full segments):")
    print_df(by("d23", [0, .1, .2, .3, .5, .8, 3], full, "|score − t23|"))

    for k, par in enumerate(cs["fold_par"]):
        print(f"   fold {k}: fitted on the other folds -> n_ref={par[0]}, "
              f"spread_ref={par[1]}, margin_ref={par[2]}")
    base_rate = np.average(crow["correct"], weights=crow["w"])
    print(f"   ALL data: n_ref={cs['par'][0]}, spread_ref={cs['par'][1]}, "
          f"margin_ref={cs['par'][2]} (Brier {cs['brier']:.4f}); unconstrained "
          f"best n_ref={cs['par_free'][0]}, spread_ref={cs['par_free'][1]}, "
          f"margin_ref={cs['par_free'][2]} (Brier {cs['brier_free']:.4f}); "
          f"constant predictor {base_rate * (1 - base_rate):.4f}; cross-fold "
          f"{np.average((cs['conf_cv'] - crow['correct']) ** 2, weights=crow['w']):.4f}\n")

    d = crow[full]
    fac = {"n term": 1.0 - np.exp(-d["n"].values / cs["par"][0]),
           "IQR term": np.exp(-(d["iqr"].values / cs["par"][1]) ** 2),
           "margin term": 0.5 + 0.5 * np.minimum(1.0, d["margin"].values
                                                 / cs["par"][2])}
    print("   How much each factor moves with the final parameters (full "
          "segments; 5% / 50% / 95% quantile): " + "; ".join(
              f"{k} " + " / ".join(f"{q:.2f}" for q in np.percentile(v, [5, 50, 95]))
              for k, v in fac.items()) + "\n")

    edges = np.array([0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9, 1.0])
    print("   Calibration with CROSS-FOLD parameters — full segments (as measured):")
    print_df(calib_table(crow[full], cs["conf_cv"][full], edges))
    print("   Calibration with CROSS-FOLD parameters — full + thinned rows:")
    print_df(calib_table(crow, cs["conf_cv"], edges))

    print(f"   Three levels: high >= {hi_t}, medium >= {med_t}, else low")
    for name, cf in (("CROSS-FOLD parameters", cs["conf_cv"]),
                     ("FINAL parameters (in the recipe)", cs["conf"])):
        print(f"   {name}, full segments:")
        print_df(calib_table(crow[full], cf[full], lv_edges, LEVELS))
    print("   FINAL parameters, full + thinned rows:")
    print_df(calib_table(crow, cs["conf"], lv_edges, LEVELS))
    print("   FINAL parameters, full segments, by predicted class (share of "
          "that class's length per level, and P(correct) in it):")
    rows = []
    d, cf = crow[full], cs["conf"][full]
    for c in S.RQI_LABELS:
        row = {"predicted": c}
        sel_c = d["pred"].values == c
        for j, nm in enumerate(LEVELS):
            s = sel_c & (cf >= lv_edges[j]) & ((cf < lv_edges[j + 1]) if j < 2 else True)
            row[f"{nm} share"] = d["w"].values[s].sum() / max(d["w"].values[sel_c].sum(), 1e-9)
            row[f"P(correct|{nm})"] = (np.average(d["correct"].values[s], weights=d["w"].values[s])
                                       if s.any() else np.nan)
        rows.append(row)
    print_df(pd.DataFrame(rows))

    # ---------------- 6. frame spacing ----------------
    rule(f"6) How dense must the frames be? {lname(Lr)} + {AGG_LABEL[kr]}, "
         "keeping every k-th frame of each chain (mean over the k offsets)")
    sp, sp_boot = spacing_eval(fr, chain, rank, segsets[Lr], kr, rec["ths"],
                               cs["par"], (med_t, hi_t), picks)
    print(f"     main columns = mean of the {len(PHASES)} segmentations; "
          "[..] and Δ = unshifted segmentation, paired cell bootstrap vs dense\n")
    rows = []
    for _, r in sp.iterrows():
        step = int(r["step"])
        dlo, dhi = ci(sp_boot[step] - sp_boot[1])
        rows.append({
            "every k-th": step, "≈ spacing m": round(step * float(np.median(fp))),
            "frames/seg": r["frames/seg"], "covered": r["covered"],
            f"n>={RECOMMENDED['min_images']}": r["n>=min_images"],
            "QWK": r["qwk"], "MAE": r["mae"], "exact": r["exact"],
            "bad AUC": r["bad_auc"], "bad acc": r["bad_acc"],
            "ΔQWK vs dense": "–" if step == 1 else fmt_d(
                r["qwk_0"] - sp["qwk_0"].values[0], dlo[0], dhi[0]),
            "ΔMAE vs dense": "–" if step == 1 else fmt_d(
                r["mae_0"] - sp["mae_0"].values[0], dlo[1], dhi[1]),
            "ΔAUC vs dense": "–" if step == 1 else fmt_d(
                r["bad_auc_0"] - sp["bad_auc_0"].values[0], dlo[4], dhi[4]),
        })
    print_df(pd.DataFrame(rows))
    print("   Confidence vs spacing (final parameters):")
    cols = ["mean conf", "high share", "medium share", "low share",
            "P(correct|high)", "P(correct|medium)", "P(correct|low)",
            "P(good/bad wrong|high)", "P(good/bad wrong|medium)",
            "P(good/bad wrong|low)"]
    t = sp[cols].copy()
    t.insert(0, "every k-th", sp["step"].astype(int))
    print_df(t)

    # ---------------- 7. regions ----------------
    rule("7) Per region: does the bias survive aggregation? "
         "(bias = predicted − truth; + = the model says worse than the human)")
    print(f"     segment rows = mean of the {len(PHASES)} segmentations "
          "(units = segments in the unshifted one)\n")

    def region_row(st, r, a):
        s = np.ones(len(st), bool) if a is None else st["area"].values == a
        w = st["length"].values[s]
        m = wmetrics(st["gt"].values[s], r["pred"][s], r["score"][s], w)
        return {"units": int(s.sum()), "km": w.sum() / 1000, "QWK": m["qwk"],
                "MAE": m["mae"], "exact": m["exact"], "bad AUC": m["bad_auc"],
                "bad acc": m["bad_acc"],
                "class bias": np.average(r["pred"][s] - st["gt"].values[s],
                                         weights=w),
                "score bias": np.average(r["score"][s] - st["lab_mean"].values[s],
                                         weights=w)}

    rows = []
    st_f = segsets[None][0][1]
    for a, label in list(S.AREA_LABELS.items()) + [(None, "ALL")]:
        rows.append({"region": label, "unit": "single frame",
                     **region_row(st_f, base["runs"][0], a)})
        per = [region_row(st, r, a)
               for (_, st), r in zip(segsets[Lr], rec["runs"])]
        mean = pd.DataFrame(per).mean(skipna=True).to_dict()
        mean["units"] = per[0]["units"]
        rows.append({"region": label, "unit": f"{lname(Lr)} {AGG_LABEL[kr]}",
                     **mean})
    print_df(pd.DataFrame(rows))
    print("   Confidence levels per region (final parameters, full segments, "
          f"{len(PHASES)} segmentations pooled):")
    rows = []
    for a, label in S.AREA_LABELS.items():
        s = full & (crow["area"].values == a)
        for _, r in calib_table(crow[s], cs["conf"][s], lv_edges, LEVELS).iterrows():
            rows.append({"region": label, "level": r["level"], "rows": r["rows"],
                         "share": r["share"], "P(correct)": r["P(correct)"],
                         "P(good/bad wrong)": r["P(good/bad wrong)"]})
    print_df(pd.DataFrame(rows))

    # ---------------- 8. recipe ----------------
    th_all = final_cutpoints(fr, segsets[Lr], kr)
    is_bad_all = np.concatenate([(st["gt"].values >= S.BAD_FROM).astype(int)
                                 for _, st in segsets[Lr]])
    gt_all = np.concatenate([st["gt"].values for _, st in segsets[Lr]])
    w_all = np.concatenate([st["length"].values for _, st in segsets[Lr]])

    def seg_mean(v):
        return np.concatenate([aggregate(v, seg, "mean_score")
                               for seg, _ in segsets[Lr]])

    def flag_acc(p, t):
        return np.average((p >= t) == is_bad_all, weights=w_all)

    # The backend's stored P(bad) / integer class come from the LIVE artifact
    # (its calibrator and frame cut-points), so the two knobs that act on them
    # are tuned through it. The artifact is only read, never written.
    p_fold = seg_mean(fr["p_bad"].values)
    p_thr_fold = best_p_threshold(is_bad_all, p_fold, w_all)
    p_thr, p_src, cls_src = p_thr_fold, "fold-fitted calibrator", "nested"
    frame_cls = fr["pred_rqi"].values.astype(float)
    notes = []
    if os.path.exists(ARTIFACT):
        import joblib
        art = joblib.load(ARTIFACT)
        notes.append("live artifact frame cut-points "
                     + fmt_th(art.get("thresholds", [])))
        if art.get("p_bad_calibrator") is not None:
            p_live = seg_mean(art["p_bad_calibrator"].predict(fr["score"].values))
            p_thr, p_src = (best_p_threshold(is_bad_all, p_live, w_all),
                            "live artifact's calibrator")
            notes.append(
                f"mean P(bad) threshold {p_thr:.2f} with the live calibrator "
                f"(good/bad acc {flag_acc(p_live, p_thr):.3f}); the fold-fitted "
                f"calibrator would give {p_thr_fold:.2f} "
                f"(acc {flag_acc(p_fold, p_thr_fold):.3f})")
        if art.get("thresholds"):
            frame_cls = np.digitize(fr["score"].values, art["thresholds"]) + 1.0
            cls_src = "live artifact's frame cut-points"
    mc = seg_mean(frame_cls)
    th_cls = S.tune_thresholds(gt_all, mc, sample_weight=w_all)
    recipe = {
        "version": 1,
        "segment_length_m": Lr,
        "aggregator": kr,
        "trim_fraction": TRIM if kr == "trimmed_mean_score" else 0.0,
        "thresholds": [round(t, 3) for t in th_all],
        "p_bad_threshold": round(p_thr, 2),
        "min_images": RECOMMENDED["min_images"],
        "recommended_frame_spacing_m": RECOMMENDED["frame_spacing_m"],
        "confidence": {"n_ref": cs["par"][0], "spread_ref": cs["par"][1],
                       "margin_ref": cs["par"][2], "high": hi_t, "medium": med_t},
        # only for frames that store the integer class but no continuous score
        "integer_class_fallback": {"aggregator": "mean_class",
                                   "thresholds": [round(t, 3) for t in th_cls]},
    }
    rule("8) Recommended recipe (cut-points tuned on ALL spatial-OOF segments "
         f"with the chosen aggregator, {len(PHASES)} segmentations pooled)")
    print(json.dumps(recipe, indent=2))
    print("   per-fold nested segment cut-points:      "
          + "; ".join(fmt_th(th) for th in rec["ths"]))
    print("   per-fold nested single-frame cut-points: "
          + "; ".join(fmt_th(th) for th in frame_ths))
    print(f"   p_bad_threshold tuned on mean P(bad) from the {p_src}; "
          f"integer_class_fallback tuned on frame classes from the {cls_src}")
    for n in notes:
        print("   " + n)

    print("\n   The same recipe at other lengths (cut-points and confidence "
          "fitted the same way; levels with FINAL parameters, full segments; "
          f"QWK at k = every k-th frame kept, mean of the {len(PHASES)} segmentations):")
    rows = []
    for L in ALTERNATIVES:
        r = results[(L, kr)]
        c = cs if L == Lr else confidence_study(segsets[L], fr, kr, r["ths"])
        lv = calib_table(c["rows"][c["full"]], c["conf"][c["full"]], lv_edges,
                         LEVELS).set_index("level")
        s = sp if L == Lr else spacing_eval(
            fr, chain, rank, segsets[L], kr, r["ths"], c["par"], (med_t, hi_t))[0]
        row = {"L": lname(L), "cut-points": fmt_th(final_cutpoints(fr, segsets[L], kr)),
               "n_ref/spread_ref/margin_ref": "/".join(str(x) for x in c["par"])}
        for nm in LEVELS[::-1]:
            row[f"{nm}: share, P(correct)"] = (
                f"{lv.loc[nm, 'share']:.2f}, {lv.loc[nm, 'P(correct)']:.2f}"
                if nm in lv.index else "–")
        for step in SPACING_STEPS:
            row[f"QWK k={step}"] = float(s.loc[s["step"] == step, "qwk"].iloc[0])
        rows.append(row)
    print_df(pd.DataFrame(rows))

    if args.write_recipe:
        with open(RECIPE_JSON, "w") as f:
            json.dump(recipe, f, indent=2)
            f.write("\n")
        print(f"   written -> {os.path.relpath(RECIPE_JSON, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
