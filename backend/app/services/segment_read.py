"""Read side of the road-segment layer (what the GraphQL resolvers call).

Serves ``roadSegments`` (map layer), ``routeQuality`` (route summary),
``Point.segmentId`` and ``segmentFrames`` (frame ↔ segment links) from the
pre-built ``road_segments`` table. Request-time rules: no Overpass, no torch,
no numpy — just PostGIS + the pure helpers — so it runs unchanged on the
read-only deploy.

Frame ↔ segment links are re-derived against all stored geometry, including
unmeasured roads. At a shared piece boundary, the builder's linear-reference
rule assigns the frame to the following piece, regardless of travel direction.

The zoom / envelope maths is pure and unit-tested; the ``fetch_*`` functions
are thin SQL.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, replace
from typing import Optional, Sequence, cast

from sqlalchemy import text

from app.services.map_matching import (
    DEFAULT_MAX_BEARING_DIFF_DEG,
    DEFAULT_MAX_DISTANCE_M,
    LineIndex,
    Match,
)
from app.services.route_scoring import speed_kmh
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
    confidence_reason,
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
# ≥ 22 m in both axes up to 60° latitude, i.e. more than ROUTE_BUFFER_M and
# more than the frame snapping radius.
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
    confidence_reason: Optional[str]
    n_images: int
    length_m: float
    road_name: Optional[str]
    highway: Optional[str]
    capture_date_min: Optional[dt.date]
    capture_date_max: Optional[dt.date]
    # Midpoint of the (unsimplified) piece and the road's bearing there —
    # where a Street View link should look.
    mid: Optional[LatLon] = None
    mid_heading: Optional[float] = None
    maxspeed_kmh: Optional[int] = None  # OSM tag; None = class default (route_scoring)


@dataclass(frozen=True)
class RouteQualityResult:
    total_length_m: float
    covered_length_m: float
    length_by_rqi: list[float]
    mean_score: Optional[float]
    worst_segments: list[SegmentRecord]
    impact_score: Optional[float] = None  # speed-weighted badness (route_scoring)
    mean_rqi: Optional[int] = None  # mean_score through the segment cut-points


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def should_serve_segments(zoom: int) -> bool:
    return int(zoom) >= SEGMENTS_MIN_ZOOM


def simplify_tolerance_deg(zoom: int) -> float:
    """ST_Simplify tolerance for a Leaflet zoom: half a
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


DENSIFY_MAX_STEP_M = 1000.0
MAX_SEGMENT_CANDIDATES = 20000


class TooManySegmentCandidates(ValueError):
    """The envelope query matched more segments than the candidate cap."""


def densify_path(path: Sequence[LatLon], max_step_m: float = DENSIFY_MAX_STEP_M) -> list[LatLon]:
    """Insert points along each edge so consecutive points are ≤ ``max_step_m``
    apart. Keeps every original vertex; a long straight edge becomes many
    short ones, so no single envelope has to cover it."""
    if not path:
        return []
    out: list[LatLon] = [path[0]]
    for a, b in zip(path, path[1:]):
        dy = (b[0] - a[0]) * 111_320.0
        dx = (b[1] - a[1]) * 111_320.0 * math.cos(math.radians((a[0] + b[0]) / 2.0))
        steps = max(1, math.ceil(math.hypot(dx, dy) / max_step_m))
        for i in range(1, steps):
            t = i / steps
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


def path_envelopes(
    path: Sequence[LatLon],
    max_span_deg: float = _ENVELOPE_MAX_SPAN_DEG,
    pad_deg: float = _ENVELOPE_PAD_DEG,
) -> list[tuple[float, float, float, float]]:
    """Cover a path with padded ``(west, south, east, north)`` boxes.

    The path is first densified (points ≤ 1 km apart) so a long edge is split
    over many small boxes instead of one huge one. Consecutive points share a
    box until it would grow past ``max_span_deg``; the next box starts at the
    previous point so no edge falls in a gap.
    """
    boxes: list[tuple[float, float, float, float]] = []
    if not path:
        return boxes
    path = densify_path(path)

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
    built_on = row.updated_at.date() if row.updated_at else dt.date.today()
    mid = None
    if row.mid_lat is not None and row.mid_lng is not None:
        mid = (row.mid_lat, row.mid_lng)
    return SegmentRecord(
        id=row.id,
        path=_latlng_path(row.geojson),
        rqi=row.rqi,
        score=row.score,
        p_bad=row.p_bad,
        confidence=row.confidence,
        confidence_level=confidence_level(row.confidence, row.n_images, cfg),
        confidence_reason=confidence_reason(
            row.confidence, row.n_images, row.score, row.capture_date_max, built_on, cfg,
            unlabelled_area=bool(getattr(row, "unlabelled_area", False)),
        ),
        n_images=row.n_images,
        length_m=row.length_m,
        road_name=row.road_name,
        highway=row.highway,
        capture_date_min=row.capture_date_min,
        capture_date_max=row.capture_date_max,
        mid=mid,
        mid_heading=row.mid_heading,
        maxspeed_kmh=getattr(row, "maxspeed_kmh", None),
    )


