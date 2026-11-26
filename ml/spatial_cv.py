"""
Spatially grouped cross-validation — the OFFICIAL evaluation protocol.

Why: Street View frames are ~10 m apart, so a random K-fold puts a frame in the
test fold and its near-identical neighbour (same street, same asphalt) in the
train fold. That measured ~0.89 QWK; a model that has to rate a street it has
never seen scores much lower. Every score that decides anything (promotion
gate, experiment grid, artifact model card) must come from this module.

Protocol (2026-11-18):
  - groups  : square grid cells of CELL_M = 1000 m (lat/lon -> local metres).
              Chosen from the label variogram: RQI similarity decays until
              ~1 km and is flat from 1 to 5 km (within a town), so 1 km cells
              remove the street-level leakage. Larger cells (3 km) start to
              hold out whole towns, which measures a *different* thing
              (regional transfer) — reported separately as leave-one-area-out.
  - folds   : StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
  - cut-points: tuned INSIDE each outer train fold on inner spatial OOF
              predictions (StratifiedGroupKFold(4) on the same cells), then
              applied to the outer test fold. No test label ever touches them.

Coordinates come from ml/image_coords.csv (ml/build_coords.py).
"""
import os

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (cohen_kappa_score, mean_absolute_error,
                             roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import rqi_scale as R  # noqa: F401  canonical scale, ML severity view (shared/rqi_scale.json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# RQI_ML_COORDS: alternative coordinate file (used by ml/retrain.py runs).
COORDS = os.environ.get("RQI_ML_COORDS") or os.path.join(ROOT, "ml", "image_coords.csv")

CELL_M = 1000
N_SPLITS = 5
INNER_SPLITS = 4
SEED = 42
RQI_LABELS = R.MODEL_LEVELS         # [1, 2, 3, 4] (severity, 1 = best)
BAD_FROM = R.BAD_FROM               # 3: severity >= 3 is a bad road
DROPPED_LEVELS = R.DROPPED_LEVELS   # [5]: too few labels, never trained
_LAT_REF = 47.0  # all data is in Hungary (46.8-47.5 N); fixed for determinism

AREA_LABELS = {
    "budapest": "Budapest (VII–VIII.)",
    "torokbalint": "Törökbálint–Budaörs",
    "szekesfehervar": "Székesfehérvár",
    "tapolca": "Tapolca környéke",
}


def load_coords(filenames):
    """Coordinates + area aligned to ``filenames`` (raises if any is missing)."""
    c = pd.read_csv(COORDS).drop_duplicates("image_filename")
    c = c.set_index("image_filename")
    missing = [f for f in filenames if f not in c.index]
    if missing:
        raise KeyError(f"{len(missing)} images have no coordinate in "
                       f"{os.path.relpath(COORDS, ROOT)} (e.g. {missing[0]}); "
                       f"re-run ml/build_coords.py")
    out = c.loc[list(filenames)].reset_index()
    if out[["lat", "lon"]].isna().any().any():
        raise ValueError("NaN coordinates in image_coords.csv")
    return out


def grid_cells(lat, lon, cell_m=CELL_M, offset=(0.0, 0.0)):
    """Integer group id of the cell_m x cell_m grid cell each point falls in.

    offset: grid origin shift in cell units (0..1, 0..1). The official
    protocol uses (0, 0); random offsets give a sensitivity estimate (with
    km-scale cells StratifiedGroupKFold is deterministic regardless of seed,
    so shifting the grid is the meaningful way to perturb the folds).
    """
    ky = np.floor(np.asarray(lat) * 111_320.0 / cell_m + offset[0]).astype(np.int64)
    kx = np.floor(np.asarray(lon) * 111_320.0 * np.cos(np.radians(_LAT_REF))
                  / cell_m + offset[1]).astype(np.int64)
    _, gid = np.unique(np.stack([ky, kx], 1), axis=0, return_inverse=True)
    return gid.ravel()


def spatial_folds(yc, groups, n_splits=N_SPLITS, seed=SEED):
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                                random_state=seed)
    return list(sgkf.split(np.zeros(len(yc)), yc, groups))


def tune_thresholds(y_true, pred, sample_weight=None):
    """Greedy per-boundary search for the 3 ordinal cut-points, maximising QWK.

    sample_weight: optional per-item weight (e.g. segment length in metres,
    see ml/segment_eval.py); None = the official unweighted per-image search.
    """
    th = [1.5, 2.5, 3.5]
    for _ in range(3):
        for i in range(3):
            lo = th[i - 1] if i else 0.8
            hi = th[i + 1] if i < 2 else 4.2
            best_q, best_t = -1.0, th[i]
            for t in np.linspace(lo + 0.02, hi - 0.02, 60):
                cand = sorted(th[:i] + [t] + th[i + 1:])
                q = cohen_kappa_score(y_true, np.digitize(pred, cand) + 1,
                                      weights="quadratic", labels=RQI_LABELS,
                                      sample_weight=sample_weight)
                if q > best_q:
                    best_q, best_t = q, t
            th[i] = best_t
            th = sorted(th)
    return [float(t) for t in th]


def _fit_predict(make_model, Xtr, ytr, Xte):
    model = make_pipeline(StandardScaler(), make_model())
    model.fit(Xtr, ytr)
    return model.predict(Xte)


