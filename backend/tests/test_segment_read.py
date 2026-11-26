"""Read side: zoom rules, path validation/envelopes, route summary, frame ↔
segment links and the GraphQL contract the frontend builds against (no DB)."""
import datetime as dt
from types import SimpleNamespace

import pytest

from app.services.route_quality import ROUTE_BUFFER_M
from app.services.segment_aggregation import config_from_dict
from app.services.segment_read import (
    MAX_PATH_LENGTH_M,
    MAX_PATH_POINTS,
    SEGMENTS_MIN_ZOOM,
    SegmentRecord,
    fetch_segments_in_bbox,
    match_frames_to_segment,
    normalize_path,
    path_envelopes,
    should_serve_segments,
    simplify_tolerance_deg,
    summarize_route,
)
from geo_helpers import FLIPPED_CONFIG, at, make_config

CFG = make_config()


def record(id, x0, x1, rqi, score, level="high", north=0.0, **kw):
    return SegmentRecord(
        id=id, path=[at(x0, north), at(x1, north)], rqi=rqi, score=score, p_bad=kw.get("p_bad"),
        confidence=kw.get("confidence", 0.8), confidence_level=level,
        confidence_reason=kw.get("reason"), n_images=kw.get("n", 10),
        length_m=abs(x1 - x0), road_name="Teszt utca", highway="residential",
        capture_date_min=dt.date(2021, 5, 1), capture_date_max=dt.date(2023, 8, 1),
        mid=at((x0 + x1) / 2, north), mid_heading=90.0,
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


def test_normalize_path_caps_the_total_length():
    # Cost is per 10 m of path, so a few points can still be expensive:
    # 1000 points zig-zagging 0.5 degrees of latitude is ~55 000 km.
    zigzag = [[47.0 + 0.5 * (i % 2), 19.0] for i in range(1000)]
    with pytest.raises(ValueError, match="too long"):
        normalize_path(zigzag)
    # A real cross-country route stays well inside the cap.
    budapest_to_szeged = [[47.4979, 19.0402], [46.2530, 20.1414]]
    assert len(normalize_path(budapest_to_szeged)) == 2
    assert MAX_PATH_LENGTH_M >= 1_000_000


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


def test_single_long_edge_is_split_into_many_small_boxes():
    # T-80: the edge is densified first, so it no longer gets one huge box.
    boxes = path_envelopes([(47.0, 19.0), (47.3, 19.4)])
    assert len(boxes) > 1
    assert all(e - w < 0.05 and n - s < 0.05 for w, s, e, n in boxes)


# ---- route summary --------------------------------------------------------

def test_summarize_route_excludes_low_confidence_from_worst():
    records = [
        record("good", 0, 150, 1, 1.3),
        record("bad", 150, 300, 4, 3.7),
        record("shaky", 300, 450, 4, 3.9, level="low"),
        record("fair", 450, 600, 3, 2.9, level="medium"),
    ]
    result = summarize_route([at(1, 1), at(601, 1)], records, CFG)
    assert result.total_length_m == pytest.approx(600, abs=0.5)
    assert result.covered_length_m == pytest.approx(600, abs=12)
    # The low-confidence segment still counts for coverage and class lengths…
    assert result.length_by_rqi[3] == pytest.approx(300, abs=12)
    assert result.mean_score == pytest.approx((1.3 + 3.7 + 3.9 + 2.9) / 4, abs=0.05)
    # …but is not listed among the worst. Worst first.
    assert [r.id for r in result.worst_segments] == ["bad", "fair", "good"]
    assert sum(result.length_by_rqi) == pytest.approx(result.covered_length_m)


def test_summarize_route_without_segments():
    result = summarize_route([at(0, 0), at(200, 0)], [], CFG)
    assert result.total_length_m == pytest.approx(200, abs=0.2)
    assert result.covered_length_m == 0.0
    assert result.length_by_rqi == [0.0, 0.0, 0.0, 0.0]
    assert result.mean_score is None
    assert result.worst_segments == []


def test_summarize_route_on_the_flipped_scale_lists_the_lowest_scores_first():
    flipped = config_from_dict(FLIPPED_CONFIG)
    records = [
        record("excellent", 0, 150, 5, 4.7),
        record("poor", 150, 300, 2, 2.3),
        record("fair", 300, 450, 3, 3.1),
    ]
    result = summarize_route([at(1, 1), at(451, 1)], records, flipped)
    assert [r.id for r in result.worst_segments] == ["poor", "fair", "excellent"]
    assert result.length_by_rqi[0] > 100 and result.length_by_rqi[3] > 100     # classes 2 and 5


# ---- frame ↔ segment ------------------------------------------------------

def frame(id, east, north, heading):
    lat, lon = at(east, north)
    return SimpleNamespace(id=id, lat=lat, lon=lon, heading=heading)


def test_segment_frames_exclude_parallel_and_crossing_roads():
    here = record("here", 0, 200, 2, 2.0)
    parallel = record("parallel", 0, 200, 3, 3.0, north=14.0)       # service road 14 m north
    crossing = SegmentRecord(
        id="crossing", path=[at(100, -80), at(100, 80)], rqi=1, score=1.2, p_bad=None,
        confidence=0.8, confidence_level="high", confidence_reason=None, n_images=5,
        length_m=160, road_name=None, highway="residential",
        capture_date_min=None, capture_date_max=None,
    )
    frames = [
        frame(3, 150, 1, 90),      # on "here"
        frame(1, 20, -2, 270),     # on "here", driving the other way
        frame(2, 80, 3, 90),       # on "here"
        frame(7, 60, 12, 90),      # 2 m from the parallel road, 12 m from here
        frame(8, 101, 5, 0),       # on the crossing road (heading north)
        frame(9, 50, 60, 90),      # nowhere near
    ]
    segments = [here, parallel, crossing]
    assert match_frames_to_segment("here", segments, frames) == [1, 2, 3]      # along the segment
    assert match_frames_to_segment("parallel", segments, frames) == [7]
    assert match_frames_to_segment("crossing", segments, frames) == [8]
    # Without the parallel road stored, its frame is in reach of "here" (12 m):
    assert match_frames_to_segment("here", [here, crossing], frames) == [1, 7, 2, 3]
    assert match_frames_to_segment("missing", segments, frames) == []


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
            "confidenceReason: String",
            "streetViewUrl: String",
        ]
        assert _sdl_block(sdl, "type RouteQuality {") == [
            "totalLengthM: Float!",
            "coveredLengthM: Float!",
            "lengthByRqi: [Float!]!",
            "meanScore: Float",
            "impactScore: Float",  # T-47, additive: speed-weighted impact
            "worstSegments: [RoadSegment!]!",
        ]
        assert "roadSegments(bbox: [Float!]!, zoom: Int!): [RoadSegment!]!" in sdl
        assert "routeQuality(path: [[Float!]!]!): RouteQuality!" in sdl
        assert "segmentFrames(segmentId: ID!): [Point!]!" in sdl
        assert "segmentId: ID" in _sdl_block(sdl, "type Point {")


