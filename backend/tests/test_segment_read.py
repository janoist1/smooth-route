"""Read side: zoom rules, path validation/envelopes, route summary and the
GraphQL contract the frontend builds against (no DB)."""
import datetime as dt

import pytest

from app.services.route_quality import ROUTE_BUFFER_M
from app.services.segment_read import (
    MAX_PATH_POINTS,
    SEGMENTS_MIN_ZOOM,
    SegmentRecord,
    fetch_segments_in_bbox,
    normalize_path,
    path_envelopes,
    should_serve_segments,
    simplify_tolerance_deg,
    summarize_route,
)
from geo_helpers import at


from app.core.rqi_scale import SCALE  # noqa: E402

sv = SCALE.from_severity


def record(id, x0, x1, rqi, score, level="high", **kw):
    """rqi / score in severity (1 = Kiváló); stored canonically via sv()."""
    return SegmentRecord(
        id=id, path=[at(x0, 0), at(x1, 0)], rqi=sv(rqi), score=sv(score), p_bad=kw.get("p_bad"),
        confidence=kw.get("confidence", 0.8), confidence_level=level, n_images=kw.get("n", 10),
        length_m=abs(x1 - x0), road_name="Teszt utca", highway="residential",
        capture_date_min=dt.date(2021, 5, 1), capture_date_max=dt.date(2023, 8, 1),
    )


# ---- zoom -----------------------------------------------------------------

def test_segments_are_served_from_zoom_13():
    assert SEGMENTS_MIN_ZOOM == 13
    assert not should_serve_segments(12)
    assert should_serve_segments(13)
    assert should_serve_segments(19)


def test_low_zoom_or_bad_bbox_returns_nothing_without_touching_the_db():
    assert fetch_segments_in_bbox(None, [19.0, 47.4, 19.2, 47.6], 12) == []
    assert fetch_segments_in_bbox(None, [19.0, 47.4, 19.2], 15) == []
    assert fetch_segments_in_bbox(None, [], 15) == []


def test_simplify_tolerance_shrinks_with_zoom():
    tolerances = [simplify_tolerance_deg(z) for z in range(13, 18)]
    assert all(a == 2 * b for a, b in zip(tolerances, tolerances[1:]))
    # Half a pixel: about 9.5 m of latitude at zoom 13, about 0.6 m at zoom 17.
    assert simplify_tolerance_deg(13) * 111_320 == pytest.approx(9.55, abs=0.1)
    assert simplify_tolerance_deg(17) * 111_320 == pytest.approx(0.6, abs=0.05)
    assert simplify_tolerance_deg(18) == 0.0
    assert simplify_tolerance_deg(25) == 0.0


# ---- path input -----------------------------------------------------------

def test_normalize_path_accepts_lat_lng_pairs():
    assert normalize_path([[47.5, 19.05], [47.6, 19.06, 123.0]]) == [(47.5, 19.05), (47.6, 19.06)]
    assert normalize_path([]) == []


@pytest.mark.parametrize(
    "bad",
    [
        [[47.5]],
        [[91.0, 19.0]],
        [[47.5, 181.0]],
        [[float("nan"), 19.0]],
        [[47.5, float("inf")]],
    ],
)
def test_normalize_path_rejects_garbage(bad):
    with pytest.raises(ValueError):
        normalize_path(bad)


def test_normalize_path_caps_the_point_count():
    with pytest.raises(ValueError, match="too many"):
        normalize_path([[47.5, 19.0]] * (MAX_PATH_POINTS + 1))


def test_path_envelopes_cover_every_point_with_padding():
    path = [(47.50 + 0.004 * i, 19.00 + 0.006 * i) for i in range(30)]     # ~20 km diagonal
    boxes = path_envelopes(path)
    assert len(boxes) > 3
    for lat, lng in path:
        assert any(w < lng < e and s < lat < n for w, s, e, n in boxes)
    # Consecutive points always share a box, so no edge can fall into a gap.
    for (la1, lo1), (la2, lo2) in zip(path, path[1:]):
        assert any(w < lo1 < e and s < la1 < n and w < lo2 < e and s < la2 < n
                   for w, s, e, n in boxes)
    # Far smaller than the path's own bounding box.
    area = sum((e - w) * (n - s) for w, s, e, n in boxes)
    assert area < 0.25 * (0.004 * 29) * (0.006 * 29)


def test_path_envelope_padding_exceeds_the_route_buffer():
    (w, s, e, n), = path_envelopes([(47.5, 19.05)])
    assert (47.5 - s) * 111_320 > ROUTE_BUFFER_M
    assert (19.05 - w) * 111_320 * 0.5 > ROUTE_BUFFER_M       # still true at 60° N
    assert path_envelopes([]) == []


def test_single_long_edge_gets_one_box():
    boxes = path_envelopes([(47.0, 19.0), (47.3, 19.4)])
    assert len(boxes) == 1


# ---- route summary --------------------------------------------------------