def nested_spatial_cv(X, y, yc, groups, make_model, *, n_splits=N_SPLITS,
                      seed=SEED, tune=True, inner_splits=INNER_SPLITS,
                      return_inner=False):
    """Spatial outer CV with nested (inner spatial CV) cut-point tuning.

    make_model: zero-arg factory for the head (StandardScaler is prepended).
    Returns dict(oof=continuous OOF score, pred=OOF class, fold=fold id per
    sample, thresholds=list per fold). With return_inner=True (needs tune)
    also ``inner``: per outer fold a (train_idx, inner_oof) pair — the inner
    spatial OOF scores of that fold's training images, for anything else that
    must be fitted without touching the test fold (P(bad) calibration,
    segment-level cut-points; see ml/segment_eval.py).
    """
    folds = spatial_folds(yc, groups, n_splits, seed)
    oof = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    fold_id = np.zeros(len(y), dtype=int)
    ths, inner_oofs = [], []
    for k, (tr, te) in enumerate(folds):
        oof[te] = _fit_predict(make_model, X[tr], y[tr], X[te])
        fold_id[te] = k
        if tune:
            inner = spatial_folds(yc[tr], groups[tr], inner_splits, seed)
            ioof = np.zeros(len(tr))
            for itr, ite in inner:
                ioof[ite] = _fit_predict(make_model, X[tr][itr], y[tr][itr],
                                         X[tr][ite])
            th = tune_thresholds(yc[tr], ioof)
            inner_oofs.append((tr, ioof))
        else:
            th = [1.5, 2.5, 3.5]
        ths.append(th)
        pred[te] = np.digitize(oof[te], th) + 1
    res = {"oof": oof, "pred": pred, "fold": fold_id, "thresholds": ths}
    if return_inner:
        res["inner"] = inner_oofs
    return res


def head_factory(estimator):
    """Turn a (fitted or unfitted) sklearn estimator into a clone factory."""
    return lambda: clone(estimator)


def ordinal_metrics(yc, yp, score, sample_weight=None):
    """Headline metrics. yp = integer class, score = continuous (higher=worse).

    sample_weight: optional per-item weight (segment length for the
    length-weighted segment metrics); None = the official per-image metrics.
    """
    yc, yp, w = np.asarray(yc), np.asarray(yp), sample_weight
    is_bad = (yc >= BAD_FROM).astype(int)
    m = {
        "n": int(len(yc)),
        "mae": float(mean_absolute_error(yc, yp, sample_weight=w)),
        "exact": float(np.average(yc == yp, weights=w)),
        "off1": float(np.average(np.abs(yc - yp) <= 1, weights=w)),
        "qwk": float(cohen_kappa_score(yc, yp, weights="quadratic",
                                       labels=RQI_LABELS, sample_weight=w)),
        "bad_acc": float(np.average((yp >= BAD_FROM).astype(int) == is_bad,
                                    weights=w)),
    }
    m["bad_auc"] = (float(roc_auc_score(is_bad, score, sample_weight=w))
                    if 0 < is_bad.sum() < len(is_bad) else float("nan"))
    return m


def per_fold_std(yc, res):
    """Std of QWK/MAE/AUC across outer folds (how noisy one number is)."""
    vals = {"qwk": [], "mae": [], "bad_auc": []}
    for k in np.unique(res["fold"]):
        s = res["fold"] == k
        m = ordinal_metrics(yc[s], res["pred"][s], res["oof"][s])
        for key in vals:
            vals[key].append(m[key])
    return {k: float(np.nanstd(v)) for k, v in vals.items()}


def cluster_bootstrap_ci(yc, res, groups, n_boot=1000, seed=SEED, alpha=0.05):
    """95% CI of QWK/MAE/AUC by resampling whole grid cells (not images) —
    images in one cell are not independent, so an image-level bootstrap
    would be too narrow."""
    rng = np.random.default_rng(seed)
    cells = np.unique(groups)
    idx_by_cell = {c: np.flatnonzero(groups == c) for c in cells}
    out = {"qwk": [], "mae": [], "bad_auc": []}
    for _ in range(n_boot):
        pick = rng.choice(cells, size=len(cells), replace=True)
        idx = np.concatenate([idx_by_cell[c] for c in pick])
        m = ordinal_metrics(yc[idx], res["pred"][idx], res["oof"][idx])
        for k in out:
            out[k].append(m[k])
    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    return {k: (float(np.nanpercentile(v, lo)), float(np.nanpercentile(v, hi)))
            for k, v in out.items()}


def paired_bootstrap_delta(yc, res_ref, res_new, groups, n_boot=1000,
                           seed=SEED, alpha=0.05):
    """Paired cell-bootstrap of (new - ref) on the SAME folds/images.

    Returns {metric: (delta, ci_lo, ci_hi)}. "Measurably better" means the CI
    of the QWK delta excludes 0 (and MAE/AUC do not get significantly worse).
    """
    rng = np.random.default_rng(seed)
    cells = np.unique(groups)
    idx_by_cell = {c: np.flatnonzero(groups == c) for c in cells}
    base_a = ordinal_metrics(yc, res_ref["pred"], res_ref["oof"])
    base_b = ordinal_metrics(yc, res_new["pred"], res_new["oof"])
    keys = ("qwk", "mae", "bad_auc")
    d = {k: [] for k in keys}
    for _ in range(n_boot):
        pick = rng.choice(cells, size=len(cells), replace=True)
        idx = np.concatenate([idx_by_cell[c] for c in pick])
        a = ordinal_metrics(yc[idx], res_ref["pred"][idx], res_ref["oof"][idx])
        b = ordinal_metrics(yc[idx], res_new["pred"][idx], res_new["oof"][idx])
        for k in keys:
            d[k].append(b[k] - a[k])
    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    return {k: (float(base_b[k] - base_a[k]), float(np.nanpercentile(d[k], lo)),
                float(np.nanpercentile(d[k], hi))) for k in keys}
