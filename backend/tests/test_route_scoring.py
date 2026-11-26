"""T-47: speed-weighted route impact (pure; no DB)."""
import math

import pytest

from app.core.rqi_scale import SCALE
from app.services import route_scoring as rs
from app.services.osm_overpass import parse_ways
from app.services.route_alternatives import RouteCandidate, rank_routes
from app.services.route_quality import SegmentRef, compute_route_stats
from app.services.segment_aggregation import load_config


@pytest.mark.parametrize("tag,kmh", [
    ("50", 50), ("30 mph", 48), ("HU:rural", 90), ("HU:urban", 50), ("30;50", 50),
    ("none", None), ("signals", None), (None, None), ("", None),
])
def test_parse_maxspeed(tag, kmh):
    assert rs.parse_maxspeed(tag) == kmh


def test_speed_prefers_the_tag_then_the_class_default():
    assert rs.speed_kmh(30, "motorway") == 30
    assert rs.speed_kmh(None, "motorway") == 130
    assert rs.speed_kmh(None, "nonsense") == rs.load_config()["fallback_kmh"]
    assert rs.speed_factor(90) == pytest.approx(1.8)


def _line(lat0=47.5, lon0=19.05, metres=300.0):
    dlon = metres / (111_320.0 * math.cos(math.radians(lat0)))
    return [(lat0, lon0), (lat0, lon0 + dlon)]


def _impact(score, speed):
    cfg = load_config()
    path = _line()
    seg = SegmentRef(id="s", coords=path, rqi=int(SCALE.nearest(score)), score=score,
                     length_m=300.0, speed_kmh=speed)
    return compute_route_stats(path, [seg], cfg.scale).impact_score


def test_the_same_defect_weighs_more_on_a_fast_road():
    worse = load_config().scale.best_to_worst[-1]  # worst level a segment can have
    slow, fast = _impact(worse, 30), _impact(worse, 90)
    assert fast == pytest.approx(3 * slow)
    best = load_config().scale.best_to_worst[0]
    assert _impact(best, 130) == pytest.approx(0.0)  # Kiváló costs nothing at any speed


@pytest.mark.parametrize("scale", [SCALE, SCALE.mirrored()], ids=["canonical", "mirrored"])
def test_badness_only_counts_shortfall_in_either_scale_direction(monkeypatch, scale):
    monkeypatch.setattr(rs, "SCALE", scale)
    best_severity = scale.to_severity(scale.best)
    for shortfall in (-0.5, 0.0, 0.75):
        score = scale.from_severity(best_severity + shortfall)
        assert rs.badness(score, scale.best) == pytest.approx(max(0.0, shortfall))


def test_smoothest_uses_the_impact_when_present():
    a = RouteCandidate(600, 5000, mean_score=3.0, covered_m=900, total_m=1000, impact_score=1.2)
    b = RouteCandidate(620, 5100, mean_score=2.0, covered_m=900, total_m=1000, impact_score=0.4)
    # b is better on impact whatever the plain mean says.
    assert rank_routes([a, b], SCALE)[1] == 1
    b2 = RouteCandidate(620, 5100, mean_score=2.0, covered_m=900, total_m=1000, impact_score=2.0)
    assert rank_routes([a, b2], SCALE)[1] == 0


def test_osm_parsing_and_chains_keep_the_speed_limit():
    from app.services import osm_chains

    payload = {"elements": [
        {"type": "way", "id": 1, "tags": {"highway": "primary", "name": "X", "maxspeed": "70"},
         "geometry": [{"lat": 47.5, "lon": 19.0}, {"lat": 47.5, "lon": 19.001}]},
        {"type": "way", "id": 2, "tags": {"highway": "primary", "name": "X"},
         "geometry": [{"lat": 47.5, "lon": 19.001}, {"lat": 47.5, "lon": 19.002}]},
    ]}
    ways = parse_ways(payload)
    assert [w.maxspeed for w in ways] == [70, None]
    merged = osm_chains.merge_ways({w.id: w for w in ways})
    assert [w.maxspeed for w in merged.values()] == [70]  # chained: the anchor's limit
