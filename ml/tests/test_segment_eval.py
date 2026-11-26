"""Tests for the pure parts of ml/segment_eval.py (chains, segments,
aggregation, segment truth, nested cut-points, confidence). Synthetic frames
only: no caches, no torch, no images.

Run: .venv/bin/python -m pytest -q ml/tests/test_segment_eval.py
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import segment_eval as E  # noqa: E402
import spatial_cv as S  # noqa: E402

M_LAT = 1 / 111_320.0
M_LON = 1 / (111_320.0 * np.cos(np.radians(47.0)))


def track(n, step_m=10.0, start=(47.0, 19.0), heading="north", source="track", seq0=0):
    lat0, lon0 = start
    d = np.arange(n) * step_m
    lat = lat0 + (d * M_LAT if heading == "north" else 0)
    lon = lon0 + (d * M_LON if heading == "east" else 0)
    return pd.DataFrame({"lat": lat, "lon": lon, "seq": seq0 + np.arange(n),
                         "coord_source": source})


def frames(df, cell=0, fold=0, labels=None, area="tapolca"):
    df = df.reset_index(drop=True).copy()
    df["cell"] = cell
    df["fold"] = fold
    df["area"] = area
    df["human_rqi"] = labels if labels is not None else 2
    return df


# --- chains ---------------------------------------------------------------------

def test_one_straight_track_is_one_chain_with_10m_footprints():
    fr = frames(track(20))
    chain, pos, fp, rank = E.build_chains(fr)
    assert len(set(chain)) == 1
    assert np.allclose(fp, 10.0, atol=0.05)
    assert pos[rank.argsort()][-1] == pytest.approx(190.0, abs=0.5)


def test_chain_breaks_at_gap_cell_turn_and_source():
    a = track(10)                                               # 0..90 m north
    gap = track(5, start=(47.0 + 200 * M_LAT, 19.0), seq0=10)   # jump of ~110 m
    fr = frames(pd.concat([a, gap]))
    assert len(set(E.build_chains(fr)[0])) == 2                # gap > GAP_M

    fr = frames(track(10))
    fr.loc[5:, "cell"] = 1                                      # crosses a CV cell
    assert len(set(E.build_chains(fr)[0])) == 2

    north = track(6)
    east = track(6, start=(47.0 + 50 * M_LAT, 19.0 + 10 * M_LON), heading="east", seq0=6)
    fr = frames(pd.concat([north, east]))                       # 90-degree corner
    assert len(set(E.build_chains(fr)[0])) == 2

    fr = frames(pd.concat([track(5), track(5, start=(47.0 + 50 * M_LAT, 19.0),
                                                source="other", seq0=5)]))
    assert len(set(E.build_chains(fr)[0])) == 2                # different collection track


def test_isolated_frame_gets_the_nominal_footprint():
    fr = frames(pd.concat([track(5), track(1, start=(47.01, 19.0), seq0=5)]))
    chain, pos, fp, rank = E.build_chains(fr)
    assert fp[-1] == E.NOMINAL_STEP_M


# --- segments -------------------------------------------------------------------

def test_cut_segments_lengths_and_dense_ids():
    fr = frames(track(60))                                      # ~600 m
    chain, pos, fp, rank = E.build_chains(fr)
    seg = E.cut_segments(chain, fp, rank, 200)
    assert sorted(set(seg)) == [0, 1, 2]                        # round(600/200) pieces
    sizes = np.bincount(seg)
    assert sizes.min() >= 19 and sizes.max() <= 21
    assert np.array_equal(E.cut_segments(chain, fp, rank, None), np.arange(len(fr)))
    # phases keep the piece count and contiguity (ids 0..k-1, no holes)
    for ph in E.PHASES:
        s = E.cut_segments(chain, fp, rank, 200, ph)
        assert sorted(set(s)) == list(range(len(set(s))))
        assert 2 <= len(set(s)) <= 4
        assert (np.diff(s[rank.argsort()]) >= 0).all()          # monotone along the chain


def test_short_chain_is_one_segment():
    fr = frames(track(4))                                       # 40 m
    chain, pos, fp, rank = E.build_chains(fr)
    assert set(E.cut_segments(chain, fp, rank, 200)) == {0}


# --- segment truth + table --------------------------------------------------------

@pytest.mark.parametrize("labels,expected", [
    ([2, 2, 3], 2),          # plain median
    ([1, 2, 3, 4], 3),       # half-way 2.5, mean 2.5 >= median -> worse class
    ([1, 1, 2, 4], 2),       # half-way 1.5, mean 2.0 >= 1.5 -> towards the mean (2)
    ([2, 3, 3, 3], 3),
    ([1, 2], 2),             # exact tie goes to the worse class
])
def test_median_class_tie_rules(labels, expected):
    assert E.median_class(np.array(labels)) == expected


def test_segment_table_truth_purity_and_one_fold_per_segment():
    fr = frames(track(30), labels=np.r_[[1] * 10, [3] * 20])
    chain, pos, fp, rank = E.build_chains(fr)
    seg = E.cut_segments(chain, fp, rank, 100)
    st = E.segment_table(seg, fr, fp)
    assert list(st["gt"]) == [1, 3, 3]
    assert st["n"].sum() == 30 and (st["fold"] == 0).all()
    assert st["purity"].iloc[0] == 1.0
    bad = fr.copy()
    bad.loc[3, "fold"] = 1                                      # a segment straddling folds
    with pytest.raises(AssertionError):
        E.segment_table(seg, bad, fp)


# --- aggregation ------------------------------------------------------------------

def test_aggregators():
    v = np.array([1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 10.0, 3.0, 3.0])
    seg = np.array([0] * 10 + [1, 1])
    assert list(E.aggregate(v, seg, "median_score")) == [2.0, 3.0]
    assert list(E.aggregate(v, seg, "mean_score")) == [2.7, 3.0]
    tm = E.aggregate(v, seg, "trimmed_mean_score")[0]
    assert tm == pytest.approx(2.0)                             # TRIM 0.2 cuts 1.0 and 10.0
    with pytest.raises(ValueError):
        E.aggregate(v, seg, "nonsense")


def test_majority_vote_breaks_ties_towards_the_mean():
    cls = np.array([1, 1, 3, 3, 4, 2, 2, 2])
    seg = np.array([0, 0, 0, 0, 0, 1, 1, 1])
    out = E.majority(cls, seg)
    assert out[1] == 2
    assert out[0] == 3                                          # 1 and 3 tie; mean 2.4 -> 3


def test_iqr_definition_matches_numpy_linear_percentiles():
    assert E.iqr_of([5.0]) == 0.0
    assert E.iqr_of([1, 2, 3, 4]) == pytest.approx(1.5)


# --- nested cut-points --------------------------------------------------------------

def test_nested_cutpoints_ignore_the_test_fold():
    rng = np.random.default_rng(0)
    n = 400
    gt = rng.integers(1, 5, n)
    fold = np.arange(n) % S.N_SPLITS
    w = np.ones(n)
    agg_in = [gt + rng.normal(0, 0.2, n) for _ in range(S.N_SPLITS)]
    ths = E.nested_cutpoints([(gt, w, fold, agg_in)])
    # scramble fold 0's units in its own inner array: fold 0's cut-points stay
    agg2 = [a.copy() for a in agg_in]
    agg2[0][fold == 0] = 9.9
    assert E.nested_cutpoints([(gt, w, fold, agg2)])[0] == ths[0]
    pred = E.apply_cutpoints(gt.astype(float), fold, ths)
    assert (pred == gt).mean() > 0.95


# --- confidence -----------------------------------------------------------------------

def test_confidence_is_monotone_in_frames_spread_and_margin():
    p = {"n_ref": 0.5, "spread_ref": 2.0, "margin_ref": 0.6}
    assert E.confidence(10, 0.1, 0.5, **p) > E.confidence(1, 0.1, 0.5, **p)
    assert E.confidence(10, 0.1, 0.5, **p) > E.confidence(10, 1.5, 0.5, **p)
    assert E.confidence(10, 0.1, 0.5, **p) > E.confidence(10, 0.1, 0.05, **p)
    assert 0.0 <= float(E.confidence(0, 9, 0, **p)) <= 1.0
    # the margin term never drops below one half
    assert float(E.confidence(1e6, 0.0, 0.0, **p)) == pytest.approx(0.5)


def test_segment_row_reports_errors_and_margin():
    r = E.segment_row(np.array([2.9, 3.1, 3.0]), [1.5, 2.5, 3.5], gt=3,
                      lab_mean=3.0, kind="median_score")
    assert (r["pred"], r["correct"], r["err"], r["n"]) == (3, 1.0, 0, 3)
    assert r["margin"] == pytest.approx(0.5)
    assert r["bad_wrong"] == 0.0
