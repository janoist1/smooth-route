"""Pure geometry: bearings, projection, splitting, linear referencing."""
import math

import pytest

from app.services.segment_geometry import (
    bearing_deg,
    bearing_diff_mod180,
    bearings_compatible,
    cumulative_lengths,
    densify,
    haversine_m,
    line_substring,
    piece_index_for_offset,
    point_at_offset,
    polyline_length_m,
    project_on_edge,
    split_count,
    split_polyline,
)
from geo_helpers import ORIGIN, at


def test_haversine_matches_the_metre_offsets():
    assert haversine_m(ORIGIN, at(100, 0)) == pytest.approx(100, abs=0.05)
    assert haversine_m(ORIGIN, at(0, 250)) == pytest.approx(250, abs=0.05)
    assert haversine_m(ORIGIN, at(300, 400)) == pytest.approx(500, abs=0.2)


def test_bearing_cardinal_directions():
    assert bearing_deg(ORIGIN, at(0, 100)) == pytest.approx(0, abs=0.01)
    assert bearing_deg(ORIGIN, at(100, 0)) == pytest.approx(90, abs=0.01)
    assert bearing_deg(ORIGIN, at(0, -100)) == pytest.approx(180, abs=0.01)
    assert bearing_deg(ORIGIN, at(-100, 0)) == pytest.approx(270, abs=0.01)


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (10, 10, 0),
        (10, 190, 0),      # opposite travel direction = same road axis
        (350, 10, 20),     # wraps through north
        (350, 170, 0),
        (0, 90, 90),
        (30, 100, 70),
        (30, 250, 40),     # 220° apart → 40° between the axes
    ],
)
def test_bearing_diff_mod180(a, b, expected):
    assert bearing_diff_mod180(a, b) == pytest.approx(expected)
    assert bearing_diff_mod180(b, a) == pytest.approx(expected)


def test_bearing_compatibility_is_strictly_below_the_limit():
    assert bearings_compatible(0, 44.9)
    assert bearings_compatible(0, 180 + 44.9)   # reverse direction still fits
    assert not bearings_compatible(0, 45.0)     # |Δ| < 45, not <=
    assert not bearings_compatible(0, 90)
    assert bearings_compatible(0, 60, max_diff_deg=61)


def test_project_on_edge_interior_and_clamped():
    a, b = at(0, 0), at(100, 0)
    t, dist = project_on_edge(at(30, 12), a, b)
    assert t == pytest.approx(0.30, abs=1e-3)
    assert dist == pytest.approx(12, abs=0.02)

    t, dist = project_on_edge(at(-40, 30), a, b)   # before the start → clamps to a
    assert t == 0.0
    assert dist == pytest.approx(50, abs=0.05)

    t, dist = project_on_edge(at(130, 40), a, b)   # past the end → clamps to b
    assert t == 1.0
    assert dist == pytest.approx(50, abs=0.05)


def test_project_on_degenerate_edge():
    t, dist = project_on_edge(at(3, 4), ORIGIN, ORIGIN)
    assert t == 0.0
    assert dist == pytest.approx(5, abs=0.01)


def test_cumulative_lengths():
    line = [at(0, 0), at(100, 0), at(100, 50)]
    cum = cumulative_lengths(line)
    assert cum[0] == 0.0
    assert cum[1] == pytest.approx(100, abs=0.05)
    assert cum[2] == pytest.approx(150, abs=0.1)
    assert polyline_length_m(line) == cum[-1]
    assert polyline_length_m([ORIGIN]) == 0.0


@pytest.mark.parametrize(
    "length, expected",
    [
        (0, 1), (40, 1), (150, 1), (224, 1),   # < 1.5 × target stays whole
        (226, 2), (300, 2), (374, 2),
        (376, 3), (450, 3), (1500, 10),
    ],
)
def test_split_count_rounds_to_nearest(length, expected):
    assert split_count(length, 150) == expected


def test_split_never_leaves_a_tiny_tail():
    # Rounding to the nearest count keeps every piece of a way that is at
    # least one target long within [0.75, 1.5) × target.
    for length in range(150, 5000, 7):
        n = split_count(length, 150)
        assert 112.5 <= length / n < 225


def test_split_count_rejects_bad_target():
    with pytest.raises(ValueError):
        split_count(100, 0)


def test_piece_index_for_offset():
    assert piece_index_for_offset(0, 300, 2) == 0
    assert piece_index_for_offset(149.9, 300, 2) == 0
    assert piece_index_for_offset(150.0, 300, 2) == 1
    assert piece_index_for_offset(300.0, 300, 2) == 1    # end clamps to the last piece
    assert piece_index_for_offset(-5, 300, 2) == 0
    assert piece_index_for_offset(999, 300, 2) == 1
    assert piece_index_for_offset(42, 80, 1) == 0


def test_point_at_offset_interpolates_and_clamps():
    line = [at(0, 0), at(100, 0), at(100, 100)]
    cum = cumulative_lengths(line)
    assert haversine_m(point_at_offset(line, cum, 25), at(25, 0)) < 0.05
    assert haversine_m(point_at_offset(line, cum, 150), at(100, 50)) < 0.1
    assert point_at_offset(line, cum, -1) == line[0]
    assert point_at_offset(line, cum, 1e9) == line[-1]


def test_line_substring_keeps_interior_vertices():
    line = [at(0, 0), at(100, 0), at(100, 100)]
    cum = cumulative_lengths(line)
    part = line_substring(line, cum, 50, 150)
    assert len(part) == 3                      # start, the corner vertex, end
    assert part[1] == line[1]
    assert polyline_length_m(part) == pytest.approx(100, abs=0.1)

    straight = line_substring(line, cum, 10, 60)   # no vertex strictly inside
    assert len(straight) == 2
    assert polyline_length_m(straight) == pytest.approx(50, abs=0.05)


def test_split_polyline_equal_contiguous_pieces():
    line = [at(0, 0), at(200, 0), at(200, 250)]     # 450 m with a corner
    pieces = split_polyline(line, 150)
    assert len(pieces) == 3
    for piece in pieces:
        assert polyline_length_m(piece) == pytest.approx(150, abs=0.2)
    # Contiguous: each piece starts where the previous one ended.
    for prev, nxt in zip(pieces, pieces[1:]):
        assert haversine_m(prev[-1], nxt[0]) < 1e-6
    assert pieces[0][0] == line[0] and pieces[-1][-1] == line[-1]


def test_split_polyline_short_way_is_returned_whole():
    line = [at(0, 0), at(60, 0)]
    assert split_polyline(line, 150) == [line]


def test_densify_lengths_sum_to_the_path_length():
    path = [at(0, 0), at(95, 0), at(95, 33), at(95, 33), at(200, 33)]  # incl. a duplicate
    samples = densify(path, 10)
    assert math.fsum(s[2] for s in samples) == pytest.approx(polyline_length_m(path), abs=1e-6)
    assert max(s[2] for s in samples) <= 10 + 1e-9
    # The bearing is that of the edge the sample lies on.
    assert samples[0][1] == pytest.approx(90, abs=0.05)
    assert any(abs(s[1]) < 0.05 for s in samples)        # the northbound edge
    with pytest.raises(ValueError):
        densify(path, 0)