class _NoDb:
    def close(self):
        pass


@pytest.fixture
def no_db(monkeypatch):
    from app.graphql import queries, resolver_helpers

    monkeypatch.setattr(queries, "get_db_session", lambda: _NoDb())
    monkeypatch.setattr(resolver_helpers, "get_db_session", lambda: _NoDb())


def test_resolvers_are_anonymous_and_map_records(monkeypatch, no_db):
    """Both queries answer without an identity, in the read-only schema, and
    format the record (rounding, YYYY-MM dates) as the contract says."""
    from app.graphql.schema import read_schema
    from app.services import segment_read

    rec = record("42:1", 0, 150, 3, 2.71828, p_bad=0.61234, confidence=0.70449, n=12,
                 reason="near_threshold")
    monkeypatch.setattr(segment_read, "fetch_segments_in_bbox", lambda db, bbox, zoom: [rec])
    monkeypatch.setattr(segment_read, "fetch_segments_near_path", lambda db, path, cfg=None: [rec])

    result = read_schema.execute_sync(
        """{ roadSegments(bbox: [19.0, 47.4, 19.2, 47.6], zoom: 15) {
               id path rqi score pBad confidence confidenceLevel confidenceReason nImages
               lengthM roadName highway captureDateMin captureDateMax streetViewUrl } }""",
        context_value={"identity": None},
    )
    assert result.errors is None
    (seg,) = result.data["roadSegments"]
    assert seg["id"] == "42:1"
    assert seg["path"] == [list(p) for p in rec.path]
    assert (seg["rqi"], seg["score"], seg["pBad"], seg["confidence"]) == (3, 2.718, 0.612, 0.704)
    assert (seg["confidenceLevel"], seg["nImages"], seg["lengthM"]) == ("high", 12, 150.0)
    assert seg["confidenceReason"] == "near_threshold"
    assert (seg["roadName"], seg["highway"]) == ("Teszt utca", "residential")
    assert (seg["captureDateMin"], seg["captureDateMax"]) == ("2021-05", "2023-08")
    # Street View link: same scheme as Point.streetViewUrl, at the midpoint,
    # looking along the road.
    mid_lat, mid_lng = rec.mid
    assert seg["streetViewUrl"] == (
        "https://www.google.com/maps/@?api=1&map_action=pano"
        f"&viewpoint={round(mid_lat, 6)},{round(mid_lng, 6)}&heading=90.0&pitch=-20.0"
    )

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
    assert len(rq["lengthByRqi"]) == 4
    assert rq["coveredLengthM"] == round(sum(rq["lengthByRqi"]), 1)      # exact, by definition
    assert rq["coveredLengthM"] <= rq["totalLengthM"]
    assert rq["meanScore"] == 2.718
    assert rq["worstSegments"] == [{"id": "42:1", "rqi": 3}]             # same id as roadSegments


