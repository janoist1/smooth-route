"""Tests for the pure parts of ml/retrain.py (no DB, no torch, no images).

Run: .venv/bin/python -m pytest -q ml/tests/test_retrain.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import retrain as R  # noqa: E402


def _labels(rows):
    return pd.DataFrame(rows, columns=["image_filename", "manual_rqi", "tags", "svi_id"])


def test_build_manifest_rounds_filters_and_dedups():
    lab = _labels([("a.jpg", 1.5, None, 1), ("b.jpg", 4.5, None, 2), ("c.jpg", None, None, 3),
                   ("d.jpg", 2.0, None, 4), ("a.jpg", 2.4, None, 1), ("gone.jpg", 3.0, None, 5)])
    m = R.build_manifest(lab, lambda f: f != "gone.jpg")
    assert list(m["image_filename"]) == ["b.jpg", "d.jpg", "a.jpg"]   # last label of a.jpg wins
    assert list(m["rqi"]) == [4, 2, 2]                                # 4.5 -> 4 (half to even), 2.4 -> 2
    assert list(m.columns) == ["image_filename", "manual_rqi", "rqi", "tags", "svi_id"]


def test_build_manifest_without_svi_id_column():
    lab = pd.DataFrame({"image_filename": ["a.jpg"], "manual_rqi": [3.0], "tags": [None]})
    m = R.build_manifest(lab, lambda f: True)
    assert m["svi_id"].isna().all()


def test_diff_labels():
    old = pd.DataFrame({"image_filename": ["a", "b", "c"], "manual_rqi": [1.0, 2.0, 3.0]})
    new = pd.DataFrame({"image_filename": ["a", "b", "d"], "manual_rqi": [1.0, 2.5, 4.0]})
    d = R.diff_labels(old, new)
    assert d == {"new": ["d"], "changed": ["b"], "removed": ["c"]}


def test_orientation_check_catches_a_flipped_export():
    old = pd.DataFrame({"image_filename": [f"f{i}" for i in range(60)],
                        "manual_rqi": np.tile([1, 2, 3, 4], 15).astype(float)})
    same = old.copy()
    flipped = old.assign(manual_rqi=6 - old["manual_rqi"])
    assert R.orientation_check(old, same)[0]
    ok, rho, n = R.orientation_check(old, flipped)
    assert not ok and rho < -0.9 and n == 60
    ok, rho, n = R.orientation_check(old, flipped.head(10))   # too little overlap to judge
    assert ok and rho is None and n == 10


def _old_cache(files):
    n = len(files)
    rng = np.random.default_rng(0)
    return {"files": files, "feats": {k: rng.normal(size=(n, R.DIM)).astype(np.float32)
                                      for k in R.DINO_KEYS},
            "clip": rng.normal(size=(n, 512)).astype(np.float32),
            "road_prob": np.linspace(0.6, 0.9, n)}


def test_assemble_features_sources():
    old = _old_cache(["a.jpg", "b.jpg"])
    man = pd.DataFrame({"image_filename": ["b.jpg", "new1.jpg", "new2.jpg", "new3.jpg"],
                        "svi_id": [np.nan, 11, 12, np.nan]})
    ff = {"ids": np.array([11, 12]), "cls": np.ones((2, R.DIM), np.float32),
          "patch": np.full((2, R.DIM), 2, np.float32)}
    feats, clip, rp, src, todo = R.assemble_features(man, old, ff, {11: 0.97})
    assert src == ["cache", "frame_feats", "extract", "extract"]
    assert todo == [2, 3]                       # 12 has no road_prob, new3 has no frame id
    np.testing.assert_array_equal(feats["cls"][0], old["feats"]["cls"][1])
    np.testing.assert_array_equal(clip[0], old["clip"][1])
    assert rp[0] == old["road_prob"][1] and rp[1] == 0.97
    assert (feats["cls"][1] == 1).all() and (feats["patch"][1] == 2).all()
    assert np.isnan(feats["cls_flip"][1]).all() and np.isnan(clip[1]).all()   # unused by cls+patch
    assert np.isnan(feats["cls"][2]).all() and np.isnan(rp[3])


def test_assemble_features_without_frame_feats():
    old = _old_cache([])
    man = pd.DataFrame({"image_filename": ["x.jpg"], "svi_id": [5]})
    *_, src, todo = R.assemble_features(man, old, None, {5: 0.9})
    assert src == ["extract"] and todo == [0]


def test_masked_nested_cv_uses_only_masked_rows_for_fitting():
    import spatial_cv as S
    rng = np.random.default_rng(1)
    n = 400
    yc = np.tile([1, 2, 3, 4], n // 4)
    X = (yc[:, None] + rng.normal(scale=0.3, size=(n, 3))).astype(float)
    y = yc.astype(float)
    groups = np.repeat(np.arange(40), 10)
    rng.shuffle(groups)

    from sklearn.linear_model import Ridge
    full = R.masked_nested_cv(X, y, yc, groups, lambda: Ridge(alpha=1.0), np.ones(n, bool))
    ref = S.nested_spatial_cv(X, y, yc, groups, lambda: Ridge(alpha=1.0))
    np.testing.assert_allclose(full["oof"], ref["oof"])          # full mask == official CV
    np.testing.assert_array_equal(full["pred"], ref["pred"])

    # A mask that hides every class-4 row: the model can no longer reach 4.
    part = R.masked_nested_cv(X, y, yc, groups, lambda: Ridge(alpha=1.0), yc != 4)
    np.testing.assert_array_equal(part["fold"], full["fold"])    # same test folds -> paired
    assert part["oof"][yc == 4].mean() < full["oof"][yc == 4].mean()


def test_verdict():
    good = {"qwk": (0.01, -0.005, 0.03)}
    assert R.verdict(False, good)[0] is False
    assert R.verdict(True, None)[0] is False
    assert R.verdict(True, good, n_new=10, min_new=50)[0] is False
    assert R.verdict(True, good, n_new=80, min_new=50)[0] is True
    assert R.verdict(True, {"qwk": (-0.001, -0.01, 0.01)})[0] is False   # worse point estimate
    assert R.verdict(True, {"qwk": (0.02, -0.03, 0.06)})[0] is False     # too uncertain on the downside