def _is_measured(segment: SegmentRecord) -> bool:
    return segment.n_images > 0 and segment.score is not None and segment.rqi is not None


class _FrameSegmentIndex:
    """Snap to stored pieces, with the builder's half-open boundary rule."""

    def __init__(self, segments: Sequence[SegmentRecord]):
        self.by_id = {s.id: s for s in segments}
        self.index = LineIndex([SegmentRef(s.id, s.path, s.rqi, s.score) for s in segments])

    def snap(self, point: LatLon, heading: Optional[float]) -> Optional[Match]:
        match = self.index.snap(
            point, heading, max_distance_m=DEFAULT_MAX_DISTANCE_M,
            max_bearing_diff_deg=DEFAULT_MAX_BEARING_DIFF_DEG,
        )
        if match is None:
            return None
        segment = self.by_id[cast(str, match.line_id)]
        # Pieces retain their chain orientation. Only the chain's final end
        # is closed; every interior endpoint belongs to the following piece.
        # Do not use the heading to choose between two pieces of one road:
        # the builder matches the whole line before assigning its offset.
        if abs(match.offset_m - polyline_length_m(segment.path)) <= 1e-7:
            anchor, sep, piece = segment.id.rpartition(":")
            if sep and piece.isdigit():
                following = self.by_id.get(f"{anchor}:{int(piece) + 1}")
                if following is not None and segment.path[-1] == following.path[0]:
                    return replace(match, line_id=following.id, offset_m=0.0)
        return match


def match_frames_to_segment(
    segment_id: str, segments: Sequence[SegmentRecord], frames: Sequence
) -> list[int]:
    """Ids of the ``frames`` (objects with id / lat / lon / heading) that
    snap to ``segment_id`` rather than to any other of ``segments``, ordered
    along the segment. Pure — the same rule the builder applies.
    """
    target = next((s for s in segments if s.id == segment_id), None)
    if target is None or not _is_measured(target):
        return []
    index = _FrameSegmentIndex(segments)
    hits: list[tuple[float, int]] = []
    for frame in frames:
        match = index.snap(
            (frame.lat, frame.lon), frame.heading,
        )
        if match is not None and match.line_id == segment_id:
            hits.append((match.offset_m, frame.id))
    return [frame_id for _offset, frame_id in sorted(hits)]


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

