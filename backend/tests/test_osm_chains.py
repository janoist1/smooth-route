"""Stitching consecutive OSM ways of the same road into lines."""
import pytest

from app.services.osm_chains import chain_members, merge_ways
from app.services.osm_overpass import Way
from app.services.segment_geometry import polyline_length_m
from geo_helpers import at


def way(id, points, name="Fő utca", highway="secondary"):
    return Way(id=id, coords=tuple(points), name=name, highway=highway)


def as_dict(*ways):
    return {w.id: w for w in ways}


def test_consecutive_same_road_ways_become_one_line():
    ways = as_dict(
        way(30, [at(0, 0), at(60, 0)]),
        way(10, [at(60, 0), at(130, 0)]),
        way(20, [at(130, 0), at(200, 0), at(260, 0)]),
    )
    merged = merge_ways(ways)
    assert list(merged) == [10]                       # id = smallest member way id
    line = merged[10]
    assert (line.name, line.highway) == ("Fő utca", "secondary")
    assert polyline_length_m(line.coords) == pytest.approx(260, abs=0.3)
    # Each shared node appears once, in order along the road.
    assert list(line.coords) == [at(0, 0), at(60, 0), at(130, 0), at(200, 0), at(260, 0)]
    assert chain_members(ways) == {10: 10, 20: 10, 30: 10}


def test_ways_drawn_in_opposite_directions_are_flipped_to_fit():
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)]),
        way(2, [at(200, 0), at(100, 0)]),             # drawn right-to-left
        way(3, [at(200, 0), at(300, 0)]),
    )
    line = merge_ways(ways)[1]
    assert list(line.coords) == [at(0, 0), at(100, 0), at(200, 0), at(300, 0)]


def test_line_is_oriented_along_its_anchor_way():
    # The anchor (smallest id) is the LAST way of the road and points west.
    ways = as_dict(
        way(9, [at(0, 0), at(100, 0)]),
        way(5, [at(200, 0), at(100, 0)]),
    )
    line = merge_ways(ways)[5]
    assert list(line.coords) == [at(200, 0), at(100, 0), at(0, 0)]


def test_result_does_not_depend_on_input_order():
    a = way(1, [at(0, 0), at(100, 0)])
    b = way(2, [at(100, 0), at(200, 0)])
    c = way(3, [at(200, 0), at(300, 0)])
    assert merge_ways(as_dict(a, b, c)) == merge_ways(as_dict(c, a, b))


def test_different_name_or_class_stops_the_chain():
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)], name="Fő utca"),
        way(2, [at(100, 0), at(200, 0)], name="Kossuth utca"),
        way(3, [at(200, 0), at(300, 0)], name="Kossuth utca", highway="tertiary"),
    )
    merged = merge_ways(ways)
    assert sorted(merged) == [1, 2, 3]
    assert merged[2].coords == ways[2].coords


def test_crossing_street_does_not_break_or_join_the_road():
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)]),
        way(2, [at(100, 0), at(200, 0)]),
        way(7, [at(100, -80), at(100, 0)], name="Mellék utca", highway="residential"),
        way(8, [at(100, 0), at(100, 80)], name="Mellék utca", highway="residential"),
    )
    merged = merge_ways(ways)
    assert sorted(merged) == [1, 7]                   # two roads, each stitched across the junction
    assert polyline_length_m(merged[1].coords) == pytest.approx(200, abs=0.2)
    assert polyline_length_m(merged[7].coords) == pytest.approx(160, abs=0.2)


def test_fork_of_the_same_road_is_not_joined():
    # A two-way road splitting into two one-way carriageways of the same name.
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)]),
        way(2, [at(100, 0), at(200, 6)]),
        way(3, [at(100, 0), at(200, -6)]),
    )
    assert sorted(merge_ways(ways)) == [1, 2, 3]


def test_unnamed_ways_join_only_at_a_plain_continuation():
    plain = as_dict(
        way(1, [at(0, 0), at(50, 0)], name=None, highway="service"),
        way(2, [at(50, 0), at(90, 0)], name=None, highway="service"),
    )
    assert list(merge_ways(plain)) == [1]

    junction = dict(plain)
    junction[3] = way(3, [at(50, 0), at(50, 40)], name="Fő utca", highway="residential")
    assert sorted(merge_ways(junction)) == [1, 2, 3]   # something else ends there → no join

    mixed = as_dict(
        way(1, [at(0, 0), at(50, 0)], name=None, highway="service"),
        way(2, [at(50, 0), at(90, 0)], name=None, highway="residential"),
    )
    assert sorted(merge_ways(mixed)) == [1, 2]


def test_roundabout_stays_on_its_own():
    ring = way(4, [at(0, 0), at(10, 10), at(20, 0), at(10, -10), at(0, 0)], name="Körforgalom")
    arm = way(5, [at(-80, 0), at(0, 0)], name="Körforgalom")
    merged = merge_ways(as_dict(ring, arm))
    assert sorted(merged) == [4, 5]
    assert merged[4].coords == ring.coords


def test_ring_made_of_several_ways_terminates():
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)]),
        way(2, [at(100, 0), at(100, 100)]),
        way(3, [at(100, 100), at(0, 100)]),
        way(4, [at(0, 100), at(0, 0)]),
    )
    merged = merge_ways(ways)
    assert list(merged) == [1]
    assert polyline_length_m(merged[1].coords) == pytest.approx(400, abs=0.5)
    assert merged[1].coords[0] == at(0, 0)             # starts with the anchor way


def test_every_way_lands_in_exactly_one_line_and_length_is_preserved():
    ways = as_dict(
        way(1, [at(0, 0), at(100, 0)]),
        way(2, [at(100, 0), at(200, 0)]),
        way(3, [at(500, 0), at(600, 0)]),                              # detached
        way(4, [at(100, 0), at(100, 90)], name="Más utca"),
        way(5, [at(0, 300), at(40, 300)], name=None, highway="service"),
    )
    merged = merge_ways(ways)
    members = chain_members(ways)
    assert set(members) == set(ways)
    assert set(members.values()) == set(merged)
    total_in = sum(polyline_length_m(w.coords) for w in ways.values())
    total_out = sum(polyline_length_m(w.coords) for w in merged.values())
    assert total_out == pytest.approx(total_in, abs=1e-6)


def test_empty_input():
    assert merge_ways({}) == {}
    assert chain_members({}) == {}
