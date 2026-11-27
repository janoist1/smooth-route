"""Small, user-triggered HU route plans through OSRM and Nominatim.

Policy limits are process-wide, including across service instances/threads.
These public endpoints must not be used for autocomplete or bulk collection.
See docs/SECURITY.md for application-wide deployment duties and policy links.
"""
from collections import OrderedDict
from contextlib import contextmanager
import math
import threading
import time
from typing import Any

import requests
from graphql import GraphQLError

from app.core.config import settings
from app.graphql.limits import parse_lat_lng, validate_route_endpoints
from app.services.directions_quota import RoutingQuotaExceeded, default_quota

USER_AGENT = "simaut.hu road-quality map (+https://simaut.hu)"
HTTP_TIMEOUT = (2, 5)
CACHE_SIZE = 256
CACHE_TTL = 24 * 60 * 60


class _RequestGate:
    """Serialize attempts and leave at least one second between their starts."""
    def __init__(self):
        self.lock = threading.Lock()
        self.last_start: float | None = None

    @contextmanager
    def attempt(self):
        with self.lock:
            if self.last_start is not None:
                delay = 1 - (time.monotonic() - self.last_start)
                if delay > 0:
                    time.sleep(delay)
            self.last_start = time.monotonic()
            yield


_osrm_gate = _RequestGate()
_nominatim_gate = _RequestGate()
_geocode_lock = threading.Lock()
_geocode_cache: OrderedDict[tuple[str, str], tuple[float, str | None]] = OrderedDict()


def _error(message: str, code: str) -> GraphQLError:
    return GraphQLError(message, extensions={"code": code})


def _get_json(url: str, params: dict, gate: _RequestGate) -> Any:
    with gate.attempt():
        try:
            default_quota("osm").reserve()
        except RoutingQuotaExceeded as exc:
            raise _error(str(exc), "RESOURCE_EXHAUSTED") from None
        try:
            # requests.get has no automatic retries; disable redirects so a
            # single attempt cannot turn into extra, unpaced upstream calls.
            response = requests.get(
                url, params=params, headers={"User-Agent": USER_AGENT},
                timeout=HTTP_TIMEOUT, allow_redirects=False,
            )
            if response.status_code == 429:
                raise _error("Routing service rate limit reached. Please try again later.",
                             "RESOURCE_EXHAUSTED")
            if response.status_code == 400 and gate is _osrm_gate:
                body = response.json()
                if isinstance(body, dict) and body.get("code") in ("NoRoute", "NoSegment"):
                    return {"code": "NoRoute"}
            if not 200 <= response.status_code < 300:
                raise _error("Routing service unavailable. Please try again later.", "UPSTREAM_ERROR")
            return response.json()
        except requests.exceptions.Timeout:
            raise _error("Routing request timed out. Please try again later.", "UPSTREAM_TIMEOUT") from None
        except (requests.exceptions.RequestException, ValueError):
            # Never include a URL, address, credentials or upstream body in
            # exceptions/logs (including local mode).
            raise _error("Routing service unavailable. Please try again later.", "UPSTREAM_ERROR") from None


def _decode_polyline(encoded: str) -> list[dict]:
    """OSRM's precision-5 polyline to the existing {lat, lng} point contract."""
    if not isinstance(encoded, str):
        raise ValueError("invalid geometry")
    coords = []
    index = 0
    lat = lng = 0
    while index < len(encoded):
        for axis in (0, 1):
            value = shift = 0
            while True:
                if index >= len(encoded) or shift > 30:
                    raise ValueError("invalid geometry")
                byte = ord(encoded[index]) - 63
                index += 1
                if not 0 <= byte <= 63:
                    raise ValueError("invalid geometry")
                value |= (byte & 31) << shift
                shift += 5
                if byte < 32:
                    break
            delta = ~(value >> 1) if value & 1 else value >> 1
            if axis == 0:
                lat += delta
            else:
                lng += delta
        if not (-90e5 <= lat <= 90e5 and -180e5 <= lng <= 180e5):
            raise ValueError("invalid geometry")
        coords.append({"lat": lat / 1e5, "lng": lng / 1e5})
    if len(coords) < 2:
        raise ValueError("invalid geometry")
    return coords


