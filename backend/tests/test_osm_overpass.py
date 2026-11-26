"""Overpass tiles, query, parsing and the cached client (no network)."""
import json

import pytest

from app.services.osm_overpass import (
    HIGHWAY_CLASSES,
    OverpassClient,
    OverpassError,
    build_query,
    cache_path,
    pad_bounds,
    parse_ways,
    tile_bounds,
    tile_of,
    tiles_for_points,
)


def way(id, coords, **tags):
    return {
        "type": "way", "id": id,
        "geometry": [{"lat": la, "lon": lo} for la, lo in coords],
        "tags": tags,
    }


PAYLOAD = {
    "version": 0.6,
    "elements": [
        way(1, [(47.50, 19.05), (47.501, 19.051)], highway="residential", name="Fő utca"),
        way(2, [(47.50, 19.05), (47.50, 19.05), (47.502, 19.05)], highway="primary", ref="4"),
        way(3, [(47.50, 19.05), (47.51, 19.05)], highway="footway"),               # not drivable
        way(4, [(47.50, 19.05), (47.51, 19.05)], highway="service", area="yes"),   # a plaza
        way(5, [(47.50, 19.05)], highway="tertiary"),                               # no line
        {"type": "node", "id": 9, "lat": 47.5, "lon": 19.05},
        way(6, [(47.50, 19.05), (47.503, 19.05)], highway="motorway_link"),
    ],
}


