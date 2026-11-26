"""Whole-area main-road network query: asked for once, cached raw, never a
bad answer in the cache. Plus the HTTP adapter with a fake httpx (no network)."""
import json
from types import SimpleNamespace

import pytest

from app.services import osm_overpass
from app.services.osm_overpass import (
    OverpassError,
    _httpx_post,
    fetch_network,
    network_cache_path,
)

BOUNDS = (47.4, 19.0, 47.6, 19.2)                       # south, west, north, east


def way(id, highway):
    return {"type": "way", "id": id, "tags": {"highway": highway},
            "geometry": [{"lat": 47.50, "lon": 19.05}, {"lat": 47.51, "lon": 19.05}]}


BODY = json.dumps({"version": 0.6, "elements": [
    way(1, "primary"), way(2, "secondary_link"), way(3, "residential")]})


class FakeHttp:
    def __init__(self, status=200, body=BODY):
        self.answer = (status, body, None)
        self.calls = []

    def __call__(self, url, query, timeout_s):
        self.calls.append((url, query, timeout_s))
        return self.answer


def quiet(message):
    pass


def test_cache_file_name_depends_on_bounds_and_classes_only(tmp_path):
    a = network_cache_path(tmp_path, BOUNDS, ("primary", "trunk"))
    assert a.parent == tmp_path and a.name.startswith("network_") and a.suffix == ".json"
    assert a == network_cache_path(tmp_path, BOUNDS, ("trunk", "primary"))      # order-free
    assert a == network_cache_path(tmp_path, tuple(b + 1e-7 for b in BOUNDS), ("primary", "trunk"))
    assert a != network_cache_path(tmp_path, BOUNDS, ("primary",))
    assert a != network_cache_path(tmp_path, (47.4, 19.0, 47.6, 19.3), ("primary", "trunk"))


def test_network_is_fetched_once_and_then_read_from_the_cache(tmp_path):
    http = FakeHttp()
    logged = []
    ways = fetch_network(tmp_path, BOUNDS, url="https://overpass.invalid/api", http_post=http,
                         log=logged.append)

    assert sorted(ways) == [1, 2]                       # main roads only; residential dropped
    (url, query, timeout_s), = http.calls
    assert url == "https://overpass.invalid/api" and timeout_s == 240.0
    assert "primary" in query and "[timeout:210]" in query
    cached = network_cache_path(tmp_path, BOUNDS, osm_overpass.MAIN_ROAD_CLASSES)
    assert cached.read_text(encoding="utf-8") == BODY   # raw answer, nothing else left behind
    assert [p.name for p in tmp_path.iterdir()] == [cached.name]
    assert len(logged) == 1 and "2 ways" in logged[0] and cached.name in logged[0]

    again = fetch_network(tmp_path, BOUNDS, http_post=http, log=quiet)
    offline = fetch_network(tmp_path, BOUNDS, allow_fetch=False, log=quiet)
    assert sorted(again) == sorted(offline) == [1, 2] and len(http.calls) == 1


def test_endpoint_falls_back_to_the_environment_then_the_default(tmp_path, monkeypatch):
    http = FakeHttp()
    monkeypatch.setenv("OVERPASS_URL", "https://mirror.invalid/api")
    fetch_network(tmp_path / "a", BOUNDS, http_post=http, log=quiet)
    monkeypatch.delenv("OVERPASS_URL")
    fetch_network(tmp_path / "b", BOUNDS, http_post=http, log=quiet)
    assert [call[0] for call in http.calls] == ["https://mirror.invalid/api",
                                                osm_overpass.OVERPASS_URL]


def test_offline_without_a_cache_is_an_error_not_a_request(tmp_path):
    http = FakeHttp()
    with pytest.raises(OverpassError, match="not cached and fetching is disabled"):
        fetch_network(tmp_path, BOUNDS, allow_fetch=False, http_post=http, log=quiet)
    assert http.calls == []


def test_corrupt_cache_file_is_fetched_again(tmp_path):
    cached = network_cache_path(tmp_path, BOUNDS, osm_overpass.MAIN_ROAD_CLASSES)
    cached.write_text("{not json", encoding="utf-8")
    http = FakeHttp()
    assert sorted(fetch_network(tmp_path, BOUNDS, http_post=http, log=quiet)) == [1, 2]
    assert len(http.calls) == 1 and cached.read_text(encoding="utf-8") == BODY


@pytest.mark.parametrize("status, body, message", [
    (429, "slow down", "HTTP 429"),
    (200, "<html>busy</html>", "invalid JSON"),
    (200, json.dumps({"version": 0.6}), "no 'elements'"),
    (200, json.dumps({"elements": [], "remark": "runtime error: Query timed out"}),
     "runtime error"),
])
def test_bad_answers_are_errors_and_never_cached(tmp_path, status, body, message):
    with pytest.raises(OverpassError, match=message):
        fetch_network(tmp_path, BOUNDS, http_post=FakeHttp(status, body), log=quiet)
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ _httpx_post

def test_http_adapter_posts_the_query_and_reads_retry_after(monkeypatch):
    httpx = pytest.importorskip("httpx")
    seen = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        seen.update(url=url, data=data, headers=headers, timeout=timeout)
        return SimpleNamespace(status_code=429, text="busy", headers=seen["reply_headers"])

    monkeypatch.setattr(httpx, "post", fake_post)
    seen["reply_headers"] = {"Retry-After": "12"}
    assert _httpx_post("https://overpass.invalid/api", "[out:json];", 30.0) == (429, "busy", 12.0)
    assert seen["data"] == {"data": "[out:json];"} and seen["timeout"] == 30.0
    assert seen["headers"]["User-Agent"] == osm_overpass.USER_AGENT

    seen["reply_headers"] = {}                          # no / unparsable header → None
    assert _httpx_post("https://overpass.invalid/api", "q", 30.0) == (429, "busy", None)


def test_http_adapter_turns_transport_errors_into_overpass_errors(monkeypatch):
    httpx = pytest.importorskip("httpx")

    def failing_post(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", failing_post)
    with pytest.raises(OverpassError, match="ConnectError: no route to host"):
        _httpx_post("https://overpass.invalid/api", "q", 30.0)
