"""Offline provider/policy regressions using OSRM and Nominatim JSON fixtures."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from graphql import GraphQLError
from pydantic import ValidationError
import pytest
import requests

from app.core.config import Settings, settings
from app.graphql.limits import InputLimitError
from app.services import routing_osm as osm
from app.services.directions_quota import default_quota
from app.services.routing import routing_service

START, END = "47.5,19.04", "47.48,19.08"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(settings, "ROUTING_PROVIDER", "osm")
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    monkeypatch.setattr(settings, "ROUTING_OSRM_URL", "https://routing.openstreetmap.de/routed-car")
    monkeypatch.setattr(settings, "ROUTING_NOMINATIM_URL", "https://nominatim.openstreetmap.org")
    monkeypatch.setattr(osm, "_osrm_gate", osm._RequestGate())
    monkeypatch.setattr(osm, "_nominatim_gate", osm._RequestGate())
    monkeypatch.setattr(osm, "_geocode_cache", osm.OrderedDict())
    clock = SimpleNamespace(now=100.0, sleeps=[])

    def sleep(delay):
        clock.sleeps.append(delay)
        clock.now += delay

    monkeypatch.setattr(osm, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    return osm.OsmRoutingService(), clock


@pytest.fixture
def upstream(monkeypatch):
    routes = json.loads((FIXTURES / "osrm_routes.json").read_text())
    geocode = json.loads((FIXTURES / "nominatim_hu.json").read_text())

    def get(url, **kwargs):
        return Mock(status_code=200, json=lambda: copy.deepcopy(geocode if url.endswith("/search") else routes))

    mock = Mock(side_effect=get)
    monkeypatch.setattr(osm.requests, "get", mock)
    return mock


def test_osrm_parsing_and_one_call_for_three_alternatives(service, upstream):
    svc, _ = service
    routes = svc.get_routes(START, END, max_routes=20)
    assert len(routes) == 3
    assert routes[0]["distance_m"] == 5000.5
    assert routes[0]["duration_s"] == 600.2
    assert [r["summary"] for r in routes] == ["Kossuth Lajos utca, M1", "Fő utca", ""]
    assert routes[0]["points"] == [{"lat": 47.5, "lng": 19.04}, {"lat": 47.48, "lng": 19.08}]
    upstream.assert_called_once_with(
        "https://routing.openstreetmap.de/routed-car/route/v1/driving/19.04,47.5;19.08,47.48",
        params={"alternatives": "2", "overview": "full", "geometries": "polyline", "steps": "true"},
        headers={"User-Agent": osm.USER_AGENT}, timeout=(2, 5), allow_redirects=False,
    )
    assert default_quota("osm").used() == 1


def test_single_route_and_limit(service, upstream):
    svc, _ = service
    assert len(svc.get_route(START, END)) == 2
    assert upstream.call_args.kwargs["params"]["alternatives"] == "false"
    assert len(svc.get_routes(START, END, max_routes=2)) == 2
    assert svc.get_routes(START, END, max_routes=0) == []
    assert upstream.call_count == 2


@pytest.mark.parametrize("origin,destination,calls", [(START, END, 1), ("Budapest", END, 2), ("Budapest", "Győr", 3)])
def test_public_text_endpoints_are_geocoded_before_one_route(service, upstream, origin, destination, calls):
    svc, _ = service
    assert svc.get_routes(origin, destination)
    assert upstream.call_count == calls
    assert sum("/route/" in c.args[0] for c in upstream.call_args_list) == 1
    assert default_quota("osm").used() == calls
    for call in upstream.call_args_list[:-1]:
        assert call.kwargs["params"] == {
            "q": origin if call == upstream.call_args_list[0] else destination,
            "format": "jsonv2", "countrycodes": "hu", "limit": 1, "accept-language": "hu",
        }


def test_geocode_cache_shared_across_instances_and_expires(service, upstream):
    svc, clock = service
    assert svc.geocode(" Budapest ") == "47.4979937,19.0403594"
    assert osm.OsmRoutingService().geocode("BUDAPEST") == "47.4979937,19.0403594"
    assert upstream.call_count == default_quota("osm").used() == 1
    clock.now += osm.CACHE_TTL
    assert svc.geocode("Budapest")
    assert upstream.call_count == 2
    # Changing deployment URL also changes the cache namespace.
    settings_url = settings.ROUTING_NOMINATIM_URL
    try:
        settings.ROUTING_NOMINATIM_URL = "https://other.example"
        assert svc.geocode("Budapest")
        assert upstream.call_count == 3
    finally:
        settings.ROUTING_NOMINATIM_URL = settings_url


def test_geocode_lru_bounds_memory_and_keeps_recent_entries(service, upstream, monkeypatch):
    svc, _ = service
    monkeypatch.setattr(settings, "ROUTING_DAILY_CAP", 1000)
    svc.geocode("Town A")
    for i in range(osm.CACHE_SIZE - 1):
        svc.geocode(f"Town {i}")
    svc.geocode("Town A")  # promote to newest
    svc.geocode("Town extra")
    assert len(osm._geocode_cache) == osm.CACHE_SIZE
    assert (settings.ROUTING_NOMINATIM_URL, "town a") in osm._geocode_cache
    assert (settings.ROUTING_NOMINATIM_URL, "town 0") not in osm._geocode_cache
    assert upstream.call_count == osm.CACHE_SIZE + 1


def test_concurrent_identical_geocodes_make_one_request(service, upstream):
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len(set(pool.map(lambda _: osm.OsmRoutingService().geocode("Budapest"), range(20)))) == 1
    upstream.assert_called_once()


@pytest.mark.parametrize("method", ["geocode", "get_routes"])
def test_process_wide_throttle_including_separate_instances(service, upstream, method):
    svc, clock = service
    if method == "geocode":
        svc.geocode("Budapest")
        osm.OsmRoutingService().geocode("Győr")
        svc.geocode("Szeged")
    else:
        svc.get_routes(START, END)
        osm.OsmRoutingService().get_routes(START, END)
        svc.get_routes(START, END)
    assert clock.sleeps == [1, 1]


def test_missing_geocode_is_cached_and_never_routed(service, upstream):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: [])
    svc, _ = service
    assert svc.get_routes("Unknown road", END) == []
    assert svc.get_route("Unknown road", END) == []
    upstream.assert_called_once()


@pytest.mark.parametrize("method", ["get_route", "get_routes", "geocode"])
@pytest.mark.parametrize("value", ["40.7,-74.0", "47.5 19.04", "via:Budapest", "x" * 201])
def test_public_input_limits_before_any_network(service, upstream, method, value):
    svc, _ = service
    args = (value,) if method == "geocode" else (value, END)
    with pytest.raises(InputLimitError):
        getattr(svc, method)(*args)
    upstream.assert_not_called()


def test_resolved_foreign_endpoint_never_reaches_osrm(service, upstream):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: [{"lat": "40.7", "lon": "-74.0"}])
    with pytest.raises(InputLimitError, match="service area"):
        service[0].get_routes("Foreign address", END)
    upstream.assert_called_once()


@pytest.mark.parametrize("method", ["get_routes", "geocode"])
@pytest.mark.parametrize("failure,code", [
    (requests.exceptions.ConnectTimeout("private URL secret"), "UPSTREAM_TIMEOUT"),
    (requests.exceptions.ReadTimeout("private URL secret"), "UPSTREAM_TIMEOUT"),
    (requests.exceptions.ConnectionError("private URL secret"), "UPSTREAM_ERROR"),
    (429, "RESOURCE_EXHAUSTED"), (503, "UPSTREAM_ERROR"), (302, "UPSTREAM_ERROR"),
])
def test_errors_are_clean_and_never_retried(service, upstream, method, failure, code):
    if isinstance(failure, Exception):
        upstream.side_effect = failure
    else:
        upstream.side_effect = None
        upstream.return_value = Mock(status_code=failure, text="private URL secret")
    args = ("Budapest", END) if method == "get_routes" else ("Budapest",)
    with pytest.raises(GraphQLError) as caught:
        getattr(service[0], method)(*args)
    assert caught.value.extensions == {"code": code}
    assert "private" not in str(caught.value) and "secret" not in str(caught.value)
    upstream.assert_called_once()
    assert default_quota("osm").used() == 1


@pytest.mark.parametrize("payload", [{"code": "NoRoute", "routes": []}, {"code": "Ok", "routes": []}])
def test_no_route(service, upstream, payload):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: payload)
    assert service[0].get_route(START, END) == []


@pytest.mark.parametrize("code", ["NoRoute", "NoSegment"])
def test_osrm_no_route_uses_real_http_400_shape(service, upstream, code):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=400, json=lambda: {"code": code, "message": "private upstream text"})
    assert service[0].get_routes(START, END) == []
    upstream.assert_called_once()


@pytest.mark.parametrize("payload", [{}, [{"lat": "invalid", "lon": "19.04"}], [{"lat": "47.5"}]])
def test_malformed_geocodes_are_not_cached(service, upstream, payload):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: payload)
    with pytest.raises(GraphQLError, match="Invalid geocoding response"):
        service[0].geocode("Budapest")
    assert not osm._geocode_cache


def test_unreadable_osm_budget_blocks_before_http(service, upstream):
    default_quota("osm").path.write_text("{broken")
    with pytest.raises(GraphQLError, match="counter is unavailable") as caught:
        service[0].get_routes(START, END)
    assert caught.value.extensions == {"code": "RESOURCE_EXHAUSTED"}
    upstream.assert_not_called()


@pytest.mark.parametrize("payload", [[], {}, {"code": "InvalidQuery", "message": "private"},
    {"code": "Ok", "routes": [{"distance": 1, "duration": 1, "legs": [], "geometry": "_"}]}])
def test_malformed_route_response_is_generic(service, upstream, payload):
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: payload)
    with pytest.raises(GraphQLError, match="Invalid routing response"):
        service[0].get_route(START, END)


def test_invalid_json_is_generic(service, upstream):
    upstream.side_effect = None
    response = Mock(status_code=200)
    response.json.side_effect = ValueError("private body")
    upstream.return_value = response
    with pytest.raises(GraphQLError, match="service unavailable"):
        service[0].geocode("Budapest")


@pytest.mark.parametrize("cap,calls", [(0, 0), (1, 1), (2, 2)])
def test_combined_cap_before_every_upstream_attempt(service, upstream, monkeypatch, cap, calls):
    monkeypatch.setattr(settings, "ROUTING_DAILY_CAP", cap)
    with pytest.raises(GraphQLError) as caught:
        service[0].get_routes("Budapest", "Győr")
    assert caught.value.extensions == {"code": "RESOURCE_EXHAUSTED"}
    assert upstream.call_count == default_quota("osm").used() == calls


def test_provider_switch_and_google_compatibility(service, upstream, monkeypatch):
    from app.services.google_maps import google_maps_service

    assert routing_service.get_routes(START, END)
    monkeypatch.setattr(settings, "ROUTING_PROVIDER", "google")
    for method, args, result in [("get_route", (START, END), []),
                                 ("get_routes", (START, END), []),
                                 ("geocode", ("Budapest",), "47.5,19.04")]:
        mock = Mock(return_value=result)
        monkeypatch.setattr(google_maps_service, method, mock)
        assert getattr(routing_service, method)(*args) == result
        mock.assert_called_once()
    assert upstream.call_count == 1  # no automatic provider fallback


def test_defaults_and_legacy_cap_alias(monkeypatch, service):
    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    assert Settings(_env_file=None).ROUTING_PROVIDER == "osm"
    monkeypatch.setenv("ROUTING_PROVIDER", "other")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_DAILY_CAP", 17)
    assert default_quota("osm").daily_cap == default_quota("google").daily_cap == 17
    monkeypatch.setattr(settings, "ROUTING_DAILY_CAP", 9)
    assert default_quota("osm").daily_cap == default_quota("google").daily_cap == 9


def test_osm_default_storage_and_legacy_google_path(service, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_QUOTA_PATH", None)
    assert str(default_quota("osm").path) == "/tmp/smooth-route/quota/osm_routing.json"
    assert str(default_quota("google").path) == "/tmp/smooth-route/quota/google_directions.json"
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", False)
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    assert default_quota("osm").path == tmp_path / "quota" / "osm_routing.json"


def test_public_schema_one_route_and_provider_credit(service, upstream, monkeypatch):
    from app.graphql.schema import read_schema
    import app.graphql.route_alternatives as resolver

    # Deliberately unmeasured route: exercising the real provider needs no DB.
    upstream.side_effect = None
    upstream.return_value = Mock(status_code=200, json=lambda: {"code": "Ok", "routes": []})
    monkeypatch.setattr(resolver, "get_db_session", lambda: SimpleNamespace(close=lambda: None))
    query = '{ routingProvider routeAlternatives(origin: "47.5,19.04", destination: "47.48,19.08") { fastestIndex } }'
    result = asyncio.run(read_schema.execute(query, context_value={"identity": None}))
    assert result.errors is None
    assert result.data["routingProvider"] == "osm"
    upstream.assert_called_once()
    upstream.reset_mock()
    query = '{ a: routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex } b: routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex } }'
    result = asyncio.run(read_schema.execute(query, context_value={"identity": None}))
    assert result.data is None and result.errors[0].extensions == {"code": "BAD_USER_INPUT"}
    upstream.assert_not_called()


def test_public_upstream_error_is_not_body_text(service, upstream):
    from app.graphql.schema import read_schema

    upstream.side_effect = None
    upstream.return_value = Mock(status_code=429, text="private key=secret")
    result = asyncio.run(read_schema.execute(
        '{ routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex } }',
        context_value={"identity": None}))
    assert result.errors[0].extensions == {"code": "RESOURCE_EXHAUSTED"}
    assert "private" not in result.errors[0].message
    upstream.assert_called_once()


def test_osrm_summary_dedupes_road_names_in_order():
    from app.services.routing_osm import _summary
    # Shape seen on routing.openstreetmap.de for Budapest -> Székesfehérvár.
    assert _summary([{"summary": "M1; M7, M7"}]) == "M1, M7"
    assert _summary([{"summary": "Fő utca"}, {"summary": "Fő utca, M1"}, {}]) == "Fő utca, M1"