class FakeHttp:
    """Scripted Overpass: pops one (status, body, retry_after) per call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, query, timeout_s):
        self.calls.append((url, query, timeout_s))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(tmp_path, http, **kw):
    sleeps = []
    c = OverpassClient(tmp_path, http_post=http, sleep=sleeps.append, log=lambda _m: None, **kw)
    return c, sleeps


OK = (200, json.dumps(PAYLOAD), None)


# ---- tile grid ------------------------------------------------------------

def test_tile_of_and_bounds_round_trip():
    tile = tile_of(47.512, 19.07)
    assert tile == (950, 381)
    south, west, north, east = tile_bounds(tile)
    assert south == pytest.approx(47.5) and north == pytest.approx(47.55)
    assert west == pytest.approx(19.05) and east == pytest.approx(19.10)
    assert south <= 47.512 < north and west <= 19.07 < east


def test_tile_of_is_stable_on_grid_lines_and_negative_coordinates():
    assert tile_of(47.5, 19.05) == (950, 381)          # exact multiples stay put
    assert tile_of(47.55, 19.1) == (951, 382)
    assert tile_of(-0.01, -0.01) == (-1, -1)


def test_tiles_for_points_deduplicates():
    points = [(47.512, 19.07), (47.52, 19.09), (47.56, 19.07)]
    assert tiles_for_points(points) == {(950, 381), (951, 381)}
    assert tiles_for_points([]) == set()


def test_pad_bounds_adds_about_100_m():
    south, west, north, east = pad_bounds((47.5, 19.05, 47.55, 19.10), 100)
    assert (47.5 - south) * 111_320 == pytest.approx(100, rel=0.01)
    assert (north - 47.55) * 111_320 == pytest.approx(100, rel=0.01)
    # A degree of longitude is shorter → more degrees for the same metres.
    assert (19.05 - west) > (47.5 - south)
    assert (19.05 - west) * 111_320 * 0.6752 == pytest.approx(100, rel=0.02)


def test_build_query_lists_drivable_classes_and_bbox_order():
    q = build_query((47.5, 19.05, 47.55, 19.1), timeout_s=90)
    assert q.startswith("[out:json][timeout:90];")
    assert "(47.500000,19.050000,47.550000,19.100000)" in q        # south,west,north,east
    assert "out tags geom" in q
    for cls in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
                "residential", "living_street", "service", "motorway_link", "tertiary_link"):
        assert cls in HIGHWAY_CLASSES and cls in q
    for excluded in ("footway", "cycleway", "track", "path", "pedestrian"):
        assert excluded not in q


def test_cache_path_encodes_tile_and_size(tmp_path):
    assert cache_path(tmp_path, (950, 381)).name == "ways_d050_950_381.json"
    assert cache_path(tmp_path, (950, 381), size=0.1).name == "ways_d100_950_381.json"


# ---- parsing --------------------------------------------------------------

def test_parse_ways_keeps_only_usable_drivable_lines():
    ways = {w.id: w for w in parse_ways(PAYLOAD)}
    assert set(ways) == {1, 2, 6}
    assert ways[1].name == "Fő utca" and ways[1].highway == "residential"
    assert ways[1].coords == ((47.50, 19.05), (47.501, 19.051))
    assert ways[2].name == "4"                       # falls back to the ref
    assert len(ways[2].coords) == 2                  # duplicate vertex dropped
    assert ways[6].name is None


def test_parse_ways_tolerates_junk():
    assert parse_ways({}) == []
    assert parse_ways({"elements": None}) == []
    broken = {"elements": [way(1, [(47.5, 19.0), (47.6, 19.0)], highway="primary")]}
    broken["elements"][0]["geometry"].insert(1, None)            # clipped node
    assert len(parse_ways(broken)[0].coords) == 2


# ---- client ---------------------------------------------------------------

def test_fetch_caches_the_raw_response_and_never_refetches(tmp_path):
    http = FakeHttp(OK)
    c, _ = client(tmp_path, http)
    tile = (950, 381)
    assert not c.is_cached(tile)

    payload = c.fetch_tile(tile)
    assert len(payload["elements"]) == len(PAYLOAD["elements"])
    assert c.is_cached(tile)
    assert json.loads(cache_path(tmp_path, tile).read_text()) == PAYLOAD      # raw, as received
    assert not list(tmp_path.glob("*.tmp*"))                                    # atomic write

    # Second call (and a brand-new client) are served from disk: no request.
    assert c.fetch_tile(tile) == PAYLOAD
    c2, _ = client(tmp_path, FakeHttp())
    assert set(c2.load_ways([tile])) == {1, 2, 6}
    assert len(http.calls) == 1


def test_request_uses_the_padded_tile_bbox(tmp_path):
    http = FakeHttp(OK)
    c, _ = client(tmp_path, http)
    c.fetch_tile((950, 381))
    _url, query, _timeout = http.calls[0]
    assert "(47.499" in query and ",47.550" in query       # 100 m outside 47.5 / 47.55
    assert "19.048" in query and "19.101" in query


def test_retries_transient_errors_with_backoff(tmp_path):
    http = FakeHttp((504, "busy", None), (429, "slow down", 7.0), OK)
    c, sleeps = client(tmp_path, http, retries=3, pause_s=2.0)
    assert set(c.load_ways([(950, 381)])) == {1, 2, 6}
    assert len(http.calls) == 3
    assert 7.0 in sleeps                    # honours Retry-After
    assert 15.0 in sleeps and 30.0 in sleeps  # exponential back-off
    assert sleeps.count(2.0) == 2           # polite pause before each further request


def test_gives_up_after_the_retries_and_caches_nothing(tmp_path):
    http = FakeHttp((504, "", None), (504, "", None))
    c, _ = client(tmp_path, http, retries=1)
    with pytest.raises(OverpassError, match="HTTP 504"):
        c.fetch_tile((950, 381))
    assert len(http.calls) == 2
    assert not c.is_cached((950, 381))


def test_fail_fast_mode_makes_a_single_attempt(tmp_path):
    http = FakeHttp(OverpassError("connect timeout"))
    c, sleeps = client(tmp_path, http, retries=0)
    with pytest.raises(OverpassError, match="connect timeout"):
        c.load_ways([(950, 381)])
    assert len(http.calls) == 1 and sleeps == []


def test_client_error_is_not_retried(tmp_path):
    http = FakeHttp((400, "bad query", None))
    c, _ = client(tmp_path, http, retries=5)
    with pytest.raises(OverpassError, match="HTTP 400"):
        c.fetch_tile((950, 381))
    assert len(http.calls) == 1


def test_server_side_timeout_remark_is_an_error_not_a_cache_entry(tmp_path):
    truncated = json.dumps({"elements": [], "remark": "runtime error: Query timed out in ..."})
    http = FakeHttp((200, truncated, None), (200, "<html>not json</html>", None))
    c, _ = client(tmp_path, http, retries=1)
    with pytest.raises(OverpassError):
        c.fetch_tile((950, 381))
    assert not c.is_cached((950, 381))


def test_offline_mode_refuses_to_fetch(tmp_path):
    http = FakeHttp(OK)
    c, _ = client(tmp_path, http)
    with pytest.raises(OverpassError, match="not cached"):
        c.load_ways([(950, 381)], allow_fetch=False)
    assert http.calls == []


def test_corrupt_cache_file_is_refetched(tmp_path):
    cache_path(tmp_path, (950, 381)).write_text("{truncated")
    http = FakeHttp(OK)
    c, _ = client(tmp_path, http)
    assert set(c.load_ways([(950, 381)])) == {1, 2, 6}
    assert len(http.calls) == 1


def test_ways_spanning_tiles_are_deduplicated(tmp_path):
    http = FakeHttp(OK, OK)
    c, sleeps = client(tmp_path, http, pause_s=2.0)
    ways = c.load_ways([(950, 381), (950, 382)])
    assert sorted(ways) == [1, 2, 6]
    assert len(http.calls) == 2
    assert sleeps == [2.0]                  # one request at a time, with a pause
