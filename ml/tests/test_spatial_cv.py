"""Tests for ml/spatial_cv.py — the official evaluation protocol behind every
promotion decision (synthetic data only: no caches, no torch, no images).

Run: .venv/bin/python -m pytest -q ml/tests/test_spatial_cv.py
"""
import os
import sys

import numpy as np
import pytest
from sklearn.linear_model import Ridge

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spatial_cv as S  # noqa: E402

M_PER_DEG = 111_320.0


def synthetic(n_cells=30, per_cell=12, seed=0, noise=0.3):
    """Frames on a grid of 1 km cells; quality varies smoothly by cell, and a
    2-d feature carries the label signal (+ noise)."""
    rng = np.random.default_rng(seed)
    lat, lon, y = [], [], []
    for c in range(n_cells):
        base_lat = 47.0 + (c // 6) * 1.5 / 111.32     # 1.5 km apart -> own cells
        base_lon = 19.0 + (c % 6) * 1.5 / (111.32 * np.cos(np.radians(47.0)))
        level = 1 + (c % 4)                            # all 4 classes present
        for _ in range(per_cell):
            lat.append(base_lat + rng.uniform(0, 0.4) / 111.32)
            lon.append(base_lon + rng.uniform(0, 0.4) / (111.32 * np.cos(np.radians(47.0))))
            y.append(np.clip(level + rng.normal(0, 0.25), 1, 4))
    y = np.array(y)
    yc = np.clip(np.round(y), 1, 4).astype(int)
    X = np.c_[y + rng.normal(0, noise, len(y)), rng.normal(0, 1, len(y))]
    return np.array(lat), np.array(lon), X, y, yc


# --- grid cells ---------------------------------------------------------------

def test_grid_cells_same_cell_same_id_and_1km_apart_differ():
    lat = np.array([47.0, 47.0 + 100 / M_PER_DEG, 47.0 + 1500 / M_PER_DEG])
    lon = np.array([19.0, 19.0, 19.0])
    g = S.grid_cells(lat, lon)
    assert g[0] == g[1] and g[0] != g[2]
    assert g.min() == 0 and g.max() == len(np.unique(g)) - 1   # dense ids


def test_grid_cells_cell_size_and_offset():
    lat = 47.0 + np.arange(10) * 300 / M_PER_DEG                # every 300 m
    lon = np.full(10, 19.0)
    assert len(np.unique(S.grid_cells(lat, lon, cell_m=1000))) < 10
    assert len(np.unique(S.grid_cells(lat, lon, cell_m=100))) == 10
    a = S.grid_cells(lat, lon, offset=(0.0, 0.0))
    b = S.grid_cells(lat, lon, offset=(0.5, 0.0))
    assert not np.array_equal(a, b)                             # the grid moved


# --- folds --------------------------------------------------------------------

def test_spatial_folds_never_split_a_cell_and_cover_everything_once():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    folds = S.spatial_folds(yc, g)
    assert len(folds) == S.N_SPLITS
    seen = np.concatenate([te for _, te in folds])
    assert sorted(seen) == list(range(len(yc)))                 # each frame tested once
    for tr, te in folds:
        assert not set(g[tr]) & set(g[te])                      # no cell on both sides


def test_spatial_folds_are_deterministic():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    a, b = S.spatial_folds(yc, g), S.spatial_folds(yc, g)
    for (tr1, te1), (tr2, te2) in zip(a, b):
        assert np.array_equal(te1, te2) and np.array_equal(tr1, tr2)


# --- cut-points ---------------------------------------------------------------

def test_tune_thresholds_recovers_separable_cut_points():
    rng = np.random.default_rng(1)
    yc = np.repeat([1, 2, 3, 4], 50)
    score = yc + rng.uniform(-0.3, 0.3, len(yc))                # perfectly separable at .5
    th = S.tune_thresholds(yc, score)
    assert th == sorted(th) and len(th) == 3
    pred = np.digitize(score, th) + 1
    assert (pred == yc).all()
    for t, want in zip(th, (1.5, 2.5, 3.5)):
        assert abs(t - want) < 0.25


def test_tune_thresholds_shift_follows_a_biased_score():
    yc = np.repeat([1, 2, 3, 4], 40)
    score = yc + 0.4                                            # model reads 0.4 too high
    th = S.tune_thresholds(yc, score)
    assert (np.digitize(score, th) + 1 == yc).all()
    # every cut lies between the (shifted) class scores it separates
    assert 1.4 < th[0] <= 2.4 and 2.4 < th[1] <= 3.4 and 3.4 < th[2] <= 4.2


def test_tune_thresholds_respects_sample_weight():
    # two frames disagree; the heavy one must win the boundary placement
    yc = np.array([1] * 20 + [2] * 20 + [3] * 20 + [4] * 20 + [2, 3])
    score = np.r_[np.repeat([1.0, 2.0, 3.0, 4.0], 20), 2.55, 2.45]
    w_heavy_2 = np.r_[np.ones(80), 50.0, 1.0]
    th = S.tune_thresholds(yc, score, sample_weight=w_heavy_2)
    assert np.digitize(2.55, th) + 1 == 2


# --- nested CV: the leakage guard ---------------------------------------------

def _ridge():
    return Ridge(alpha=1.0)


def test_nested_cv_cut_points_never_see_the_test_fold_labels():
    """Each fold's cut-points must be exactly what tuning on its TRAINING
    frames' inner spatial OOF gives, and its test scores what a model fitted
    on the training frames alone predicts — rebuilt here independently."""
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    res = S.nested_spatial_cv(X, y, yc, g, _ridge, return_inner=True)
    for k, (tr, te) in enumerate(S.spatial_folds(yc, g)):
        assert not set(g[tr]) & set(g[te])
        ioof = np.zeros(len(tr))
        for itr, ite in S.spatial_folds(yc[tr], g[tr], S.INNER_SPLITS):
            assert not set(g[tr][itr]) & set(g[tr][ite])       # inner folds spatial too
            ioof[ite] = S._fit_predict(_ridge, X[tr][itr], y[tr][itr], X[tr][ite])
        assert np.allclose(res["inner"][k][1], ioof)
        assert res["thresholds"][k] == S.tune_thresholds(yc[tr], ioof)
        assert np.allclose(res["oof"][te], S._fit_predict(_ridge, X[tr], y[tr], X[te]))
        assert np.array_equal(res["pred"][te],
                              np.digitize(res["oof"][te], res["thresholds"][k]) + 1)


def test_nested_cv_output_shapes_and_quality_on_learnable_data():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    res = S.nested_spatial_cv(X, y, yc, g, _ridge)
    assert res["oof"].shape == y.shape and set(res["pred"]) <= {1, 2, 3, 4}
    assert set(res["fold"]) == set(range(S.N_SPLITS))
    assert len(res["thresholds"]) == S.N_SPLITS
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    assert m["qwk"] > 0.8                                      # the signal is easy


def test_nested_cv_without_tuning_uses_half_rounding():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    res = S.nested_spatial_cv(X, y, yc, g, _ridge, tune=False)
    assert all(t == [1.5, 2.5, 3.5] for t in res["thresholds"])


# --- metrics + bootstraps -----------------------------------------------------

def test_ordinal_metrics_perfect_and_bad_road_definition():
    yc = np.array([1, 2, 3, 4, 1, 4])
    m = S.ordinal_metrics(yc, yc, yc.astype(float))
    assert (m["qwk"], m["mae"], m["exact"], m["off1"], m["bad_acc"], m["bad_auc"]) \
        == (1.0, 0.0, 1.0, 1.0, 1.0, 1.0)
    assert S.BAD_FROM == 3                                     # severity >= 3 = bad road
    m2 = S.ordinal_metrics(yc, np.array([2, 2, 3, 3, 2, 3]), yc.astype(float))
    assert m2["mae"] == pytest.approx(4 / 6) and m2["off1"] == 1.0


def test_paired_bootstrap_zero_for_identical_and_positive_for_better():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    good = {"oof": y.astype(float), "pred": yc}
    rng = np.random.default_rng(3)
    noisy_score = y + rng.normal(0, 0.9, len(y))
    bad = {"oof": noisy_score, "pred": np.clip(np.round(noisy_score), 1, 4).astype(int)}
    same = S.paired_bootstrap_delta(yc, good, good, g, n_boot=100)
    assert all(v == (0.0, 0.0, 0.0) for v in same.values())
    d = S.paired_bootstrap_delta(yc, bad, good, g, n_boot=200)
    assert d["qwk"][0] > 0 and d["qwk"][1] > 0                 # CI excludes 0
    assert d["mae"][0] < 0


def test_cluster_bootstrap_ci_brackets_the_estimate():
    lat, lon, X, y, yc = synthetic()
    g = S.grid_cells(lat, lon)
    rng = np.random.default_rng(4)
    s = y + rng.normal(0, 0.5, len(y))
    res = {"oof": s, "pred": np.clip(np.round(s), 1, 4).astype(int)}
    point = S.ordinal_metrics(yc, res["pred"], res["oof"])["qwk"]
    lo, hi = S.cluster_bootstrap_ci(yc, res, g, n_boot=200)["qwk"]
    assert lo <= point <= hi and hi - lo > 0
