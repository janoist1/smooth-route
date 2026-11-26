"""OSM road network via the public Overpass API, with an on-disk tile cache.

The road-segment layer needs real road geometry. We fetch the drivable OSM
ways around our Street View frames in fixed lat/lon tiles (a stable grid, so a
tile fetched once is reused by every later rebuild) and cache the RAW Overpass
responses under ``data/osm/``.

Why tiles instead of one bbox per route: frames lie along routes, so a route's
bounding box is mostly empty area; only tiles that actually contain frames are
requested. Each tile query is padded (``PAD_M``) and Overpass returns the FULL
geometry of every way touching the padded tile, so:

- any way within the snapping radius of a frame is present in that frame's
  tile response, and
- a way crossing several tiles is identical in each response (deduplicated by
  OSM way id on load).

Politeness: one request at a time, a pause between requests, a generic
User-Agent with no personal data, back-off on 429/504.

Data © OpenStreetMap contributors, ODbL — anything rendering these geometries
must show that attribution.

Only this module talks to Overpass; it is never imported on the request path
(the GraphQL resolvers read the pre-built ``road_segments`` table).
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "smooth-route-dev"

# Tile edge in degrees (~5.6 km N-S, ~3.8 km E-W at 47°N). Part of the cache
# file name, so changing it simply starts a new cache generation.
TILE_DEG = 0.05
# Padding around a tile so ways just across the edge are still returned.
PAD_M = 100.0

# Drivable classes (plus the *_link ramps of the classes that have them).
HIGHWAY_CLASSES = (
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "service",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
    "tertiary_link",
)

_M_PER_DEG_LAT = 111_320.0

Tile = tuple[int, int]  # (lat index, lon index) on the TILE_DEG grid


class OverpassError(RuntimeError):
    """Overpass could not be reached or returned an unusable answer."""


@dataclass(frozen=True)
class Way:
    """One OSM way reduced to what the segment builder needs."""

    id: int
    coords: tuple[tuple[float, float], ...]  # ((lat, lon), ...)
    name: Optional[str]
    highway: str


# --------------------------------------------------------------------------
# Tile grid (pure)
# --------------------------------------------------------------------------

def tile_of(lat: float, lon: float, size: float = TILE_DEG) -> Tile:
    """Grid tile containing a point. The epsilon keeps exact multiples stable."""
    return (math.floor(lat / size + 1e-9), math.floor(lon / size + 1e-9))


def tile_bounds(tile: Tile, size: float = TILE_DEG) -> tuple[float, float, float, float]:
    """(south, west, north, east) of a tile, unpadded."""
    iy, ix = tile
    return (iy * size, ix * size, (iy + 1) * size, (ix + 1) * size)


def tiles_for_points(points: Iterable[tuple[float, float]], size: float = TILE_DEG) -> set[Tile]:
    """The set of tiles occupied by (lat, lon) points."""
    return {tile_of(lat, lon, size) for lat, lon in points}


def pad_bounds(bounds: tuple[float, float, float, float], pad_m: float = PAD_M
               ) -> tuple[float, float, float, float]:
    """Grow (south, west, north, east) by ``pad_m`` metres on every side."""
    south, west, north, east = bounds
    dlat = pad_m / _M_PER_DEG_LAT
    mid = math.radians((south + north) / 2.0)
    dlon = pad_m / (_M_PER_DEG_LAT * max(0.01, math.cos(mid)))
    return (south - dlat, west - dlon, north + dlat, east + dlon)


# Main roads worth collecting on their own (no motorways: almost always fine).
MAIN_ROAD_CLASSES = (
    "trunk", "primary", "secondary",
    "trunk_link", "primary_link", "secondary_link",
)


def build_query(
    bounds: tuple[float, float, float, float],
    timeout_s: int = 120,
    highway_classes: tuple[str, ...] = HIGHWAY_CLASSES,
) -> str:
    """Overpass QL for the ways of the given highway classes (default: all
    drivable ones) in (south, west, north, east)."""
    south, west, north, east = bounds
    classes = "|".join(highway_classes)
    return (
        f"[out:json][timeout:{timeout_s}];"
        f'way["highway"~"^({classes})$"]'
        f"({south:.6f},{west:.6f},{north:.6f},{east:.6f});"
        "out tags geom qt;"
    )


def cache_path(cache_dir: Path | str, tile: Tile, size: float = TILE_DEG) -> Path:
    """Cache file of a tile, e.g. ``data/osm/ways_d050_949_381.json``."""
    iy, ix = tile
    return Path(cache_dir) / f"ways_d{round(size * 1000):03d}_{iy}_{ix}.json"


# --------------------------------------------------------------------------
# Response parsing (pure)
# --------------------------------------------------------------------------

def parse_ways(payload: dict, highway_classes: tuple[str, ...] = HIGHWAY_CLASSES) -> list[Way]:
    """Turn a raw Overpass JSON response into ``Way`` objects.

    Skips non-ways, area polygons (``area=yes`` — plazas, not carriageways),
    classes outside ``highway_classes`` and anything without a usable line.
    Consecutive duplicate vertices are dropped (they would make zero-length
    edges with an undefined bearing).
    """
    ways: list[Way] = []
    for el in payload.get("elements") or []:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        highway = tags.get("highway")
        if highway not in highway_classes or tags.get("area") == "yes":
            continue
        coords: list[tuple[float, float]] = []
        for pt in el.get("geometry") or []:
            if not pt or pt.get("lat") is None or pt.get("lon") is None:
                continue
            ll = (float(pt["lat"]), float(pt["lon"]))
            if not coords or coords[-1] != ll:
                coords.append(ll)
        if len(coords) < 2:
            continue
        name = tags.get("name") or tags.get("ref") or None
        ways.append(Way(id=int(el["id"]), coords=tuple(coords), name=name, highway=highway))
    return ways


def _check_payload(payload: object) -> dict:
    """Reject answers that are valid JSON but not a complete result."""
    if not isinstance(payload, dict) or "elements" not in payload:
        raise OverpassError("Overpass answer has no 'elements'")
    remark = payload.get("remark")
    # Overpass reports a server-side timeout / out-of-memory as a 200 with a
    # remark and a truncated element list — never cache that.
    if remark and re.search(r"error|timed out|out of memory", str(remark), re.I):
        raise OverpassError(f"Overpass runtime error: {remark}")
    return payload


# --------------------------------------------------------------------------
# Fetch + cache
# --------------------------------------------------------------------------

HttpPost = Callable[[str, str, float], tuple[int, str, Optional[float]]]


def _httpx_post(url: str, query: str, timeout_s: float) -> tuple[int, str, Optional[float]]:
    """POST the query. Returns (status, body, retry_after_seconds)."""
    import httpx  # local import: keeps the module importable without httpx

    try:
        resp = httpx.post(
            url,
            data={"data": query},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout_s,
        )
    except httpx.HTTPError as exc:
        raise OverpassError(f"Overpass request failed: {exc.__class__.__name__}: {exc}") from exc
    retry_after: Optional[float] = None
    try:
        retry_after = float(resp.headers.get("Retry-After", ""))
    except ValueError:
        pass
    return resp.status_code, resp.text, retry_after


class OverpassClient:
    """Sequential, cached Overpass access for road tiles.

    ``retries`` / ``timeout_s`` are constructor arguments because the two
    callers want opposite behaviour: the offline builder is patient (Overpass
    is frequently slow), the job hook must fail fast and skip.
    """

    def __init__(
        self,
        cache_dir: Path | str,
        *,
        url: Optional[str] = None,
        tile_deg: float = TILE_DEG,
        pad_m: float = PAD_M,
        timeout_s: float = 240.0,
        retries: int = 4,
        pause_s: float = 2.0,
        http_post: Optional[HttpPost] = None,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = print,
    ):
        self.cache_dir = Path(cache_dir)
        self.url = url or os.environ.get("OVERPASS_URL") or OVERPASS_URL
        self.tile_deg = tile_deg
        self.pad_m = pad_m
        self.timeout_s = timeout_s
        self.retries = retries
        self.pause_s = pause_s
        self._post = http_post or _httpx_post
        self._sleep = sleep
        self._log = log
        self._requests_made = 0

    # -- cache ------------------------------------------------------------
    def is_cached(self, tile: Tile) -> bool:
        return cache_path(self.cache_dir, tile, self.tile_deg).is_file()

    def read_cached(self, tile: Tile) -> Optional[dict]:
        path = cache_path(self.cache_dir, tile, self.tile_deg)
        if not path.is_file():
            return None
        try:
            return _check_payload(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OverpassError):
            # A corrupt cache file is treated as missing and refetched.
            return None

    def _write_cache(self, tile: Tile, body: str) -> None:
        path = cache_path(self.cache_dir, tile, self.tile_deg)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)  # atomic: a reader never sees a half-written tile

    # -- network ----------------------------------------------------------
    def fetch_tile(self, tile: Tile) -> dict:
        """Return the tile's raw payload, from cache or (once) from Overpass."""
        cached = self.read_cached(tile)
        if cached is not None:
            return cached

        bounds = pad_bounds(tile_bounds(tile, self.tile_deg), self.pad_m)
        # Server-side budget a little under our client timeout.
        query = build_query(bounds, timeout_s=max(25, int(self.timeout_s) - 30))
        last_error = "no attempt"
        for attempt in range(self.retries + 1):
            if self._requests_made:
                self._sleep(self.pause_s)  # be polite between requests
            self._requests_made += 1
            try:
                status, body, retry_after = self._post(self.url, query, self.timeout_s)
            except OverpassError as exc:
                last_error = str(exc)
            else:
                if status == 200:
                    try:
                        payload = _check_payload(json.loads(body))
                    except ValueError as exc:
                        last_error = f"invalid JSON: {exc}"
                    except OverpassError as exc:
                        last_error = str(exc)
                    else:
                        self._write_cache(tile, body)
                        return payload
                else:
                    last_error = f"HTTP {status}"
                    if status not in (429, 502, 503, 504):
                        break  # a client error will not get better by retrying
                    if retry_after:
                        self._sleep(min(120.0, retry_after))
            if attempt < self.retries:
                wait = min(120.0, 15.0 * (2 ** attempt))
                self._log(f"  overpass: tile {tile} failed ({last_error}); retry in {wait:.0f}s")
                self._sleep(wait)
        raise OverpassError(f"tile {tile}: {last_error}")

    def load_ways(self, tiles: Iterable[Tile], *, allow_fetch: bool = True) -> dict[int, Way]:
        """All ways of the given tiles, deduplicated by OSM way id.

        ``allow_fetch=False`` reads the cache only and raises ``OverpassError``
        for a missing tile (used to prove a rebuild needs no network).
        """
        ways: dict[int, Way] = {}
        ordered = sorted(set(tiles))
        for i, tile in enumerate(ordered, 1):
            cached = self.is_cached(tile)
            if not cached and not allow_fetch:
                raise OverpassError(f"tile {tile} is not cached and fetching is disabled")
            started = time.monotonic()
            payload = self.fetch_tile(tile)
            parsed = parse_ways(payload)
            for way in parsed:
                ways.setdefault(way.id, way)
            if not cached:
                self._log(
                    f"  overpass: tile {i}/{len(ordered)} {tile} fetched "
                    f"({len(parsed)} ways, {time.monotonic() - started:.0f}s)"
                )
        return ways


