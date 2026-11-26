"""Route summary: matching a path to segments and the length bookkeeping."""
import pytest

from app.services.route_quality import (
    SegmentRef,
    compute_route_stats,
    worst_segment_ids,
)
from app.services.segment_aggregation import config_from_dict
from geo_helpers import FLIPPED_CONFIG, at, make_config

SCALE = make_config().scale


def seg(id, x0, x1, rqi, score, north=0.0):
    """An east-west segment from x0 to x1 metres, optionally shifted north."""
    return SegmentRef(id=id, coords=[at(x0, north), at(x1, north)], rqi=rqi, score=score,
                      length_m=abs(x1 - x0))


# 600 m of road: good, then bad, then a 150 m gap, then fair.
ROAD = [
    seg("a", 0, 150, 1, 1.2),
    seg("b", 150, 300, 4, 3.6),
    seg("d", 450, 600, 2, 2.0),
]


def test_stats_along_a_partly_covered_route():
    # Starts at x=1 so no sample midpoint sits exactly on the end-slack limit.
    stats = compute_route_stats([at(1, 2), at(601, 2)], ROAD, SCALE)
    assert stats.total_length_m == pytest.approx(600, abs=0.5)
    # 450 m of segments; each gap end may add the end slack plus one sample.
    assert 445 <= stats.covered_length_m <= 475
    assert stats.length_by_rqi[0] == pytest.approx(150, abs=12)
    assert stats.length_by_rqi[1] == pytest.approx(150, abs=12)
    assert stats.length_by_rqi[2] == 0.0
    assert stats.length_by_rqi[3] == pytest.approx(150, abs=12)
    assert sum(stats.length_by_rqi) == pytest.approx(stats.covered_length_m)
    # Length-weighted: three equal stretches.
    assert stats.mean_score == pytest.approx((1.2 + 3.6 + 2.0) / 3, abs=0.05)
    assert set(stats.matched_m) == {"a", "b", "d"}


def test_mean_score_is_length_weighted():
    segments = [seg("long", 0, 300, 2, 2.0), seg("short", 300, 400, 4, 4.0)]
    stats = compute_route_stats([at(0, 0), at(400, 0)], segments, SCALE)
    assert stats.mean_score == pytest.approx((300 * 2.0 + 100 * 4.0) / 400, abs=0.03)


def test_route_outside_the_buffer_is_uncovered():
    stats = compute_route_stats([at(0, 30), at(600, 30)], ROAD, SCALE)      # 30 m away
    assert stats.total_length_m == pytest.approx(600, abs=0.5)
    assert stats.covered_length_m == 0.0
    assert stats.mean_score is None
    assert stats.length_by_rqi == [0.0, 0.0, 0.0, 0.0]
    # ...and 14 m away is still inside the 15 m buffer.
    assert compute_route_stats([at(0, 14), at(600, 14)], ROAD, SCALE).covered_length_m > 400


def test_crossing_street_does_not_count():
    # The route drives north across the east-west road: wrong direction.
    stats = compute_route_stats([at(75, -100), at(75, 100)], ROAD, SCALE)
    assert stats.covered_length_m == 0.0


def test_driving_the_other_way_matches_too():
    stats = compute_route_stats([at(601, -3), at(1, -3)], ROAD, SCALE)
    # 450 m of segments; each gap end may add the end slack plus one sample.
    assert 445 <= stats.covered_length_m <= 475


def test_segments_without_data_are_ignored():
    empty = SegmentRef(id="c", coords=[at(300, 0), at(450, 0)], rqi=None, score=None, length_m=150)
    stats = compute_route_stats([at(1, 0), at(601, 0)], ROAD + [empty], SCALE)
    assert "c" not in stats.matched_m
    assert 445 <= stats.covered_length_m <= 475


def test_a_data_gap_is_not_credited_by_the_buffer():
    # 300 m route, a segment only over its middle 100 m: the 15 m buffer must
    # not stretch that to 130 m (flat ends, a few metres of slack at most).
    middle = seg("m", 100, 200, 3, 2.8)
    stats = compute_route_stats([at(1, 0), at(301, 0)], [middle], SCALE)
    assert 95 <= stats.covered_length_m <= 121      # not 130


