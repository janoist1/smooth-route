"""Tests for ml/motorway_vlm.py (Era 17): the motorway-only correction head
keeps the champion score on every other frame, skips the correction without
enough motorway rows, and the level constants come from the scale. Synthetic
data, no torch, no DB.

Run: .venv/bin/python -m pytest -q ml/tests/test_motorway_vlm.py
"""
import os
import sys

import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import motorway_vlm as M  # noqa: E402
import rqi_scale as R  # noqa: E402


def _data(n=300, nb=8, na=3, n_mw=80, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(1, 5, n).astype(float)
    Xb = rng.normal(size=(n, nb)) + y[:, None] * 0.5
    A = rng.normal(size=(n, na)) + y[:, None] * 0.3
    m = np.zeros(n)
    m[:n_mw] = 1
    return np.hstack([Xb, A, m[:, None]]), y, nb


def test_levels_come_from_the_scale():
    assert M.KIVALO == R.MIN_LEVEL and M.KIVALO < M.JO < R.BAD_FROM
    assert set(M.MOTORWAY) == {"motorway", "motorway_link", "trunk", "trunk_link"}


def test_correction_leaves_other_frames_on_the_champion_score():
    X, y, nb = _data()
    head = M.MotorwayCorrection(n_base=nb).fit(X, y)
    assert head.ridge_ is not None
    sc = StandardScaler().fit(X[:, :nb])
    champ = SVR(C=1.0, gamma="scale", epsilon=0.05).fit(sc.transform(X[:, :nb]), y)
    other = X[:, -1] < 0.5
    np.testing.assert_allclose(head.predict(X[other]),
                               champ.predict(sc.transform(X[other, :nb])), atol=1e-9)
    assert not np.allclose(head.predict(X[~other]),
                           champ.predict(sc.transform(X[~other, :nb])))


def test_no_correction_without_enough_motorway_rows():
    X, y, nb = _data(n_mw=10)
    head = M.MotorwayCorrection(n_base=nb, min_rows=30).fit(X, y)
    assert head.ridge_ is None
    assert np.isfinite(head.predict(X)).all()
