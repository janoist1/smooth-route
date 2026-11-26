#!/usr/bin/env python3
"""
Segment-level evaluation: how to turn noisy per-frame RQI predictions into a
reliable ROAD-SEGMENT quality, measured honestly (spatially grouped).

One command, prints every table of docs/MODEL_EXPERIMENTS.md section 7:

  .venv/bin/python ml/segment_eval.py                 # evaluate + print
  .venv/bin/python ml/segment_eval.py --write-recipe  # also (re)write ml/segment_recipe.json

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
     label (half-way ties go towards the segment mean, then to the worse class).
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

# the live champion (ml/README.md): DINOv2-small CLS+patch-mean + SVR-RBF
CHAMPION = {"recipe": "cls+patch", "backbone": "small", "head": "svr-rbf"}

GAP_M = 40.0          # chain breaks at a larger gap between consecutive frames
TURN_DEG = 45.0       # ... and at a sharper turn between consecutive steps
NOMINAL_STEP_M = 10.0  # footprint of a frame that has no neighbour
LENGTHS = [None, 50, 100, 150, 200, 300]   # None = single frame
SIGMAS = [25, 50, 100]
TRIM = 0.2            # trimmed mean: fraction cut from EACH end
PHASES = [0.0, 1 / 3, 2 / 3]    # shifted segmentations (robustness)
SUBSAMPLE_N = [1, 2, 3, 5, 8]   # confidence: thin a segment to n frames
SUBSAMPLE_DRAWS = 4
SPACING_STEPS = [1, 2, 3, 5, 10]   # keep every k-th frame (~10 m apart)

# ---- the recommended recipe (picked from the nested tables this script
# ---- prints; see docs/MODEL_EXPERIMENTS.md section 7 for the reasoning) ----
RECOMMENDED = {"segment_length_m": 200, "aggregator": "median_score",
               "min_images": 2, "frame_spacing_m": 50,
               "high": 0.70, "medium": 0.60}

AGG_LABEL = {"median_score": "median score", "mean_score": "mean score",
             "trimmed_mean_score": f"trimmed mean ({TRIM:.0%}/side)",
             "mean_p_bad": "mean P(bad)", "majority_vote": "majority vote"}
KEYS = ("qwk", "mae", "exact", "off1", "bad_auc", "bad_acc")


# --------------------------------------------------------------------------
# 1. champion OOF under the official spatial protocol
# --------------------------------------------------------------------------
def champion_oof():
    """Frame table with OOF score/class/P(bad) + inner-OOF matrices.

    inner[k, i]   = inner spatial OOF score of frame i when fold k is the test
                    fold (NaN if frame i is in test fold k). Used to tune
                    anything "inside the fold".
    inner_p[k, i] = the same through fold k's P(bad) calibrator.
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
    return seg


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
    lab_gt = t["gt"].values[seg]
    dev = pd.Series(np.abs(fr["human_rqi"].values - lab_gt)).groupby(seg)
    t["purity"] = (dev.apply(lambda s: (s == 0).mean())).values
    t["mad"] = dev.mean().values
    return t


# --------------------------------------------------------------------------
# 3. aggregators
# --------------------------------------------------------------------------
def aggregate(v, seg, kind):
    """Per-segment aggregate of a frame vector (NaN-only segments stay NaN)."""
    g = pd.Series(v).groupby(seg, sort=True)
    if kind == "median_score":
        return g.median().values
    if kind in ("mean_score", "mean_p_bad"):
        return g.mean().values
    if kind == "trimmed_mean_score":
        return g.agg(lambda s: trim_mean(s.values, TRIM)).values
    if kind == "iqr":
        return g.agg(lambda s: np.subtract(*np.percentile(s.values, [75, 25]))).values
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


def nested_classes(gt, w, fold, agg_oof, agg_inner):
    """Class per unit with cut-points tuned inside the fold: for test fold k
    they are tuned on the TRAINING units' aggregated inner-OOF scores."""
    pred = np.zeros(len(gt), dtype=int)
    ths = []
    for k in range(S.N_SPLITS):
        tr = fold != k
        th = S.tune_thresholds(gt[tr], agg_inner[k][tr], sample_weight=w[tr])
        pred[~tr] = np.digitize(agg_oof[~tr], th) + 1
        ths.append(th)
    return pred, ths


