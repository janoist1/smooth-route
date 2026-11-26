"""Tests for the pure parts of ml/pairwise_pilot.py (no images, no DB).

Run: .venv/bin/python -m pytest -q ml/tests/test_pairwise_pilot.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pairwise_pilot as pp  # noqa: E402


def test_worse_side_uses_higher_is_worse():
    # Training numbering: 1 = best, 4 = worst; model scores the same way.
    assert pp.worse_side(4, 2) == "A"
    assert pp.worse_side(1, 3) == "B"
    assert pp.worse_side(2, 2) == "equal"
    assert pp.worse_side(2.91, 2.90) == "A"
    assert pp.worse_side(None, 2) is None
    assert pp.worse_side(float("nan"), 2) is None


def test_accuracy_counts_equal_as_wrong_and_skips_human_ties():
    rows = [
        {"human": "A", "j": "A"},
        {"human": "B", "j": "equal"},
        {"human": "B", "j": "A"},
        {"human": "equal", "j": "A"},  # human tie: not part of the accuracy
        {"human": "A", "j": None},  # unanswered
    ]
    acc = pp.accuracy(rows, "j")
    assert acc["n"] == 3
    assert acc["exact"] == round(1 / 3, 3)
    assert acc["decided"] == round(2 / 3, 3)
    assert acc["among_decided"] == 0.5


def test_wilson_interval_brackets_the_rate():
    lo, hi = pp.wilson(85, 100)
    assert lo < 0.85 < hi
    assert 0.76 < lo < 0.78 and 0.90 < hi < 0.92
    assert all(math.isnan(x) for x in pp.wilson(0, 0))


def test_haversine_roughly_one_km_per_0009_deg_lat():
    assert 990 < pp.haversine_m(47.0, 19.0, 47.009, 19.0) < 1010


def test_nearest_cut_picks_the_closest_threshold():
    cuts = [2.466, 3.175]
    assert pp.nearest_cut(2.5, cuts) == (2.466, pytest_approx(0.034))
    cut, dist = pp.nearest_cut(3.0, cuts)
    assert cut == 3.175 and round(dist, 3) == 0.175


def test_budapest_bbox_excludes_the_city_only():
    assert pp.in_bbox(47.4979, 19.0402)  # Deák tér
    assert not pp.in_bbox(46.9, 17.9)  # Balaton
    assert not pp.in_bbox(47.19, 18.41)  # Székesfehérvár


def pytest_approx(x):
    import pytest

    return pytest.approx(x, abs=1e-6)
