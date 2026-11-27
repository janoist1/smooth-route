"""Security delta review (T-45): limits for the fields merged after the first
review. No DB, no network: rejections happen before execution."""
from types import SimpleNamespace
import asyncio
import threading
import time

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

    res = asyncio.run(schema.execute(
        '{ routeAlternatives(origin: "47.5,19.05", destination: "Lisboa") '
        "{ routes { summary coverage quality { totalLengthM coveredLengthM meanScore } } } }",
        context_value={"identity": Identity(user_id="u", clerk_id="c", email=None, role="user")}))
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


# --- Independent public review regressions (T-105) ----------------------------

def test_antimeridian_probe_rejected_before_quality_work(monkeypatch):
    from app.graphql.limits import InputLimitError, validate_route_path
    from app.graphql.schema import read_schema
    import app.graphql.queries as queries

    path = [[0, 180], [0, -180]] * 10_000
    with pytest.raises(InputLimitError, match="antimeridian"):
        validate_route_path(path)

    def unexpected_db():
        pytest.fail("antimeridian input reached the DB")

    monkeypatch.setattr(queries, "get_db_session", unexpected_db)
    result = read_schema.execute_sync(
        "query($path: [[Float!]!]!) { routeQuality(path: $path) { totalLengthM } }",
        variable_values={"path": path}, context_value={"identity": None})
    assert rejected(result, "antimeridian")
    assert result.errors[0].extensions == {"code": "BAD_USER_INPUT"}


def test_segment_reader_rejects_antimeridian_without_graphql_guard():
    from app.graphql.limits import InputLimitError
    from app.services.segment_read import normalize_path

    with pytest.raises(InputLimitError, match="antimeridian"):
        normalize_path([[0, 180], [0, -180]] * 10_000)


def test_interpolation_cap_checked_before_allocating(monkeypatch):
    from app.graphql.limits import InputLimitError
    from app.services import segment_read

    def allocation_started(*args):
        pytest.fail("interpolation allocated points before checking its budget")

    monkeypatch.setattr(segment_read, "range", allocation_started, raising=False)
    with pytest.raises(InputLimitError, match="generated points"):
        segment_read.densify_path([(0, 0), (0, 1)], max_step_m=0.001)


def test_envelope_cap_is_independent(monkeypatch):
    from app.graphql.limits import InputLimitError
    from app.services import segment_read

    monkeypatch.setattr(segment_read, "MAX_PATH_ENVELOPES", 2, raising=False)
    with pytest.raises(InputLimitError, match="envelopes"):
        segment_read.path_envelopes([(47, 19), (47.1, 19.1)])


def test_route_sample_cap_checked_before_matching(monkeypatch):
    from app.graphql.limits import InputLimitError
    from app.services import segment_read

    monkeypatch.setattr(segment_read, "MAX_ROUTE_SAMPLES", 2, raising=False)
    with pytest.raises(InputLimitError, match="generated samples"):
        segment_read.summarize_route([(47, 19), (47.001, 19)], [])


@pytest.mark.parametrize("levels", [16, 60])
def test_doubling_fragments_probe_finishes_fast(levels):
    query = f"{{ ...F{levels} }} fragment F0 on Query {{ me {{ role }} }} " + " ".join(
        f"fragment F{i} on Query {{ ...F{i - 1} ...F{i - 1} }}" for i in range(1, levels + 1)
    )
    start = time.monotonic()
    result = run_public(query)
    assert rejected(result, "expansion budget")
    assert result.errors[0].extensions == {"code": "BAD_USER_INPUT"}
    assert time.monotonic() - start < 0.5


def test_fragment_cycles_rejected_before_validation():
    from app.graphql.limits import InputLimitError, check_document_limits
    from graphql import parse

    query = "{ ...A } fragment A on Query { ...B } fragment B on Query { ...A }"
    with pytest.raises(InputLimitError, match="cycles"):
        check_document_limits(parse(query))
    assert rejected(run_public(query), "cycles")


def test_shared_fragments_keep_depth_alias_and_root_limits():
    from app.graphql.limits import InputLimitError, check_document_limits
    from graphql import parse

    # The same fragment at different nesting levels must retain its relative
    # depth, regardless of which spread the memoized traversal visits first.
    for fields in ("me { ...P } ...P", "...P me { ...P }"):
        body = "role"
        for _ in range(8):
            body = "nested { " + body + " }"
        with pytest.raises(InputLimitError, match="depth"):
            check_document_limits(parse("{ " + fields + " } fragment P on Query { " + body + " }"))
    aliases = "{ ...P ...P } fragment P on Query { " + " ".join(
        f"a{i}: me {{ role }}" for i in range(6)) + " }"
    assert rejected(run_public(aliases), "aliases found")
    # Reusing a fragment merges the same response key; distinct keys still cost.
    assert run_public("{ ...P ...P } fragment P on Query { me { role } }").errors is None
    assert rejected(run_public(
        '{ ...P ...P b: points { id } c: points { id } } '
        'fragment P on Query { a: points { id } }'), "At most 2 points")


def test_async_fragment_budget_runs_before_other_validators():
    from app.graphql.schema import read_schema

    # Invalid fields/types would fail normal validation, but expansion must be
    # checked first to bound even those validators' work on hostile documents.
    query = "{ ...F16 } fragment F0 on Unknown { missing } " + " ".join(
        f"fragment F{i} on Unknown {{ ...F{i - 1} ...F{i - 1} }}" for i in range(1, 17))
    result = asyncio.run(read_schema.execute(query, context_value={"identity": None}))
    assert rejected(result, "expansion budget")