class OsmRoutingService:
    def geocode(self, address: str) -> str | None:
        address, _ = validate_route_endpoints(address, address)
        if parse_lat_lng(address) is not None:
            return address
        base = settings.ROUTING_NOMINATIM_URL.rstrip("/")
        query = " ".join(address.split())
        key = (base, query.casefold())
        # Hold across misses: simultaneous identical queries produce one
        # lookup, and the LRU remains safe across all worker threads.
        with _geocode_lock:
            cached = _geocode_cache.get(key)
            if cached and time.monotonic() - cached[0] < CACHE_TTL:
                _geocode_cache.move_to_end(key)
                return cached[1]
            result = _get_json(base + "/search", {
                "q": query, "format": "jsonv2", "countrycodes": "hu",
                "limit": 1, "accept-language": "hu",
            }, _nominatim_gate)
            try:
                if not isinstance(result, list):
                    raise ValueError("invalid geocode")
                value = None
                if result:
                    lat, lng = float(result[0]["lat"]), float(result[0]["lon"])
                    # Validate resolved text endpoints too, before OSRM I/O.
                    value, _ = validate_route_endpoints(f"{lat},{lng}", f"{lat},{lng}")
            except (KeyError, TypeError, ValueError, IndexError):
                raise _error("Invalid geocoding response.", "UPSTREAM_ERROR") from None
            _geocode_cache[key] = (time.monotonic(), value)
            _geocode_cache.move_to_end(key)
            while len(_geocode_cache) > CACHE_SIZE:
                _geocode_cache.popitem(last=False)
            return value

    def get_route(self, origin: str, destination: str) -> list[dict]:
        routes = self.get_routes(origin, destination, max_routes=1)
        return routes[0]["points"] if routes else []

    def get_routes(self, origin: str, destination: str, max_routes: int = 3) -> list[dict]:
        origin, destination = validate_route_endpoints(origin, destination)
        limit = max(0, min(3, max_routes))
        if not limit:
            return []
        start = origin if parse_lat_lng(origin) is not None else self.geocode(origin)
        if start is None:
            return []
        end = destination if parse_lat_lng(destination) is not None else self.geocode(destination)
        if end is None:
            return []
        start_coords, end_coords = parse_lat_lng(start), parse_lat_lng(end)
        assert start_coords is not None and end_coords is not None
        lat1, lng1 = start_coords
        lat2, lng2 = end_coords
        base = settings.ROUTING_OSRM_URL.rstrip("/")
        result = _get_json(f"{base}/route/v1/driving/{lng1},{lat1};{lng2},{lat2}", {
            "alternatives": str(limit - 1) if limit > 1 else "false",
            # FOSSGIS v5.27 computes leg summaries only when steps are enabled.
            "overview": "full", "geometries": "polyline", "steps": "true",
        }, _osrm_gate)
        try:
            if result.get("code") == "NoRoute":
                return []
            if result.get("code") != "Ok":
                raise ValueError("invalid route")
            routes = []
            for route in result["routes"][:limit]:
                distance, duration = float(route["distance"]), float(route["duration"])
                if not all(math.isfinite(v) and v >= 0 for v in (distance, duration)):
                    raise ValueError("invalid route")
                routes.append({
                    "points": _decode_polyline(route["geometry"]),
                    "distance_m": distance, "duration_s": duration,
                    "summary": " · ".join(leg["summary"] for leg in route["legs"] if leg.get("summary")),
                })
            return routes
        except (AttributeError, KeyError, TypeError, ValueError):
            raise _error("Invalid routing response.", "UPSTREAM_ERROR") from None


osm_routing_service = OsmRoutingService()
