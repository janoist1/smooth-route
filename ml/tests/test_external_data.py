"""Tests for ml/external_data.py and ml/scene_bias.py (Era 16): label mapping
through the scale helpers, the CV harness with external rows (never scored,
cut-points from our labels only) and the road-type weights. Synthetic data,
no torch, no images.

Run: .venv/bin/python -m pytest -q ml/tests/test_external_data.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import external_data as X  # noqa: E402
import rqi_scale as R  # noqa: E402
import scene_bias as SB  # noqa: E402
import spatial_cv as S  # noqa: E402


def test_import_does_not_pull_torch():
    for mod in (X, SB):
        src = open(mod.__file__).read()
        assert "import torch" not in src and "from transformers" not in src


def test_osm_mapping_follows_the_scale():
    words = ["excellent", "good", "intermediate", "bad", "very_bad"]
    sev = [X.osm_to_severity(w) for w in words]
    assert sev == sorted(sev) and len(set(sev)) == 5          # best -> worst, distinct
    assert sev[0] == R.MIN_LEVEL and sev[-1] == R.MAX_LEVEL
    assert sev[-1] in R.DROPPED_LEVELS                         # very_bad = untrained level
    assert all(s in R.MODEL_LEVELS for s in sev[:-1])
    assert X.osm_to_severity("bad") >= R.BAD_FROM > X.osm_to_severity("good")


def _lab(n=240, d=6, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(1, 5, n).astype(float)
    Xf = rng.normal(size=(n, d)) + y[:, None] * 0.8
    lat = 47.0 + rng.integers(0, 6, n) * 0.012 + rng.uniform(0, 0.005, n)
    lon = 19.0 + rng.integers(0, 6, n) * 0.016 + rng.uniform(0, 0.005, n)
    lab = {"X": Xf, "y": y, "yc": y.astype(int), "lat": lat, "lon": lon,
           "area": np.array([X.AREAS[i % 4] for i in range(n)], dtype=object)}
    lab["groups"] = S.grid_cells(lat, lon)
    lab["bbox"] = np.zeros(n, bool)
    lab["bbox"][:60] = True
    return lab


def test_run_cv_scores_every_frame_once_and_ignores_test_labels():
    lab = _lab()
    rng = np.random.default_rng(1)
    ext = (rng.normal(size=(50, 6)) + 2.0, rng.integers(1, 5, 50).astype(float),
           np.full(50, 0.5))
    res = X.run_cv(lab, "spatial", ext=ext, n_jobs=1)
    assert sorted(res["test"]) == list(range(len(lab["y"])))  # each frame tested once
    assert len(res["thresholds"]) == S.N_SPLITS
    # leakage guard: scrambling the test fold's labels must not change its predictions
    folds = X.make_folds(lab, "spatial")
    te = folds[0][1]
    lab2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in lab.items()}
    lab2["y"][te] = 5 - lab2["y"][te]
    lab2["yc"][te] = lab2["y"][te].astype(int)
    # (folds depend on yc via stratification; reuse the same folds by patching)
    orig = X.make_folds
    X.make_folds = lambda _lab, _kind: folds
    try:
        res2 = X.run_cv(lab2, "spatial", ext=ext, n_jobs=1)
    finally:
        X.make_folds = orig
    np.testing.assert_allclose(res["oof"][te], res2["oof"][te])


def test_ext_only_and_domain_heads_run():
    lab = _lab()
    rng = np.random.default_rng(2)
    ext = (rng.normal(size=(80, 6)) + lab["y"][:80, None] * 0.8, lab["y"][:80].copy(),
           np.ones(80))
    r1 = X.run_cv(lab, "loro", ext=ext, ext_only=True, n_jobs=1)
    r2 = X.run_cv(lab, "bp_bbox", ext=ext, dom=20.0, n_jobs=1)
    assert np.isfinite(r1["oof"]).all() and len(r2["test"]) == 60
    h = X.Head(dom=20.0).fit(lab["X"], lab["y"], d=np.zeros(len(lab["y"])))
    assert h.predict(lab["X"][:3]).shape == (3,)


def test_road_type_weights_balance_the_class_mix():
    lab = _lab()
    rt = np.where(lab["yc"] <= 2, "motorway", "urban")       # road type = proxy for class
    rt[::7] = "urban"
    w = SB.road_type_weights(lab, rt)(np.arange(len(rt)))
    assert np.isclose(w.mean(), 1.0) and w.min() >= 0 and np.isfinite(w).all()
    # rare (class, road type) combinations get more weight than common ones
    rare = (rt == "urban") & (lab["yc"] <= 2)
    common = (rt == "motorway") & (lab["yc"] <= 2)
    assert w[rare].mean() > w[common].mean()
