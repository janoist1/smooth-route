"""Snapping points to lines: distance limit, bearing rule, linear reference."""
import pytest

from app.services.map_matching import LineIndex
from geo_helpers import FakeLine, at

# An east-west street and a north-south street crossing at the origin.
EAST_WEST = FakeLine(1, [at(-200, 0), at(0, 0), at(200, 0)])
NORTH_SOUTH = FakeLine(2, [at(0, -200), at(0, 200)])


def test_snaps_to_the_nearest_line_within_range():
    index = LineIndex([EAST_WEST, NORTH_SOUTH])
    match = index.snap(at(120, 6), heading=90)
    assert match.line_id == 1
    assert match.distance_m == pytest.approx(6, abs=0.05)
    assert match.offset_m == pytest.approx(320, abs=0.2)     # 200 m edge + 120 m
    assert match.bearing_diff == pytest.approx(0, abs=0.05)


def test_too_far_is_unmatched():
    index = LineIndex([EAST_WEST])
    assert index.snap(at(50, 19.5), heading=90) is not None
    assert index.snap(at(50, 20.5), heading=90) is None
    assert index.snap(at(50, 8), heading=90, max_distance_m=5) is None


def test_bearing_rule_picks_the_road_we_drive_on_at_a_junction():
    index = LineIndex([EAST_WEST, NORTH_SOUTH])
    # 3 m from the N-S street, 8 m from the E-W one — but heading east.
    match = index.snap(at(3, 8), heading=92)
    assert match.line_id == 1
    # Same spot, heading north → the N-S street.
    assert index.snap(at(3, 8), heading=5).line_id == 2


def test_both_travel_directions_merge():
    index = LineIndex([EAST_WEST])
    assert index.snap(at(50, 4), heading=90).line_id == 1
    assert index.snap(at(50, 4), heading=270).line_id == 1     # driving back
    assert index.snap(at(50, 4), heading=300).line_id == 1     # 30° off the axis


def test_incompatible_bearing_is_unmatched_even_when_close():
    index = LineIndex([EAST_WEST])
    assert index.snap(at(50, 1), heading=0) is None            # perpendicular
    assert index.snap(at(50, 1), heading=44) is None           # 46° off the axis
    assert index.snap(at(50, 1), heading=46) is not None       # 44° off the axis
    assert index.snap(at(50, 1), heading=0, max_bearing_diff_deg=91) is not None


def test_no_heading_means_nearest_line_wins():
    index = LineIndex([EAST_WEST, NORTH_SOUTH])
    assert index.snap(at(3, 8), heading=None).line_id == 2


def test_local_bearing_follows_the_edge_on_a_bent_way():
    # East for 100 m, then north for 100 m.
    bent = FakeLine(7, [at(0, 0), at(100, 0), at(100, 100)])
    index = LineIndex([bent])
    on_north_leg = index.snap(at(104, 60), heading=0)
    assert on_north_leg.offset_m == pytest.approx(160, abs=0.3)
    # Heading east next to the northbound leg: that leg is incompatible, and
    # the eastbound leg is 60 m away → unmatched.
    assert index.snap(at(104, 60), heading=90) is None


def test_distance_tie_is_deterministic():
    twin_a = FakeLine(20, [at(0, 0), at(100, 0)])
    twin_b = FakeLine(10, [at(0, 0), at(100, 0)])
    assert LineIndex([twin_a, twin_b]).snap(at(50, 2), heading=90).line_id == 10
    assert LineIndex([twin_b, twin_a]).snap(at(50, 2), heading=90).line_id == 10


def test_long_edge_is_found_far_from_its_vertices():
    # A 3 km straight edge: the point is ~1.5 km from both end vertices.
    long_way = FakeLine(3, [at(0, 0), at(3000, 0)])
    match = LineIndex([long_way]).snap(at(1500, -10), heading=270)
    assert match.line_id == 3
    assert match.offset_m == pytest.approx(1500, abs=1.5)


def test_parallel_carriageways_stay_separate():
    north_side = FakeLine("N", [at(0, 8), at(300, 8)])
    south_side = FakeLine("S", [at(300, -8), at(0, -8)])     # drawn the other way
    index = LineIndex([north_side, south_side])
    assert index.snap(at(100, 6), heading=90).line_id == "N"
    assert index.snap(at(100, -7), heading=270).line_id == "S"


def test_degenerate_lines_are_ignored():
    index = LineIndex([FakeLine(1, [at(0, 0)]), FakeLine(2, [])])
    assert len(index) == 0
    assert index.snap(at(0, 0), heading=0) is None