def test_empty_inputs():
    assert compute_route_stats([], ROAD, SCALE).total_length_m == 0.0
    assert compute_route_stats([at(0, 0)], ROAD, SCALE).total_length_m == 0.0
    stats = compute_route_stats([at(0, 0), at(100, 0)], [], SCALE)
    assert (stats.total_length_m, stats.covered_length_m, stats.mean_score) == (
        pytest.approx(100, abs=0.1), 0.0, None)


def test_route_with_a_bend_follows_both_legs():
    segments = [
        SegmentRef("east", [at(0, 0), at(200, 0)], 2, 2.1, 200),
        SegmentRef("north", [at(200, 0), at(200, 200)], 3, 2.9, 200),
    ]
    stats = compute_route_stats([at(0, 0), at(200, 0), at(200, 200)], segments, SCALE)
    assert stats.covered_length_m == pytest.approx(400, abs=1)
    assert stats.matched_m["east"] == pytest.approx(200, abs=10)
    assert stats.matched_m["north"] == pytest.approx(200, abs=10)


def test_worst_segments_sorted_by_score_and_limited():
    segments = [seg(f"s{i}", i * 100, (i + 1) * 100, 2, 1.0 + i * 0.4) for i in range(8)]
    stats = compute_route_stats([at(0, 0), at(800, 0)], segments, SCALE)
    worst = worst_segment_ids(stats, segments, SCALE)
    assert worst == ["s7", "s6", "s5", "s4", "s3"]
    assert worst_segment_ids(stats, segments, SCALE, limit=2) == ["s7", "s6"]


def test_worst_segments_respect_the_eligible_set():
    stats = compute_route_stats([at(0, 0), at(600, 0)], ROAD, SCALE)
    assert worst_segment_ids(stats, ROAD, SCALE) == ["b", "d", "a"]
    # "b" has low confidence → excluded by the caller's filter.
    assert worst_segment_ids(stats, ROAD, SCALE, eligible={"a", "d"}) == ["d", "a"]
    assert worst_segment_ids(stats, ROAD, SCALE, eligible=set()) == []


def test_worst_segments_skip_barely_touched_segments():
    # The route only drives the first 10 m of a 150 m bad segment.
    stats = compute_route_stats([at(-99, 0), at(11, 0)], [seg("bad", 0, 150, 4, 3.9)], SCALE)
    assert 10 - 1e-6 <= stats.matched_m["bad"] <= 20 + 1e-6
    assert worst_segment_ids(stats, [seg("bad", 0, 150, 4, 3.9)], SCALE) == []
    # A short segment driven end to end does qualify.
    short = seg("short", 0, 12, 4, 3.9)
    stats = compute_route_stats([at(-50, 0), at(50, 0)], [short], SCALE)
    assert worst_segment_ids(stats, [short], SCALE) == ["short"]


def test_length_by_rqi_always_sums_to_the_covered_length():
    stats = compute_route_stats([at(1, 2), at(601, 2)], ROAD, SCALE)
    assert len(stats.length_by_rqi) == 4
    assert sum(stats.length_by_rqi) == pytest.approx(stats.covered_length_m, abs=1e-9)


def test_segment_with_an_unknown_class_is_not_coverage():
    odd = SegmentRef(id="odd", coords=[at(0, 0), at(150, 0)], rqi=9, score=2.0, length_m=150)
    stats = compute_route_stats([at(0, 0), at(150, 0)], [odd], SCALE)
    assert stats.covered_length_m == 0.0 and stats.mean_score is None
    assert sum(stats.length_by_rqi) == 0.0


def test_flipped_scale_reverses_worst_and_reindexes_classes():
    """After the scale flip (5 = excellent) the lowest score is the worst and
    lengthByRqi is indexed by the classes 2, 3, 4, 5."""
    flipped = config_from_dict(FLIPPED_CONFIG).scale
    road = [
        seg("a", 0, 150, 5, 4.8),       # excellent
        seg("b", 150, 300, 2, 2.4),     # poor
        seg("d", 450, 600, 4, 4.0),     # good
    ]
    stats = compute_route_stats([at(1, 2), at(601, 2)], road, flipped)
    assert len(stats.length_by_rqi) == 4
    assert stats.length_by_rqi[0] > 100          # class 2
    assert stats.length_by_rqi[1] == 0.0         # class 3
    assert stats.length_by_rqi[2] > 100          # class 4
    assert stats.length_by_rqi[3] > 100          # class 5
    assert sum(stats.length_by_rqi) == pytest.approx(stats.covered_length_m)
    assert worst_segment_ids(stats, road, flipped) == ["b", "d", "a"]
