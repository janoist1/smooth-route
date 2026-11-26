"""Security delta review (T-45): limits for the fields merged after the first
review. No DB, no network: rejections happen before execution."""
from types import SimpleNamespace

import pytest

from app.core.secret_scan import redact_secrets

BBOX = "[19.0, 47.45, 19.15, 47.55]"


def run_public(query: str):
    from app.graphql.schema import read_schema

    return read_schema.execute_sync(query, context_value={"identity": None})


def rejected(res, needle: str) -> bool:
    return res.data is None and bool(res.errors) and needle in res.errors[0].message


# --- Point.segmentId: one query per point -> only on point(id) ---------------


@pytest.mark.parametrize("query", [
    f"{{ points(bbox: {BBOX}, limit: 20000) {{ id segmentId }} }}",
    '{ segmentFrames(segmentId: "s1") { id segmentId } }',
    f"{{ points(bbox: {BBOX}) {{ ...P }} }} fragment P on Point {{ segmentId }}",
    f"{{ points(bbox: {BBOX}) {{ ... on Point {{ segmentId }} }} }}",
])
def test_segment_id_refused_on_lists(query):
    res = run_public(query)
    assert rejected(res, "segmentId is only available on point(id)")


def test_segment_id_allowed_on_single_point_passes_the_guard():
    from app.graphql.limits import check_operation
    from app.graphql.schema import read_schema
    from graphql import parse

    # Passes the guard (execution would then hit the DB, not run here).
    check_operation(read_schema._schema, parse("{ point(id: 1) { id segmentId } }"))
    check_operation(read_schema._schema, parse(
        "query { point(id: 1) { ...P } } fragment P on Point { segmentId }"))


def test_segment_id_check_also_guards_the_full_schema():
    from app.graphql.schema import schema

    res = schema.execute_sync(f"{{ points(bbox: {BBOX}) {{ segmentId }} }}",
                              context_value={"identity": None})
    assert rejected(res, "segmentId is only available")


# --- paid fields: one per request in total -----------------------------------


def test_get_route_and_alternatives_together_refused():
    from app.graphql.schema import schema

    # Both paid fields coexist only on the full schema; the guard must still
    # reject their combined cost before permissions or resolvers run.
    res = schema.execute_sync(
        '{ getRoute(origin: "Budapest", destination: "Győr") { points { lat } }'
        ' routeAlternatives(origin: "Budapest", destination: "Pécs") { fastestIndex } }',
        context_value={"identity": None})
    assert rejected(res, "At most 1 route request")


def test_segment_frames_count_capped():
    q = "{ " + " ".join(f'f{i}: segmentFrames(segmentId: "s{i}") {{ id }}' for i in range(3)) + " }"
    assert rejected(run_public(q), "At most 2 segmentFrames per request")


# --- routeAlternatives: no quality work beyond the public path caps ----------


def test_alternatives_skip_quality_for_routes_over_the_cap(monkeypatch):
    import app.graphql.route_alternatives as mod
    from app.core.auth import Identity
    from app.graphql.limits import MAX_PATH_KM
    from app.services import google_maps, segment_read

    pts = [{"lat": 47.5, "lng": 19.05}, {"lat": 47.49, "lng": 19.06}]
    routes = [
        {"points": pts, "distance_m": 5000.0, "duration_s": 600.0, "summary": "near"},
        {"points": pts, "distance_m": MAX_PATH_KM * 1000 + 1, "duration_s": 650.0,
         "summary": "abroad"},
    ]
    computed = []

    def fake_quality(db, path):
        computed.append(len(path))
        return SimpleNamespace(total_length_m=5000.0, length_by_rqi=[5000.0, 0, 0, 0, 0],
                               mean_score=4.0, worst_segments=[])

    monkeypatch.setattr(google_maps.google_maps_service, "get_routes", lambda o, d: routes)
    monkeypatch.setattr(segment_read, "route_quality", fake_quality)
    monkeypatch.setattr(mod, "get_db_session", lambda: SimpleNamespace(close=lambda: None))
    from app.graphql.schema import schema

    res = schema.execute_sync(
        '{ routeAlternatives(origin: "47.5,19.05", destination: "Lisboa") '
        "{ routes { summary coverage quality { totalLengthM coveredLengthM meanScore } } } }",
        context_value={"identity": Identity(user_id="u", clerk_id="c", email=None, role="user")})
    assert res.errors is None, res.errors
    assert computed == [2]  # only the near route was measured
    far = res.data["routeAlternatives"]["routes"][1]
    assert far["coverage"] == 0 and far["quality"]["coveredLengthM"] == 0
    assert far["quality"]["meanScore"] is None
    assert far["quality"]["totalLengthM"] == pytest.approx(MAX_PATH_KM * 1000 + 1, abs=1)


def test_measurable_point_cap():
    from app.graphql.limits import MAX_PATH_POINTS
    from app.graphql.route_alternatives import measurable

    many = [{"lat": 47.5, "lng": 19.0}] * (MAX_PATH_POINTS + 1)
    assert not measurable({"points": many, "distance_m": 10.0})
    assert measurable({"points": many[:2], "distance_m": 10.0})


# --- logs never carry the key -------------------------------------------------


def test_redact_secrets_in_exception_text():
    key = "AIza" + "x" * 35
    msg = ("HTTPSConnectionPool(host='maps.googleapis.com', port=443): Max retries exceeded "
           f"with url: /maps/api/directions/json?origin=a&destination=b&key={key} (Caused by X)")
    out = redact_secrets(msg)
    assert key not in out and "key=[REDACTED]" in out and "origin=a" in out
    assert redact_secrets("postgresql://u:secret@host/db") == "postgresql://[REDACTED]@host/db"
    assert redact_secrets("no secrets here") == "no secrets here"


def test_google_maps_error_log_is_redacted(capsys):
    from app.services.google_maps import GoogleMapsService

    key = "AIza" + "y" * 35

    def boom(*a, **k):
        raise ConnectionError(f"url: /maps/api/directions/json?key={key}")

    svc = GoogleMapsService.__new__(GoogleMapsService)
    svc.client = SimpleNamespace(directions=boom, geocode=boom)
    assert svc.get_route("a", "b") == []
    assert svc.get_routes("a", "b") == []
    out = capsys.readouterr().out
    assert key not in out and "ConnectionError" in out