def nested_bad_flag(is_bad, w, fold, p_oof, p_inner):
    """Good/bad flag from mean P(bad) with the threshold tuned inside the fold
    (maximising length-weighted accuracy on the training units)."""
    flag = np.zeros(len(is_bad), dtype=int)
    for k in range(S.N_SPLITS):
        tr = fold != k
        flag[~tr] = p_oof[~tr] >= best_p_threshold(is_bad[tr], p_inner[k][tr], w[tr])
    return flag


def best_p_threshold(is_bad, p, w):
    grid = np.linspace(0.10, 0.90, 81)
    acc = [np.average((p >= t).astype(int) == is_bad, weights=w) for t in grid]
    best = np.flatnonzero(np.isclose(acc, np.max(acc)))
    return float(grid[best[len(best) // 2]])   # middle of the plateau


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
    "margin_ref": [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5],
}
BRIER_TOL = 0.001


def fit_confidence(rows):
    """Grid-search the three parameters: minimise the length-weighted Brier
    score of confidence vs "segment class is correct".

    Fits within BRIER_TOL of the best are indistinguishable, so among them the
    most cautious one wins: the largest n_ref (few frames -> less sure), then
    the smallest spread_ref (scattered scores -> less sure), then the best
    margin_ref. The labelled runs are dense and curated; this keeps the two
    terms they cannot test (very few frames, wildly scattered scores) from
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


def frames_by_segment(seg):
    return pd.Series(np.arange(len(seg))).groupby(seg, sort=True).apply(
        lambda s: s.values)


def confidence_rows(seg, st, fr, kind, ths_by_fold, rng):
    """Evaluation rows for the confidence fit: every segment as measured
    (all its frames) plus thinned copies with only n frames (SUBSAMPLE_N,
    random subsets) — the labelled runs are dense (~10 m), production
    segments will often hold fewer images. Truth stays the segment's full
    human median; cut-points are the segment's own fold's (nested)."""
    score = fr["score"].values
    rows = []
    for s, idx in enumerate(frames_by_segment(seg)):
        fold = int(st["fold"].values[s])
        th = ths_by_fold[fold]
        gt, lab_mean = int(st["gt"].values[s]), float(st["lab_mean"].values[s])
        length = float(st["length"].values[s])
        variants = [("all", idx, 1.0)]
        for k in SUBSAMPLE_N:
            if k < len(idx):
                variants += [(str(k), rng.choice(idx, k, replace=False),
                              1.0 / SUBSAMPLE_DRAWS)
                             for _ in range(SUBSAMPLE_DRAWS)]
        for tag, ii, wmul in variants:
            r = segment_row(score[ii], th, gt, lab_mean, kind)
            r.update(seg=s, variant=tag, fold=fold, w=length * wmul,
                     cell=int(st["cell"].values[s]),
                     area=st["area"].values[s])
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
            "segs": int(s.sum()),
            "share": float(w.sum() / rows["w"].sum()),
            "mean conf": float(np.average(conf[s], weights=w)),
            "P(correct)": avg(rows["correct"].values),
            "P(|err|>=1)": 1.0 - avg(rows["correct"].values),
            "P(|err|>=2)": avg((rows["err"].values >= 2).astype(float)),
            "P(good/bad wrong)": avg(rows["bad_wrong"].values),
            "class MAE": avg(rows["err"].values.astype(float)),
        })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# 6. frame spacing (how dense must the frames be?)
# --------------------------------------------------------------------------
def spacing_eval(fr, chain, rank, seg, st, kind, ths_by_fold, par, picks,
                 levels):
    """Keep every k-th frame of each chain (k = SPACING_STEPS, every offset)
    and re-evaluate the recommended recipe: same segments, same truth (the
    full human median), same cut-points; only the frames used shrink."""
    score = fr["score"].values
    gt, w = st["gt"].values, st["length"].values
    cell, fold = st["cell"].values, st["fold"].values
    lab_mean = st["lab_mean"].values
    in_chain = (pd.Series(rank).groupby(chain).rank(method="first")
                .astype(int).values - 1)
    med_t, hi_t = levels
    out, boots = [], {}
    for step in SPACING_STEPS:
        acc = []
        bsum = 0.0
        for offset in range(step):
            keep = np.flatnonzero(in_chain % step == offset)
            rows = []
            for s, ii in pd.Series(keep).groupby(seg[keep], sort=True):
                r = segment_row(score[ii.values], ths_by_fold[int(fold[s])],
                                int(gt[s]), float(lab_mean[s]), kind)
                r.update(seg=s, w=float(w[s]))
                rows.append(r)
            d = pd.DataFrame(rows)
            sg = d["seg"].values
            conf = confidence(d["n"].values, d["iqr"].values,
                              d["margin"].values, *par)
            m = wmetrics(d["gt"].values, d["pred"].values, d["agg"].values,
                         d["w"].values)
            bsum = bsum + boot_matrix(cell[sg], d["gt"].values,
                                      d["pred"].values, d["agg"].values,
                                      d["w"].values, picks)
            dw = d["w"].values
            lvl = np.where(conf >= hi_t, 2, np.where(conf >= med_t, 1, 0))
            row = {k: m[k] for k in KEYS}
            row.update({
                "frames/seg": float(np.average(d["n"].values, weights=dw)),
                "covered": dw.sum() / w.sum(),
                "n>=min_images": dw[d["n"].values >= RECOMMENDED["min_images"]].sum() / w.sum(),
                "mean conf": float(np.average(conf, weights=dw)),
            })
            for j, name in enumerate(("low", "medium", "high")):
                sel = lvl == j
                row[f"{name} share"] = dw[sel].sum() / dw.sum()
                row[f"P(correct|{name})"] = (
                    float(np.average(d["correct"].values[sel], weights=dw[sel]))
                    if sel.any() else np.nan)
            acc.append(row)
        mean = pd.DataFrame(acc).mean().to_dict()
        mean["step"] = step
        out.append(mean)
        boots[step] = bsum / step
    return pd.DataFrame(out), boots


# --------------------------------------------------------------------------
# printing helpers
# --------------------------------------------------------------------------
def lname(length_m):
    return "1 frame" if length_m is None else f"{length_m} m"


def fmt_ci(v, lo, hi, d=3):
    return f"{v:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def fmt_d(v, lo, hi, d=3):
    return f"{v:+.{d}f} [{lo:+.{d}f}, {hi:+.{d}f}]"


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
    args = ap.parse_args()
    if args.length:
        RECOMMENDED["segment_length_m"] = args.length
    if args.aggregator:
        RECOMMENDED["aggregator"] = args.aggregator
    if (args.length or args.aggregator) and args.write_recipe:
        ap.error("--write-recipe writes the RECOMMENDED recipe only; change "
                 "RECOMMENDED in the script to recommend something else")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)

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

    segs, tabs = {}, {}
    rows = []
    for L in LENGTHS:
        seg = cut_segments(chain, fp, rank, L)
        st = segment_table(seg, fr, fp)
        segs[L], tabs[L] = seg, st
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
        g = pd.Series(resid).groupby(segs[L])
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

    def evaluate(seg, st, kind, fixed_ths=None):
        gt, w, fold = st["gt"].values, st["length"].values, st["fold"].values
        bad_flag, ths = None, None
        if kind == "majority_vote":
            pred = majority(fr["pred_rqi"].values, seg)
            score = pd.Series(fr["pred_rqi"].values.astype(float)).groupby(
                seg, sort=True).mean().values
        elif kind == "mean_p_bad":
            score = aggregate(fr["p_bad"].values, seg, kind)
            agg_in = [aggregate(inner_p[k], seg, kind) for k in range(S.N_SPLITS)]
            # 4 classes from mean P(bad): cut-points searched on 1 + 3*p
            pred, ths = nested_classes(gt, w, fold, 1 + 3 * score,
                                       [1 + 3 * a for a in agg_in])
            bad_flag = nested_bad_flag((gt >= S.BAD_FROM).astype(int), w, fold,
                                       score, agg_in)
        else:
            score = aggregate(fr["score"].values, seg, kind)
            if fixed_ths is not None:
                ths = fixed_ths
                pred = np.zeros(len(gt), dtype=int)
                for k in range(S.N_SPLITS):
                    pred[fold == k] = np.digitize(score[fold == k], ths[k]) + 1
            else:
                agg_in = [aggregate(inner[k], seg, kind)
                          for k in range(S.N_SPLITS)]
                pred, ths = nested_classes(gt, w, fold, score, agg_in)
        return {"m": wmetrics(gt, pred, score, w, bad_flag), "pred": pred,
                "score": score, "ths": ths, "bad_flag": bad_flag}

    def with_boot(r, st):
        r["boot"] = boot_matrix(st["cell"].values, st["gt"].values, r["pred"],
                                r["score"], st["length"].values, picks,
                                r["bad_flag"])
        return r

    ALL_KINDS = ["median_score", "mean_score", "trimmed_mean_score",
                 "mean_p_bad", "majority_vote"]
    results = {(None, "median_score"):
               with_boot(evaluate(segs[None], tabs[None], "median_score"),
                         tabs[None])}
    base = results[(None, "median_score")]
    shifted = {}    # (L, kind) -> list of metric dicts, one per phase
    for L in LENGTHS[1:]:
        for kind in ALL_KINDS:
            results[(L, kind)] = with_boot(evaluate(segs[L], tabs[L], kind),
                                           tabs[L])
            shifted[(L, kind)] = [results[(L, kind)]["m"]]
        for ph in PHASES[1:]:
            seg_p = cut_segments(chain, fp, rank, L, ph)
            st_p = segment_table(seg_p, fr, fp)
            for kind in ALL_KINDS:
                shifted[(L, kind)].append(evaluate(seg_p, st_p, kind)["m"])

    rule("3+4) Segment-level metrics, length-weighted; cut-points re-tuned per "
         "aggregator INSIDE the spatial folds")
    print(f"     [..] = 95% CI, cell bootstrap ({args.n_boot} resamples of the "
          f"{len(cells)} cells); Δ = paired gain vs the single frame;")
    print(f"     'shifted' = mean ± sd over {len(PHASES)} segmentations of the "
          "same chains (cuts moved by 0, 1/3, 2/3 of a segment)\n")
    rows = []
    for (L, kind), r in results.items():
        lo, hi = ci(r["boot"])
        dlo, dhi = ci(r["boot"] - base["boot"])
        m = r["m"]
        row = {"L": lname(L),
               "aggregator": "(single frame)" if L is None else AGG_LABEL[kind],
               "segs": len(r["pred"]),
               "QWK": fmt_ci(m["qwk"], lo[0], hi[0]),
               "MAE": fmt_ci(m["mae"], lo[1], hi[1]),
               "exact": f"{m['exact']:.3f}", "±1": f"{m['off1']:.3f}",
               "bad AUC": fmt_ci(m["bad_auc"], lo[4], hi[4]),
               "bad acc": f"{m['bad_acc']:.3f}",
               "ΔQWK": fmt_d(m["qwk"] - base["m"]["qwk"], dlo[0], dhi[0]),
               "ΔMAE": fmt_d(m["mae"] - base["m"]["mae"], dlo[1], dhi[1]),
               "ΔAUC": fmt_d(m["bad_auc"] - base["m"]["bad_auc"], dlo[4], dhi[4])}
        if L is not None:
            sh = pd.DataFrame(shifted[(L, kind)])
            row["QWK shifted"] = f"{sh['qwk'].mean():.3f} ± {sh['qwk'].std(ddof=0):.3f}"
            row["MAE shifted"] = f"{sh['mae'].mean():.3f}"
            row["AUC shifted"] = f"{sh['bad_auc'].mean():.3f}"
            row["bad acc shifted"] = f"{sh['bad_acc'].mean():.3f}"
        else:
            row.update({"QWK shifted": "–", "MAE shifted": "–",
                        "AUC shifted": "–", "bad acc shifted": "–"})
        rows.append(row)
    print_df(pd.DataFrame(rows))

    print("   Summary over segmentations ('shifted' means): QWK / MAE by "
          "aggregator and length")
    piv = pd.DataFrame([
        {"aggregator": AGG_LABEL[kind], "L": lname(L),
         "v": f"{pd.DataFrame(v)['qwk'].mean():.3f} / {pd.DataFrame(v)['mae'].mean():.3f}"}
        for (L, kind), v in shifted.items()])
    print(piv.pivot(index="aggregator", columns="L", values="v")
          .reindex(index=[AGG_LABEL[k] for k in ALL_KINDS],
                   columns=[lname(L) for L in LENGTHS[1:]]).to_string())
    print(f"   single frame: {base['m']['qwk']:.3f} / {base['m']['mae']:.3f}\n")

    # does re-tuning the cut-points for the aggregated score pay off?
    Lr, kr = RECOMMENDED["segment_length_m"], RECOMMENDED["aggregator"]
    print(f"   Re-tuned cut-points vs the single-frame cut-points applied to the "
          f"aggregated score ({AGG_LABEL[kr]}; mean of the "
          f"{len(PHASES)} segmentations):")
    rows = []
    for L in LENGTHS[1:]:
        fx = [evaluate(cut_segments(chain, fp, rank, L, ph),
                       segment_table(cut_segments(chain, fp, rank, L, ph), fr, fp),
                       kr, fixed_ths=frame_ths)["m"] for ph in PHASES]
        a, b = pd.DataFrame(shifted[(L, kr)]), pd.DataFrame(fx)
        rows.append({"L": lname(L),
                     "QWK re-tuned": a["qwk"].mean(), "QWK frame cut-points": b["qwk"].mean(),
                     "MAE re-tuned": a["mae"].mean(), "MAE frame cut-points": b["mae"].mean(),
                     "bad acc re-tuned": a["bad_acc"].mean(),
                     "bad acc frame cut-points": b["bad_acc"].mean()})
    print_df(pd.DataFrame(rows))

    # confusion matrix of the recommended recipe
    rec, st_r, seg_r = results[(Lr, kr)], tabs[Lr], segs[Lr]
    print(f"   Confusion of the recommended recipe ({lname(Lr)} + {AGG_LABEL[kr]}), "
          "in km of road; rows = segment truth, cols = predicted:")
    cm = pd.crosstab(st_r["gt"].values, rec["pred"], st_r["length"].values,
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
        dlo, dhi = ci(b - base["boot"])
        rows.append({"method": name,
                     "QWK": fmt_ci(m["qwk"], lo[0], hi[0]),
                     "MAE": fmt_ci(m["mae"], lo[1], hi[1]),
                     "exact": f"{m['exact']:.3f}", "±1": f"{m['off1']:.3f}",
                     "bad AUC": fmt_ci(m["bad_auc"], lo[4], hi[4]),
                     "bad acc": f"{m['bad_acc']:.3f}",
                     "ΔQWK": fmt_d(m["qwk"] - base["m"]["qwk"], dlo[0], dhi[0]),
                     "ΔMAE": fmt_d(m["mae"] - base["m"]["mae"], dlo[1], dhi[1])})

    frame_row("single frame", base["pred"], base["score"])
    for L in LENGTHS[1:]:
        r = results[(L, kr)]
        frame_row(f"segment {L} m", r["pred"][segs[L]], r["score"][segs[L]])
    for sg in SIGMAS:
        sm = gaussian_smooth(fr["score"].values, chain, pos, sg)
        sm_in = [gaussian_smooth(inner[k], chain, pos, sg)
                 for k in range(S.N_SPLITS)]
        pred_s, _ = nested_classes(yc, fp, fold_f, sm, sm_in)
        frame_row(f"Gaussian σ={sg} m", pred_s, sm)
    print_df(pd.DataFrame(rows))

    # ---------------- 5. confidence ----------------
    rule(f"5) Confidence — {lname(Lr)} + {AGG_LABEL[kr]}; conf = "
         "(1-exp(-n/n_ref)) * exp(-(iqr/spread_ref)^2) * "
         "(0.5+0.5*min(1,margin/margin_ref))")
    crow = confidence_rows(seg_r, st_r, fr, kr, rec["ths"],
                           np.random.default_rng(S.SEED))
    full = crow["variant"].values == "all"

    def by(col, bins, sel, label):
        d = crow[sel]
        b = pd.cut(d[col], bins, include_lowest=True)
        out = []
        for key, g in d.groupby(b, observed=True):
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

    # cross-fold: parameters fitted on 4 folds' segments, applied to the 5th
    conf_cv = np.zeros(len(crow))
    for k in range(S.N_SPLITS):
        te = crow["fold"].values == k
        par, _, _, _ = fit_confidence(crow[~te])
        conf_cv[te] = confidence(crow["n"].values[te], crow["iqr"].values[te],
                                 crow["margin"].values[te], *par)
        print(f"   fold {k}: fitted on the other folds -> n_ref={par[0]}, "
              f"spread_ref={par[1]}, margin_ref={par[2]}")
    par_all, brier_all, par_free, brier_free = fit_confidence(crow)
    base_rate = np.average(crow["correct"], weights=crow["w"])
    print(f"   ALL data: n_ref={par_all[0]}, spread_ref={par_all[1]}, "
          f"margin_ref={par_all[2]} (Brier {brier_all:.4f}); unconstrained "
          f"best n_ref={par_free[0]}, spread_ref={par_free[1]}, "
          f"margin_ref={par_free[2]} (Brier {brier_free:.4f}); constant "
          f"predictor {base_rate * (1 - base_rate):.4f}; cross-fold "
          f"{np.average((conf_cv - crow['correct']) ** 2, weights=crow['w']):.4f}\n")

    edges = np.array([0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9, 1.0])
    print("   Calibration with CROSS-FOLD parameters — full segments (as measured):")
    print_df(calib_table(crow[full], conf_cv[full], edges))
    print("   Calibration with CROSS-FOLD parameters — full + thinned rows:")
    print_df(calib_table(crow, conf_cv, edges))

    hi_t, med_t = RECOMMENDED["high"], RECOMMENDED["medium"]
    conf_final = confidence(crow["n"].values, crow["iqr"].values,
                            crow["margin"].values, *par_all)
    lv_edges, lv_names = np.array([0, med_t, hi_t, 1.0]), ["low", "medium", "high"]
    print(f"   Three levels: high >= {hi_t}, medium >= {med_t}, else low")
    for name, cf in (("CROSS-FOLD parameters", conf_cv),
                     ("FINAL parameters (in the recipe)", conf_final)):
        print(f"   {name}, full segments:")
        print_df(calib_table(crow[full], cf[full], lv_edges, lv_names))
    print("   FINAL parameters, full + thinned rows:")
    print_df(calib_table(crow, conf_final, lv_edges, lv_names))
    print("   FINAL parameters, full segments, by predicted class "
          "(share of that class's length per level / P(correct)):")
    rows = []
    d, cf = crow[full], conf_final[full]
    for c in S.RQI_LABELS:
        row = {"predicted": c}
        sel_c = d["pred"].values == c
        for j, nm in enumerate(lv_names):
            s = sel_c & (cf >= lv_edges[j]) & ((cf < lv_edges[j + 1]) if j < 2 else True)
            row[f"{nm} share"] = d["w"].values[s].sum() / max(d["w"].values[sel_c].sum(), 1e-9)
            row[f"P(correct|{nm})"] = (np.average(d["correct"].values[s], weights=d["w"].values[s])
                                       if s.any() else np.nan)
        rows.append(row)
    print_df(pd.DataFrame(rows))

    # ---------------- 6. frame spacing ----------------
    rule(f"6) How dense must the frames be? {lname(Lr)} + {AGG_LABEL[kr]}, "
         "keeping every k-th frame of each chain (mean over the k offsets)")
    sp, sp_boot = spacing_eval(fr, chain, rank, seg_r, st_r, kr, rec["ths"],
                               par_all, picks, (med_t, hi_t))
    rows = []
    for _, r in sp.iterrows():
        step = int(r["step"])
        lo, hi = ci(sp_boot[step])
        dlo, dhi = ci(sp_boot[step] - sp_boot[1])
        rows.append({
            "every k-th": step, "≈ spacing m": round(step * float(np.median(fp))),
            "frames/seg": r["frames/seg"], "covered": r["covered"],
            f"n>={RECOMMENDED['min_images']}": r["n>=min_images"],
            "QWK": fmt_ci(r["qwk"], lo[0], hi[0]),
            "MAE": fmt_ci(r["mae"], lo[1], hi[1]),
            "exact": r["exact"],
            "bad AUC": fmt_ci(r["bad_auc"], lo[4], hi[4]), "bad acc": r["bad_acc"],
            "ΔQWK vs dense": "–" if step == 1 else fmt_d(
                r["qwk"] - sp["qwk"].values[0], dlo[0], dhi[0]),
            "ΔMAE vs dense": "–" if step == 1 else fmt_d(
                r["mae"] - sp["mae"].values[0], dlo[1], dhi[1]),
        })
    print_df(pd.DataFrame(rows))
    print("   Confidence vs spacing (final parameters):")
    cols = ["mean conf", "high share", "medium share", "low share",
            "P(correct|high)", "P(correct|medium)", "P(correct|low)"]
    t = sp[cols].copy()
    t.insert(0, "every k-th", sp["step"].astype(int))
    print_df(t)

    # ---------------- 7. regions ----------------
    rule("7) Per region: does the bias survive aggregation? "
         "(bias = predicted − truth; + = the model says worse than the human)")
    rows = []
    st_f = tabs[None]
    for a, label in list(S.AREA_LABELS.items()) + [(None, "ALL")]:
        for name, st, r in (("single frame", st_f, base),
                            (f"{lname(Lr)} {AGG_LABEL[kr]}", st_r, rec)):
            s = np.ones(len(st), bool) if a is None else st["area"].values == a
            w = st["length"].values[s]
            m = wmetrics(st["gt"].values[s], r["pred"][s], r["score"][s], w)
            rows.append({"region": label, "unit": name, "units": int(s.sum()),
                         "km": w.sum() / 1000, "QWK": m["qwk"], "MAE": m["mae"],
                         "exact": m["exact"], "bad AUC": m["bad_auc"],
                         "bad acc": m["bad_acc"],
                         "class bias": np.average(r["pred"][s] - st["gt"].values[s], weights=w),
                         "score bias": np.average(r["score"][s] - st["lab_mean"].values[s], weights=w)})
    print_df(pd.DataFrame(rows))
    print("   Confidence levels per region (final parameters, full segments):")
    rows = []
    for a, label in S.AREA_LABELS.items():
        s = full & (crow["area"].values == a)
        t = calib_table(crow[s], conf_final[s], lv_edges, lv_names)
        for _, r in t.iterrows():
            rows.append({"region": label, "level": r["level"], "segs": r["segs"],
                         "share": r["share"], "P(correct)": r["P(correct)"],
                         "P(good/bad wrong)": r["P(good/bad wrong)"]})
    print_df(pd.DataFrame(rows))

    # ---------------- 8. recipe ----------------
    agg_all = aggregate(fr["score"].values, seg_r, kr)
    th_all = S.tune_thresholds(st_r["gt"].values, agg_all,
                               sample_weight=st_r["length"].values)
    p_all = aggregate(fr["p_bad"].values, seg_r, "mean_p_bad")
    p_thr = best_p_threshold((st_r["gt"].values >= S.BAD_FROM).astype(int),
                             p_all, st_r["length"].values)
    recipe = {
        "version": 1,
        "segment_length_m": Lr,
        "aggregator": kr,
        "trim_fraction": TRIM if kr == "trimmed_mean_score" else 0.0,
        "thresholds": [round(t, 3) for t in th_all],
        "p_bad_threshold": round(p_thr, 2),
        "min_images": RECOMMENDED["min_images"],
        "recommended_frame_spacing_m": RECOMMENDED["frame_spacing_m"],
        "confidence": {"n_ref": par_all[0], "spread_ref": par_all[1],
                       "margin_ref": par_all[2], "high": hi_t, "medium": med_t},
    }
    rule("8) Recommended recipe (cut-points tuned on ALL spatial-OOF segments "
         "with the chosen aggregator)")
    print(json.dumps(recipe, indent=2))
    for ph in PHASES[1:]:
        seg_p = cut_segments(chain, fp, rank, Lr, ph)
        st_p = segment_table(seg_p, fr, fp)
        th_p = S.tune_thresholds(st_p["gt"].values,
                                 aggregate(fr["score"].values, seg_p, kr),
                                 sample_weight=st_p["length"].values)
        print(f"   (same, cuts shifted by {ph:.2f} segment: "
              + ", ".join(f"{t:.3f}" for t in th_p) + ")")
    print("   per-fold nested segment cut-points: "
          + "; ".join("[" + ", ".join(f"{t:.2f}" for t in th) + "]"
                      for th in rec["ths"]))
    print("   per-fold nested single-frame cut-points: "
          + "; ".join("[" + ", ".join(f"{t:.2f}" for t in th) + "]"
                      for th in frame_ths))
    m_all = wmetrics(st_r["gt"].values, np.digitize(agg_all, th_all) + 1,
                     agg_all, st_r["length"].values)
    print(f"   (in-sample check of the final cut-points, NOT a performance "
          f"claim: QWK {m_all['qwk']:.3f}, MAE {m_all['mae']:.3f})")
    if args.write_recipe:
        with open(RECIPE_JSON, "w") as f:
            json.dump(recipe, f, indent=2)
            f.write("\n")
        print(f"   written -> {os.path.relpath(RECIPE_JSON, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
