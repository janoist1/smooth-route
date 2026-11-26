"""Read side of the road-segment layer (what the GraphQL resolvers call).

Serves ``roadSegments`` (map layer) and ``routeQuality`` (route summary) from
the pre-built ``road_segments`` table. Request-time rules: no Overpass, no
torch, no numpy — just PostGIS + the pure helpers — so it runs unchanged on
the read-only deploy.

The zoom / envelope maths is pure and unit-tested; the two ``fetch_*``
functions are thin SQL.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import text

from app.services.route_quality import (
    RouteStats,
    SegmentRef,
    compute_route_stats,
    worst_segment_ids,
)
from app.services.segment_aggregation import (
    LEVEL_LOW,
    SegmentConfig,
    confidence_level,
    load_config,
)
from app.services.segment_geometry import LatLon, polyline_length_m

# Below this Leaflet zoom the segment layer returns nothing: a screen then
# spans tens of kilometres and the quality grid (roadQualityGrid) is the
# honest overview. Segments are for street-level reading.
SEGMENTS_MIN_ZOOM = 13
# Hard cap per request; when it bites, the best-supported segments win.
MAX_SEGMENTS_PER_REQUEST = 5000
# At/above this zoom a pixel is < 1 m — simplification would save nothing.
_NO_SIMPLIFY_ZOOM = 18

# routeQuality input guards (anonymous endpoint).
MAX_PATH_POINTS = 20000
# The path is sampled every ROUTE_SAMPLE_STEP_M, so work grows with its
# length, not its point count: 20 000 points zig-zagging across the country
# would mean millions of samples per anonymous request. No drivable route the
# app plans comes near this (Hungary is ~530 km across).
MAX_PATH_LENGTH_M = 2_000_000
# A path is covered by many small envelopes instead of one huge bbox, so a
# long diagonal route does not pull in every segment of the country.
_ENVELOPE_MAX_SPAN_DEG = 0.02
# ≥ 22 m in both axes up to 60° latitude, i.e. more than ROUTE_BUFFER_M.
_ENVELOPE_PAD_DEG = 0.0004


@dataclass(frozen=True)
class SegmentRecord:
    """One stored segment, geometry already as ``[(lat, lng), ...]``."""

    id: str
    path: list[LatLon]
    rqi: Optional[int]
    score: Optional[float]
    p_bad: Optional[float]
    confidence: float
    confidence_level: str
    n_images: int
    length_m: float
    road_name: Optional[str]
    highway: Optional[str]
    capture_date_min: Optional[dt.date]
    capture_date_max: Optional[dt.date]


@dataclass(frozen=True)
class RouteQualityResult:
    total_length_m: float
    covered_length_m: float
    length_by_rqi: list[float]
    mean_score: Optional[float]
    worst_segments: list[SegmentRecord]


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def should_serve_segments(zoom: int) -> bool:
    return int(zoom) >= SEGMENTS_MIN_ZOOM


def simplify_tolerance_deg(zoom: int) -> float:
    """ST_SimplifyPreserveTopology tolerance for a Leaflet zoom: half a
    screen pixel in degrees of longitude (one 256 px tile spans 360/2^zoom
    degrees), 0 once zoomed in far enough that nothing would be removed.
    """
    z = max(0, min(22, int(zoom)))
    if z >= _NO_SIMPLIFY_ZOOM:
        return 0.0
    return 0.5 * 360.0 / (256 * 2 ** z)


def normalize_path(path: Sequence[Sequence[float]]) -> list[LatLon]:
    """Validate a GraphQL ``[[lat, lng], ...]`` path. Raises ``ValueError``."""
    if len(path) > MAX_PATH_POINTS:
        raise ValueError(f"path has too many points (max {MAX_PATH_POINTS})")
    out: list[LatLon] = []
    for pt in path:
        if len(pt) < 2:
            raise ValueError("every path point must be [lat, lng]")
        lat, lng = float(pt[0]), float(pt[1])
        if not (math.isfinite(lat) and math.isfinite(lng)) or abs(lat) > 90 or abs(lng) > 180:
            raise ValueError("path point out of range (expected [lat, lng])")
        out.append((lat, lng))
    if polyline_length_m(out) > MAX_PATH_LENGTH_M:
        raise ValueError(f"path is too long (max {MAX_PATH_LENGTH_M // 1000} km)")
    return out


def path_envelopes(
    path: Sequence[LatLon],
    max_span_deg: float = _ENVELOPE_MAX_SPAN_DEG,
    pad_deg: float = _ENVELOPE_PAD_DEG,
) -> list[tuple[float, float, float, float]]:
    """Cover a path with padded ``(west, south, east, north)`` boxes.

    Consecutive points share a box until it would grow past ``max_span_deg``;
    the next box starts at the previous point so no edge falls in a gap.
    """
    boxes: list[tuple[float, float, float, float]] = []
    if not path:
        return boxes

    def close(s: float, w: float, n: float, e: float) -> None:
        boxes.append((w - pad_deg, s - pad_deg, e + pad_deg, n + pad_deg))

    south = north = path[0][0]
    west = east = path[0][1]
    points_in_box = 1
    prev = path[0]
    for lat, lng in path[1:]:
        s, n = min(south, lat), max(north, lat)
        w, e = min(west, lng), max(east, lng)
        too_big = n - s > max_span_deg or e - w > max_span_deg
        if too_big and points_in_box > 1:
            # Close the box and restart it on the edge prev→this point. (A
            # single edge longer than the span simply gets a box of its own.)
            close(south, west, north, east)
            south, north = min(prev[0], lat), max(prev[0], lat)
            west, east = min(prev[1], lng), max(prev[1], lng)
            points_in_box = 2
        else:
            south, north, west, east = s, n, w, e
            points_in_box += 1
        prev = (lat, lng)
    close(south, west, north, east)
    return boxes


def _latlng_path(geojson: str) -> list[LatLon]:
    """GeoJSON LineString ([lng, lat] order) → ``[(lat, lng), ...]``."""
    return [(c[1], c[0]) for c in json.loads(geojson)["coordinates"]]


def _record(row, cfg: SegmentConfig) -> SegmentRecord:
    return SegmentRecord(
        id=row.id,
        path=_latlng_path(row.geojson),
        rqi=row.rqi,
        score=row.score,
        p_bad=row.p_bad,
        confidence=row.confidence,
        confidence_level=confidence_level(row.confidence, row.n_images, cfg),
        n_images=row.n_images,
        length_m=row.length_m,
        road_name=row.road_name,
        highway=row.highway,
        capture_date_min=row.capture_date_min,
        capture_date_max=row.capture_date_max,
    )


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

_COLUMNS = (
    "s.id, s.rqi, s.score, s.p_bad, s.confidence, s.n_images, s.length_m, "
    "s.road_name, s.highway, s.capture_date_min, s.capture_date_max"
)


def fetch_segments_in_bbox(
    db, bbox: Sequence[float], zoom: int, cfg: Optional[SegmentConfig] = None
) -> list[SegmentRecord]:
    """Segments WITH data inside ``[minLng, minLat, maxLng, maxLat]``,
    geometry simplified for the zoom. Empty below ``SEGMENTS_MIN_ZOOM`` or for
    a malformed bbox.
    """
    if not should_serve_segments(zoom) or not bbox or len(bbox) != 4:
        return []
    cfg = cfg or load_config()
    min_lng, min_lat, max_lng, max_lat = (float(v) for v in bbox)
    tolerance = simplify_tolerance_deg(zoom)
    geom = "s.geom" if tolerance <= 0 else "ST_SimplifyPreserveTopology(s.geom, :tol)"
    rows = db.execute(
        text(
            f"""
            SELECT {_COLUMNS}, ST_AsGeoJSON({geom}, 6) AS geojson
            FROM road_segments s
            WHERE s.n_images > 0
              AND s.geom && ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326)
            ORDER BY s.n_images DESC, s.id
            LIMIT :limit
            """
        ),
        {
            "min_lng": min_lng, "min_lat": min_lat, "max_lng": max_lng, "max_lat": max_lat,
            "tol": tolerance, "limit": MAX_SEGMENTS_PER_REQUEST,
        },
    ).fetchall()
    return [_record(r, cfg) for r in rows]


def fetch_segments_near_path(
    db, path: Sequence[LatLon], cfg: Optional[SegmentConfig] = None
) -> list[SegmentRecord]:
    """Segments WITH data whose bbox touches the padded envelopes of ``path``
    (a superset of the route buffer — exact matching happens in Python)."""
    boxes = path_envelopes(path)
    if not boxes:
        return []
    cfg = cfg or load_config()
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (s.id) {_COLUMNS}, ST_AsGeoJSON(s.geom, 7) AS geojson
            FROM road_segments s
            JOIN unnest(
                   CAST(:west AS float8[]), CAST(:south AS float8[]),
                   CAST(:east AS float8[]), CAST(:north AS float8[])
                 ) AS b(west, south, east, north)
              ON s.geom && ST_MakeEnvelope(b.west, b.south, b.east, b.north, 4326)
            WHERE s.n_images > 0
            ORDER BY s.id
            """
        ),
        {
            "west": [b[0] for b in boxes], "south": [b[1] for b in boxes],
            "east": [b[2] for b in boxes], "north": [b[3] for b in boxes],
        },
    ).fetchall()
    return [_record(r, cfg) for r in rows]


def summarize_route(path: Sequence[LatLon], records: Sequence[SegmentRecord]) -> RouteQualityResult:
    """Route stats + the worst driven segments (pure given the records).

    ``worst_segments``: up to 5 by score descending, skipping segments whose
    confidence level is "low" — a single noisy frame should not headline the
    route summary.
    """
    refs = [
        SegmentRef(id=r.id, coords=r.path, rqi=r.rqi, score=r.score, length_m=r.length_m)
        for r in records
    ]
    stats: RouteStats = compute_route_stats(path, refs)
    eligible = {r.id for r in records if r.confidence_level != LEVEL_LOW}
    by_id = {r.id: r for r in records}
    return RouteQualityResult(
        total_length_m=stats.total_length_m,
        covered_length_m=stats.covered_length_m,
        length_by_rqi=stats.length_by_rqi,
        mean_score=stats.mean_score,
        worst_segments=[by_id[i] for i in worst_segment_ids(stats, refs, eligible)],
    )


def route_quality(db, path: Sequence[Sequence[float]]) -> RouteQualityResult:
    """Validate the path, load the nearby segments and summarize."""
    points = normalize_path(path)
    return summarize_route(points, fetch_segments_near_path(db, points))