def test_route_quality_with_no_coverage_has_null_mean_score(monkeypatch, no_db):
    from app.graphql.schema import read_schema
    from app.services import segment_read

    monkeypatch.setattr(segment_read, "fetch_segments_near_path", lambda db, path, cfg=None: [])
    result = read_schema.execute_sync(
        """query($p: [[Float!]!]!) { routeQuality(path: $p) {
               totalLengthM coveredLengthM lengthByRqi meanScore worstSegments { id } } }""",
        variable_values={"p": [list(at(0, 0)), list(at(300, 0))]},
        context_value={"identity": None},
    )
    assert result.errors is None
    rq = result.data["routeQuality"]
    assert rq["totalLengthM"] == pytest.approx(300, abs=0.5)
    assert (rq["coveredLengthM"], rq["meanScore"], rq["worstSegments"]) == (0.0, None, [])
    assert rq["lengthByRqi"] == [0.0, 0.0, 0.0, 0.0]


def test_route_quality_rejects_a_malformed_path():
    from app.graphql.schema import read_schema

    result = read_schema.execute_sync(
        "{ routeQuality(path: [[47.5]]) { totalLengthM } }", context_value={"identity": None}
    )
    assert result.errors and "lat, lng" in result.errors[0].message


def test_segment_without_midpoint_has_no_street_view_link():
    from app.graphql.queries import _road_segment

    bare = SegmentRecord(
        id="1:0", path=[at(0, 0), at(10, 0)], rqi=2, score=2.0, p_bad=None, confidence=0.5,
        confidence_level="low", confidence_reason="few_images", n_images=1, length_m=10,
        road_name=None, highway=None, capture_date_min=None, capture_date_max=None,
    )
    assert _road_segment(bare).street_view_url() is None


def test_point_segment_id_resolves_through_the_matcher(monkeypatch, no_db):
    from app.graphql.types import Point
    from app.services import segment_read

    seen = {}

    def fake(db, lat, lng, heading):
        seen.update(lat=lat, lng=lng, heading=heading)
        return "363312385:2"

    monkeypatch.setattr(segment_read, "segment_id_for_point", fake)

    def make_point(dino_rqi_score=2.0, analysis_metadata=None):
        return Point(
            id=7, latitude=47.5, longitude=19.05, heading=123.0, pitch=-20.0, image_url=None,
            rqi_score=None, damage_count=0, damage_types=None,
            analysis_metadata=analysis_metadata, dino_rqi_score=dino_rqi_score,
            created_at=dt.datetime(2026, 1, 1),
        )

    assert make_point().segment_id() == "363312385:2"
    assert seen == {"lat": 47.5, "lng": 19.05, "heading": 123.0}

    # Frames the builder does not use never claim a segment (and cost no query),
    # so a non-null segmentId always means "listed in segmentFrames".
    seen.clear()
    assert make_point(analysis_metadata={"frame_quality": {"usable": False}}).segment_id() is None
    assert make_point(dino_rqi_score=None).segment_id() is None            # not scored yet
    assert seen == {}
    assert make_point(dino_rqi_score=None,
                      analysis_metadata={"dino_score": 2.4}).segment_id() == "363312385:2"

    monkeypatch.setattr(segment_read, "segment_id_for_point", lambda *a: None)
    assert make_point().segment_id() is None                  # unmatched frame