def network_cache_path(
    cache_dir: Path | str, bounds: tuple[float, float, float, float],
    highway_classes: tuple[str, ...],
) -> Path:
    """Cache file of one whole-area network query (bounds + classes hashed)."""
    import hashlib

    tag = hashlib.sha1(
        json.dumps([[round(b, 5) for b in bounds], sorted(highway_classes)]).encode()
    ).hexdigest()[:10]
    return Path(cache_dir) / f"network_{tag}.json"


def fetch_network(
    cache_dir: Path | str,
    bounds: tuple[float, float, float, float],
    highway_classes: tuple[str, ...] = MAIN_ROAD_CLASSES,
    *,
    allow_fetch: bool = True,
    url: Optional[str] = None,
    timeout_s: float = 240.0,
    http_post: Optional[HttpPost] = None,
    log: Callable[[str], None] = print,
) -> dict[int, Way]:
    """The ways of ``highway_classes`` in (south, west, north, east) from ONE
    Overpass request, cached raw on disk like the tiles — asked for once,
    never refetched. ``allow_fetch=False`` uses the cache only.
    """
    path = network_cache_path(cache_dir, bounds, highway_classes)
    if path.is_file():
        try:
            return {w.id: w for w in parse_ways(
                _check_payload(json.loads(path.read_text(encoding="utf-8"))), highway_classes)}
        except (ValueError, OverpassError):
            pass  # corrupt cache file → fetch again
    if not allow_fetch:
        raise OverpassError(f"network {path.name} is not cached and fetching is disabled")

    query = build_query(bounds, timeout_s=max(25, int(timeout_s) - 30),
                        highway_classes=highway_classes)
    post = http_post or _httpx_post
    endpoint = url or os.environ.get("OVERPASS_URL") or OVERPASS_URL
    started = time.monotonic()
    status, body, _retry_after = post(endpoint, query, timeout_s)
    if status != 200:
        raise OverpassError(f"network query: HTTP {status}")
    try:
        payload = _check_payload(json.loads(body))
    except ValueError as exc:
        raise OverpassError(f"network query: invalid JSON: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    ways = {w.id: w for w in parse_ways(payload, highway_classes)}
    log(f"  overpass: network fetched ({len(ways)} ways, {len(body) / 1e6:.1f} MB, "
        f"{time.monotonic() - started:.0f}s) → {path.name}")
    return ways