def test_modifier_rejected_before_google_or_address_fallback(monkeypatch):
    from app.core.config import settings
    from app.services.google_maps import google_maps_service

    def unexpected_call(*args, **kwargs):
        pytest.fail("modifier reached Google")

    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    monkeypatch.setattr(google_maps_service, "get_routes", unexpected_call)
    assert rejected(run_public(
        '{ routeAlternatives(origin: "heading=90:40.7,-74.0", destination: "Győr") '
        '{ fastestIndex } }'), "modifiers")


@pytest.mark.parametrize("prefix", ["heading=90:", "side_of_road:", "via:", "place_id:", "custom:"])
@pytest.mark.parametrize("location", ["47.5,19.04", "40.7,-74.0", "Budapest"])
@pytest.mark.parametrize("endpoint", ["origin", "destination"])
def test_google_location_modifiers_rejected(prefix, location, endpoint):
    from app.graphql.limits import InputLimitError, validate_route_endpoints

    args = {"origin": "Budapest", "destination": "Győr", endpoint: prefix + location}
    with pytest.raises(InputLimitError, match="modifiers"):
        validate_route_endpoints(**args)


@pytest.mark.parametrize("method", ["get_routes", "geocode"])
@pytest.mark.parametrize("timeout_kind", ["ConnectTimeout", "ReadTimeout"])
def test_google_http_timeout_is_bounded_and_clean(monkeypatch, method, timeout_kind):
    import requests
    from graphql import GraphQLError
    from app.core.config import settings
    from app.services.google_maps import GoogleMapsService

    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "AIza" + "x" * 35)
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    svc = GoogleMapsService()
    attempts = []

    def timeout(*args, **kwargs):
        attempts.append(kwargs.get("timeout"))
        raise getattr(requests.exceptions, timeout_kind)("private timeout URL")

    monkeypatch.setattr(svc.client.session, "get", timeout)
    args = ("Budapest", "Győr") if method == "get_routes" else ("Budapest",)
    with pytest.raises(GraphQLError, match="Google Maps request timed out") as caught:
        getattr(svc, method)(*args)
    assert caught.value.extensions == {"code": "UPSTREAM_TIMEOUT"}
    assert "private" not in str(caught.value)
    assert len(attempts) == 1
    assert isinstance(attempts[0], tuple) and all(0 < value <= 5 for value in attempts[0])


def test_public_google_call_runs_off_event_loop(monkeypatch):
    from app.core.config import settings
    from app.graphql.schema import read_schema
    from app.services.google_maps import google_maps_service
    import app.graphql.route_alternatives as mod

    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    event_loop_thread = threading.get_ident()
    worker_threads = []

    def fake_routes(*args):
        worker_threads.append(threading.get_ident())
        return []

    monkeypatch.setattr(google_maps_service, "get_routes", fake_routes)
    monkeypatch.setattr(mod, "get_db_session", lambda: SimpleNamespace(close=lambda: None))
    result = asyncio.run(read_schema.execute(
        '{ routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex } }',
        context_value={"identity": None},
    ))
    assert result.errors is None
    assert worker_threads and all(t != event_loop_thread for t in worker_threads)


def test_public_timeout_returns_generic_error_without_fallback(monkeypatch):
    import googlemaps
    from app.core.config import settings
    from app.graphql.schema import read_schema
    from app.services.google_maps import google_maps_service

    calls = []

    def timeout(*args, **kwargs):
        calls.append("directions")
        raise googlemaps.exceptions.Timeout("private /srv/key URL")

    def unexpected_geocode(*args, **kwargs):
        pytest.fail("timeout triggered a paid fallback")

    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    monkeypatch.setattr(google_maps_service, "client",
                        SimpleNamespace(directions=timeout, geocode=unexpected_geocode))
    result = asyncio.run(read_schema.execute(
        '{ routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex } }',
        context_value={"identity": None}))
    assert result.data is None and calls == ["directions"]
    assert result.errors[0].extensions == {"code": "UPSTREAM_TIMEOUT"}
    assert result.errors[0].message == "Google Maps request timed out. Please try again later."


@pytest.mark.parametrize("root", ['job(id: "test")', "activeJob"])
def test_public_jobs_never_return_stored_diagnostics(monkeypatch, root):
    import app.graphql.queries as queries
    from app.services import job_service
    from app.core.timeutil import utcnow

    job = SimpleNamespace(job_id="test", status=job_service.JobStatus.FAILED,
                          progress=3, total=10, current_step=None,
                          message="private /srv/database SQL diagnostics", error="private URL",
                          result={"private": "SQL"}, created_at=utcnow(), completed_at=None)
    monkeypatch.setattr(queries, "get_job", lambda id: job)
    monkeypatch.setattr(job_service, "get_job", lambda id: job)
    monkeypatch.setattr(job_service, "get_active_job", lambda: job)
    result = run_public("{ " + root + " { status progress total message } }")
    assert result.errors is None
    payload = next(iter(result.data.values()))
    assert payload == {"status": "failed", "progress": 3, "total": 10, "message": "Job failed."}


def test_public_job_schema_excludes_diagnostic_fields(monkeypatch):
    from app.graphql.schema import read_schema, schema
    from app.services import job_service

    def unexpected_read(*args):
        pytest.fail("diagnostic selections must be rejected before reading jobs")

    monkeypatch.setattr(job_service, "get_job", unexpected_read)
    monkeypatch.setattr(job_service, "get_active_job", unexpected_read)

    result = run_public('{ job(id: "test") { error result details } activeJob { error result } }')
    assert result.data is None and len(result.errors) == 5
    assert read_schema._schema.get_type("Job") is None
    assert set(read_schema._schema.get_type("PublicJob").fields) == {
        "id", "status", "progress", "total", "message", "createdAt", "completedAt"}
    assert {"error", "result", "details"} <= set(schema._schema.get_type("Job").fields)