def test_point_and_segment_street_view_links_share_one_scheme():
    from app.graphql.types import street_view_link

    assert street_view_link(47.5, 19.05, 90.0, -20.0) == (
        "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=47.5,19.05&heading=90.0&pitch=-20.0"
    )
    assert street_view_link(47.5, 19.05, 90.0, None, pano_id="abc") == (
        "https://www.google.com/maps/@?api=1&map_action=pano&pano=abc&heading=90.0&pitch=0"
    )


def test_segment_frames_unknown_id_is_empty(monkeypatch, no_db):
    from app.graphql.schema import read_schema
    from app.services import segment_read

    monkeypatch.setattr(segment_read, "frame_ids_on_segment", lambda db, segment_id: [])
    result = read_schema.execute_sync(
        '{ segmentFrames(segmentId: "nope:0") { id } }', context_value={"identity": None}
    )
    assert result.errors is None
    assert result.data["segmentFrames"] == []


def test_record_maps_the_unlabelled_area_flag_to_the_reason():
    import datetime as dt

    from app.services.segment_read import _record
    from geo_helpers import make_config

    cfg = make_config(unlabelled_area={"radius_km": 3, "cap_level": "medium"})
    base = dict(id="1:0", geojson='{"type":"LineString","coordinates":[[19.0,47.5],[19.001,47.5]]}',
                rqi=2, score=1.8, p_bad=0.1, confidence=0.6599, n_images=12,
                length_m=150.0, road_name="X", highway="residential",
                capture_date_min=None, capture_date_max=None,
                updated_at=dt.datetime(2026, 11, 26), mid_lat=None, mid_lng=None,
                mid_heading=None)
    flagged = _record(SimpleNamespace(**base, unlabelled_area=True), cfg)
    assert flagged.confidence_level == "medium"
    assert flagged.confidence_reason == "unlabelled_area"
    plain = _record(SimpleNamespace(**base, unlabelled_area=False), cfg)
    assert plain.confidence_reason != "unlabelled_area"


class _CaptureDb:
    """Fake session: records the SQL text, returns no rows."""

    def __init__(self):
        self.sql = None

    def execute(self, clause, params=None):
        self.sql = str(clause)
        self.params = params

        class _Rows:
            def fetchall(self):
                return []

        return _Rows()


def test_bbox_query_uses_plain_simplify_below_street_zoom():
    # ST_SimplifyPreserveTopology (GEOS per row) cost ~85 ms of ~110 ms for a
    # zoom-13 Budapest viewport; segments are single short LineStrings.
    db = _CaptureDb()
    fetch_segments_in_bbox(db, [19.0, 47.4, 19.2, 47.6], 13)
    assert "ST_Simplify(s.geom, :tol, true)" in db.sql
    assert "PreserveTopology" not in db.sql
    assert db.params["tol"] == pytest.approx(simplify_tolerance_deg(13))


def test_bbox_query_sends_raw_geometry_from_zoom_18():
    db = _CaptureDb()
    fetch_segments_in_bbox(db, [19.0, 47.49, 19.01, 47.5], 18)
    assert "ST_AsGeoJSON(s.geom, 6)" in db.sql
    assert "ST_Simplify" not in db.sql


def test_long_edge_is_densified_into_small_envelopes():
    """T-80: a ~590 km single edge must not become one country-sized box."""
    from app.services import segment_read as sr

    path = [(45.8, 16.2), (48.5, 22.8)]
    dense = sr.densify_path(path)
    assert dense[0] == path[0] and dense[-1] == path[-1]
    assert len(dense) > 500
    boxes = sr.path_envelopes(path)
    assert len(boxes) > 10
    limit = sr._ENVELOPE_MAX_SPAN_DEG + 2 * sr._ENVELOPE_PAD_DEG + 0.02
    for west, south, east, north in boxes:
        assert east - west <= limit
        assert north - south <= limit


def test_segment_candidate_cap_raises(monkeypatch):
    from app.services import segment_read as sr

    class _Res:
        def fetchall(self):
            return [object()] * 3

    class _Db:
        def execute(self, *a, **k):
            return _Res()

    monkeypatch.setattr(sr, "MAX_SEGMENT_CANDIDATES", 2)
    import pytest

    with pytest.raises(sr.TooManySegmentCandidates):
        sr.fetch_segments_in_boxes(_Db(), [(0.0, 0.0, 1.0, 1.0)], cfg=object())