def test_summarize_route_excludes_low_confidence_from_worst():
    records = [
        record("good", 0, 150, 1, 1.3),
        record("bad", 150, 300, 4, 3.7),
        record("shaky", 300, 450, 4, 3.9, level="low"),
        record("fair", 450, 600, 3, 2.9, level="medium"),
    ]
    result = summarize_route([at(1, 1), at(601, 1)], records)
    assert result.total_length_m == pytest.approx(600, abs=0.5)
    assert result.covered_length_m == pytest.approx(600, abs=12)
    # The low-confidence segment still counts for coverage and class lengths…
    assert result.length_by_rqi[3] == pytest.approx(300, abs=12)
    assert result.mean_score == pytest.approx(sv((1.3 + 3.7 + 3.9 + 2.9) / 4), abs=0.05)
    # …but is not listed among the worst.
    assert [r.id for r in result.worst_segments] == ["bad", "fair", "good"]


def test_summarize_route_without_segments():
    result = summarize_route([at(0, 0), at(200, 0)], [])
    assert result.total_length_m == pytest.approx(200, abs=0.2)
    assert result.covered_length_m == 0.0
    assert result.length_by_rqi == [0.0, 0.0, 0.0, 0.0]
    assert result.mean_score is None
    assert result.worst_segments == []


# ---- GraphQL contract -----------------------------------------------------

def _sdl_block(sdl: str, header: str) -> list[str]:
    start = sdl.index(header)
    return [line.strip() for line in sdl[start:sdl.index("}", start)].splitlines()[1:] if line.strip()]


def test_graphql_contract_matches_what_the_frontend_builds_against():
    from app.graphql.schema import read_schema, schema

    for s in (schema, read_schema):          # full app AND the read-only deploy
        sdl = s.as_str()
        assert _sdl_block(sdl, "type RoadSegment {") == [
            "id: ID!",
            "path: [[Float!]!]!",
            "rqi: Int",
            "score: Float",
            "pBad: Float",
            "confidence: Float!",
            "confidenceLevel: String!",
            "nImages: Int!",
            "lengthM: Float!",
            "roadName: String",
            "highway: String",
            "captureDateMin: String",
            "captureDateMax: String",
        ]
        assert _sdl_block(sdl, "type RouteQuality {") == [
            "totalLengthM: Float!",
            "coveredLengthM: Float!",
            "lengthByRqi: [Float!]!",
            "meanScore: Float",
            "worstSegments: [RoadSegment!]!",
        ]
        assert "roadSegments(bbox: [Float!]!, zoom: Int!): [RoadSegment!]!" in sdl
        assert "routeQuality(path: [[Float!]!]!): RouteQuality!" in sdl


def test_resolvers_are_anonymous_and_map_records(monkeypatch):
    """Both queries answer without an identity, in the read-only schema, and
    format the record (rounding, YYYY-MM dates) as the contract says."""
    from app.graphql import queries
    from app.graphql.schema import read_schema
    from app.services import segment_read

    class NoDb:
        def close(self):
            pass

    rec = record("42:1", 0, 150, 3, 2.71828, p_bad=0.61234, confidence=0.70449, n=12)
    monkeypatch.setattr(queries, "get_db_session", lambda: NoDb())
    monkeypatch.setattr(segment_read, "fetch_segments_in_bbox", lambda db, bbox, zoom: [rec])
    monkeypatch.setattr(segment_read, "fetch_segments_near_path", lambda db, path, cfg=None: [rec])

    result = read_schema.execute_sync(
        """{ roadSegments(bbox: [19.0, 47.4, 19.2, 47.6], zoom: 15) {
               id path rqi score pBad confidence confidenceLevel nImages lengthM
               roadName highway captureDateMin captureDateMax } }""",
        context_value={"identity": None},
    )
    assert result.errors is None
    (seg,) = result.data["roadSegments"]
    assert seg["id"] == "42:1"
    assert seg["path"] == [list(p) for p in rec.path]
    assert (seg["rqi"], seg["score"], seg["pBad"], seg["confidence"]) == (sv(3), round(sv(2.71828), 3), 0.612, 0.704)
    assert (seg["confidenceLevel"], seg["nImages"], seg["lengthM"]) == ("high", 12, 150.0)
    assert (seg["roadName"], seg["highway"]) == ("Teszt utca", "residential")
    assert (seg["captureDateMin"], seg["captureDateMax"]) == ("2021-05", "2023-08")

    path = [list(at(1, 1)), list(at(151, 1))]
    result = read_schema.execute_sync(
        """query($p: [[Float!]!]!) { routeQuality(path: $p) {
               totalLengthM coveredLengthM lengthByRqi meanScore worstSegments { id rqi } } }""",
        variable_values={"p": path},
        context_value={"identity": None},
    )
    assert result.errors is None
    rq = result.data["routeQuality"]
    assert rq["totalLengthM"] == pytest.approx(150, abs=0.5)
    assert rq["coveredLengthM"] == pytest.approx(150, abs=6)
    assert rq["lengthByRqi"][2] == rq["coveredLengthM"] and len(rq["lengthByRqi"]) == 4
    assert rq["meanScore"] == round(sv(2.71828), 3)
    assert rq["worstSegments"] == [{"id": "42:1", "rqi": sv(3)}]


def test_route_quality_rejects_a_malformed_path():
    from app.graphql.schema import read_schema

    result = read_schema.execute_sync(
        "{ routeQuality(path: [[47.5]]) { totalLengthM } }", context_value={"identity": None}
    )
    assert result.errors and "lat, lng" in result.errors[0].message