# The midpoint and the bearing around it come from the stored (unsimplified)
# geometry, so they do not move with the zoom-dependent simplification.
_COLUMNS = (
    "s.id, s.rqi, s.score, s.p_bad, s.confidence, s.unlabelled_area, s.n_images, s.length_m, "
    "s.road_name, s.highway, s.maxspeed_kmh, s.capture_date_min, s.capture_date_max, s.updated_at, "
    "ST_Y(ST_LineInterpolatePoint(s.geom, 0.5)) AS mid_lat, "
    "ST_X(ST_LineInterpolatePoint(s.geom, 0.5)) AS mid_lng, "
    "degrees(ST_Azimuth(ST_LineInterpolatePoint(s.geom, 0.45), "
    "ST_LineInterpolatePoint(s.geom, 0.55))) AS mid_heading"
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
    # Plain Douglas-Peucker: each segment is one short LineString (~7 points),
    # so topology preservation buys nothing, and ST_SimplifyPreserveTopology
    # (a GEOS round trip per row) was ~85 ms of a ~110 ms zoom-13 Budapest
    # query vs ~4 ms here. preserveCollapsed keeps tiny pieces from vanishing.
    geom = "s.geom" if tolerance <= 0 else "ST_Simplify(s.geom, :tol, true)"
    rows = db.execute(
        text(
            f"""
            SELECT {_COLUMNS}, ST_AsGeoJSON({geom}, 6) AS geojson
            FROM road_segments s
            WHERE s.n_images > 0
              AND s.score IS NOT NULL AND s.rqi IS NOT NULL
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
    records = [_record(r, cfg) for r in rows]
    return [r for r in records if _is_measured(r)]


def fetch_segments_in_boxes(
    db, boxes: Sequence[tuple[float, float, float, float]], cfg: Optional[SegmentConfig] = None
) -> list[SegmentRecord]:
    """All segments whose bbox touches a box, including unmeasured roads.
    Full precision geometry preserves linear-reference piece boundaries."""
    if not boxes:
        return []
    cfg = cfg or load_config()
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (s.id) {_COLUMNS}, ST_AsGeoJSON(s.geom, 15) AS geojson
            FROM road_segments s
            JOIN unnest(
                   CAST(:west AS float8[]), CAST(:south AS float8[]),
                   CAST(:east AS float8[]), CAST(:north AS float8[])
                 ) AS b(west, south, east, north)
              ON s.geom && ST_MakeEnvelope(b.west, b.south, b.east, b.north, 4326)
            ORDER BY s.id
            LIMIT :cap
            """
        ),
        {
            "west": [b[0] for b in boxes], "south": [b[1] for b in boxes],
            "east": [b[2] for b in boxes], "north": [b[3] for b in boxes],
            "cap": MAX_SEGMENT_CANDIDATES + 1,
        },
    ).fetchall()
    if len(rows) > MAX_SEGMENT_CANDIDATES:
        raise TooManySegmentCandidates(
            f"too many road segments near the path (more than {MAX_SEGMENT_CANDIDATES}); "
            "use a shorter path"
        )
    return [_record(r, cfg) for r in rows]


def fetch_segments_near_path(
    db, path: Sequence[LatLon], cfg: Optional[SegmentConfig] = None
) -> list[SegmentRecord]:
    """Segments around a path (padded envelopes — a superset of the buffer)."""
    return fetch_segments_in_boxes(db, path_envelopes(path), cfg)


# --------------------------------------------------------------------------
# Route summary
# --------------------------------------------------------------------------

def summarize_route(
    path: Sequence[LatLon], records: Sequence[SegmentRecord], cfg: Optional[SegmentConfig] = None
) -> RouteQualityResult:
    """Route stats + the worst driven segments (pure given the records).

    ``worst_segments``: up to 5, worst first, skipping segments whose
    confidence level is "low" — a single noisy frame should not headline the
    route summary.
    """
    cfg = cfg or load_config()
    refs = [
        SegmentRef(id=r.id, coords=r.path, rqi=r.rqi, score=r.score, length_m=r.length_m,
                   speed_kmh=speed_kmh(r.maxspeed_kmh, r.highway))
        for r in records
    ]
    stats: RouteStats = compute_route_stats(path, refs, cfg.scale)
    eligible = {r.id for r in records if r.confidence_level != LEVEL_LOW}
    by_id = {r.id: r for r in records}
    return RouteQualityResult(
        total_length_m=stats.total_length_m,
        covered_length_m=stats.covered_length_m,
        length_by_rqi=stats.length_by_rqi,
        mean_score=stats.mean_score,
        mean_rqi=None if stats.mean_score is None else cfg.classify(stats.mean_score),
        impact_score=stats.impact_score,
        worst_segments=[by_id[cast(str, i)] for i in worst_segment_ids(stats, refs, cfg.scale, eligible)],
    )


def route_quality(db, path: Sequence[Sequence[float]]) -> RouteQualityResult:
    """Validate the path, load the nearby segments and summarize."""
    cfg = load_config()
    points = normalize_path(path)
    return summarize_route(points, fetch_segments_near_path(db, points, cfg), cfg)


# --------------------------------------------------------------------------
# Frame ↔ segment
# --------------------------------------------------------------------------

def _box_around(points: Sequence[LatLon]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    pad = _ENVELOPE_PAD_DEG
    return (min(lngs) - pad, min(lats) - pad, max(lngs) + pad, max(lats) + pad)


def segment_id_for_point(db, lat: float, lng: float, heading: Optional[float]) -> Optional[str]:
    """The segment a frame at this position/heading belongs to, or None."""
    segments = fetch_segments_in_boxes(db, [_box_around([(lat, lng)])])
    if not segments:
        return None
    match = _FrameSegmentIndex(segments).snap((lat, lng), heading)
    if match is None:
        return None
    matched = next(s for s in segments if s.id == match.line_id)
    return matched.id if _is_measured(matched) else None


def frame_ids_on_segment(db, segment_id: str) -> list[int]:
    """Ids of the frames that belong to a segment, ordered along it. Only
    frames the builder would use (scored, not marked unusable)."""
    from app.services.road_segments import load_frames

    cfg = load_config()
    row = db.execute(
        text(
            """
            SELECT ST_XMin(geom) AS west, ST_YMin(geom) AS south,
                   ST_XMax(geom) AS east, ST_YMax(geom) AS north
            FROM road_segments WHERE id = :id
              AND n_images > 0 AND score IS NOT NULL AND rqi IS NOT NULL
            """
        ),
        {"id": segment_id},
    ).first()
    if row is None:
        return []
    pad = _ENVELOPE_PAD_DEG
    # Frames within reach of the segment…
    frames = load_frames(
        db, cfg, (row.south - pad, row.west - pad, row.north + pad, row.east + pad)
    ).frames
    if not frames:
        return []
    # …and every segment any of those frames could prefer instead.
    box = (row.west - 2 * pad, row.south - 2 * pad, row.east + 2 * pad, row.north + 2 * pad)
    return match_frames_to_segment(segment_id, fetch_segments_in_boxes(db, [box], cfg), frames)
