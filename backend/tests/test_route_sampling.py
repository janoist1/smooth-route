"""Route jobs: 50 m first pass, dense second pass on low-confidence segments,
and the route cost dry run (pure parts; no Google, no DB)."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.frame_store import segments_to_densify
from app.services.network_sampling import SamplingConfig, plan_collection, sample_route
from app.services.osm_overpass import tiles_in_bounds
from app.services.segment_geometry import haversine_m
from geo_helpers import at

_SPEC = importlib.util.spec_from_file_location(
    "route_cost", Path(__file__).resolve().parents[1] / "scripts" / "route_cost.py")
route_cost = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(route_cost)

ROUTE = [at(0, 0), at(1000, 0), at(1000, 500)]            # 1.5 km with a corner
SAMPLING = SamplingConfig(50.0, 30.0, ("low_confidence",))


def segment(id, x0, x1, level, north=0.0):
    return SimpleNamespace(id=id, path=[at(x0, north), at(x1, north)], rqi=3, score=3.1,
                           confidence_level=level)


def frame(east, north=1.0, heading=90.0):
    lat, lon = at(east, north)
    return SimpleNamespace(lat=lat, lon=lon, heading=heading)


def test_first_pass_is_one_point_every_50_m_not_every_10():
    points = sample_route(ROUTE, 50)
    assert len(points) == 30                                # was ~150 at the old 10 m spacing
    gaps = [haversine_m(a, b) for a, b in zip(points, points[1:])]
    assert max(gaps) <= 50.5 and min(gaps) > 30             # the corner cuts one gap short
    assert sample_route([at(0, 0)], 50) == [] and sample_route([], 50) == []


def test_second_pass_targets_only_low_confidence_segments_of_the_job():
    segments = [
        segment("sure", 0, 200, "high"),
        segment("shaky", 200, 400, "low"),
        segment("so-so", 400, 600, "medium"),
        segment("shaky-elsewhere", 5000, 5200, "low"),      # low, but not this job's
    ]
    job_frames = [frame(x) for x in range(25, 600, 50)]     # first pass over 0–600 m
    targets = segments_to_densify(segments, job_frames, SAMPLING)
    assert list(targets) == ["shaky"]
    assert targets["shaky"].coords == segments[1].path
    # config switch: no densify rule → no second pass at all
    assert segments_to_densify(segments, job_frames, SamplingConfig(50, 30, ())) == {}
    assert segments_to_densify(segments, [], SAMPLING) == {}


def test_second_pass_adds_points_between_the_first_pass_frames():
    shaky = segment("shaky", 200, 400, "low")
    first_pass = [frame(x) for x in (225, 275, 325, 375)]   # 50 m apart
    targets = segments_to_densify([shaky], first_pass, SAMPLING)
    plan = plan_collection(targets, first_pass, SAMPLING.dense_spacing_m)
    added = sorted(round(c.offset_m) for _cell, members in plan for c in members)
    # 30 m grid on a 200 m segment: 14, 43, 71, 100, 129, 157, 186 — minus the
    # ones within 15 m of an existing frame (at 25, 75, 125, 175).
    assert added == [43, 100, 157]
    assert all(min(abs(a - f) for f in (25, 75, 125, 175)) > 15 for a in added)


def test_route_cost_estimate_is_a_ceiling():
    cost = route_cost.estimate(ROUTE, 50, 30)
    assert cost["length_m"] == pytest.approx(1500, abs=1)
    assert cost["first_pass_max"] == 30
    assert cost["second_pass_max"] == 20                    # 50 dense points − 30 already taken
    short = route_cost.estimate([at(0, 0), at(20, 0)], 50, 30)
    assert (short["first_pass_max"], short["second_pass_max"]) == (0, 1)


def test_tiles_in_bounds_covers_the_box_without_the_touching_edge():
    assert tiles_in_bounds((47.50, 19.05, 47.55, 19.10)) == [(950, 381)]      # exactly one tile
    assert tiles_in_bounds((47.51, 19.06, 47.52, 19.07)) == [(950, 381)]
    assert len(tiles_in_bounds((47.49, 19.04, 47.56, 19.11))) == 9
    box = tiles_in_bounds((47.35, 18.85, 47.62, 19.35))                        # the collection area
    assert len(box) == 60 and box[0] == (947, 377) and box[-1] == (952, 386)
    assert box == sorted(box)
