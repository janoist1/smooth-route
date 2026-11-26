"""Pure geometry helpers for the road-segment layer (no DB, no numpy).

Everything works on plain ``(lat, lon)`` tuples in WGS84 degrees and returns
metres / degrees. Distances between nearby points use a local equirectangular
projection, which is accurate to well under 0.1 % at the scales we care about
(snapping radius ~20 m, pieces ~150 m); polyline lengths use the haversine
formula.

Used by the offline builder AND by the ``routeQuality`` resolver on the
torch-free read-only deploy, hence the stdlib-only implementation.
"""
from __future__ import annotations

import math
from typing import Sequence

EARTH_RADIUS_M = 6_371_008.8
_M_PER_DEG = math.pi * EARTH_RADIUS_M / 180.0  # metres per degree of latitude

LatLon = tuple[float, float]


# --------------------------------------------------------------------------
# Distance / bearing
# --------------------------------------------------------------------------

def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance in metres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Initial compass bearing a→b in degrees, [0, 360): 0 = north, 90 = east."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360.0


def bearing_diff_mod180(a: float, b: float) -> float:
    """Angle between two UNDIRECTED lines given as bearings, in [0, 90].

    Both travel directions merge: 10° vs 190° → 0, 10° vs 100° → 90.
    """
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def bearings_compatible(a: float, b: float, max_diff_deg: float = 45.0) -> bool:
    """True when two bearings describe the same road axis (either direction)."""
    return bearing_diff_mod180(a, b) < max_diff_deg


# --------------------------------------------------------------------------
# Local projection + point-to-edge
# --------------------------------------------------------------------------

def to_local_xy(origin: LatLon, p: LatLon) -> tuple[float, float]:
    """Metres east/north of ``origin`` (equirectangular, valid near origin)."""
    x = (p[1] - origin[1]) * _M_PER_DEG * math.cos(math.radians(origin[0]))
    y = (p[0] - origin[0]) * _M_PER_DEG
    return x, y


def project_on_edge(p: LatLon, a: LatLon, b: LatLon) -> tuple[float, float]:
    """Project point ``p`` on edge a→b.

    Returns ``(t, distance_m)``: ``t`` in [0, 1] is the clamped position of the
    foot point along the edge, ``distance_m`` the distance from ``p`` to it.
    """
    ax, ay = to_local_xy(p, a)
    bx, by = to_local_xy(p, b)
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 0.0:
        return 0.0, math.hypot(ax, ay)
    # p is the origin of the local frame, so the vector a→p is (-ax, -ay).
    t = max(0.0, min(1.0, (-ax * dx - ay * dy) / denom))
    return t, math.hypot(ax + t * dx, ay + t * dy)


def end_overshoot_m(p: LatLon, a: LatLon, b: LatLon) -> float:
    """How far ``p`` lies beyond the ends of edge a→b, measured ALONG its axis.

    0 when the foot of the perpendicular falls on the edge; positive when the
    point is "before a" or "past b". Lets a caller tell "beside the line" from
    "off its end" (a plain distance test treats both alike).
    """
    ax, ay = to_local_xy(p, a)
    bx, by = to_local_xy(p, b)
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length <= 0.0:
        return math.hypot(ax, ay)
    along = (-ax * dx - ay * dy) / length      # metres from a towards b
    return max(0.0, -along, along - length)


# --------------------------------------------------------------------------
# Polylines: lengths, splitting, linear referencing
# --------------------------------------------------------------------------

def cumulative_lengths(coords: Sequence[LatLon]) -> list[float]:
    """Running length in metres at every vertex; ``[0.0, ..., total]``."""
    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_m(a, b))
    return cum


def polyline_length_m(coords: Sequence[LatLon]) -> float:
    return cumulative_lengths(coords)[-1] if len(coords) > 1 else 0.0


def split_count(length_m: float, target_m: float) -> int:
    """How many equal pieces a way of ``length_m`` is cut into.

    ``round(length / target)``, at least 1 — every piece of a way that is at
    least one target long then lies within [0.75, 1.5) × target, so there is
    never a tiny tail piece. A way shorter than the target stays one piece.
    """
    if target_m <= 0:
        raise ValueError("target_m must be > 0")
    if length_m <= 0:
        return 1
    return max(1, int(math.floor(length_m / target_m + 0.5)))


def piece_index_for_offset(offset_m: float, length_m: float, n_pieces: int) -> int:
    """Which of ``n_pieces`` equal pieces contains a linear-reference offset."""
    if n_pieces <= 1 or length_m <= 0:
        return 0
    idx = int(offset_m / (length_m / n_pieces))
    return max(0, min(n_pieces - 1, idx))


def point_at_offset(coords: Sequence[LatLon], cum: Sequence[float], offset_m: float) -> LatLon:
    """Point at a distance along the polyline (clamped to its ends)."""
    if offset_m <= 0:
        return coords[0]
    if offset_m >= cum[-1]:
        return coords[-1]
    # Linear scan is fine: ways have few vertices and callers walk in order.
    for i in range(len(coords) - 1):
        if offset_m <= cum[i + 1]:
            seg = cum[i + 1] - cum[i]
            t = 0.0 if seg <= 0 else (offset_m - cum[i]) / seg
            a, b = coords[i], coords[i + 1]
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return coords[-1]


def line_substring(
    coords: Sequence[LatLon], cum: Sequence[float], start_m: float, end_m: float
) -> list[LatLon]:
    """The part of a polyline between two offsets, keeping interior vertices."""
    start_m = max(0.0, min(cum[-1], start_m))
    end_m = max(start_m, min(cum[-1], end_m))
    eps = 1e-6
    out = [point_at_offset(coords, cum, start_m)]
    for i in range(1, len(coords) - 1):
        if start_m + eps < cum[i] < end_m - eps:
            out.append(coords[i])
    out.append(point_at_offset(coords, cum, end_m))
    return out


def split_polyline(coords: Sequence[LatLon], target_m: float) -> list[list[LatLon]]:
    """Cut a polyline into ``split_count`` equal-length pieces (in order)."""
    cum = cumulative_lengths(coords)
    total = cum[-1]
    n = split_count(total, target_m)
    if n == 1:
        return [list(coords)]
    step = total / n
    return [line_substring(coords, cum, i * step, (i + 1) * step) for i in range(n)]


def densify(coords: Sequence[LatLon], step_m: float) -> list[tuple[LatLon, float, float]]:
    """Sample a path every ≤ ``step_m`` metres.

    Returns ``(midpoint, bearing_deg, length_m)`` per sample; the sample
    lengths add up exactly to the path length, so they can be summed as
    "metres of route" per matched segment.
    """
    if step_m <= 0:
        raise ValueError("step_m must be > 0")
    samples: list[tuple[LatLon, float, float]] = []
    for a, b in zip(coords, coords[1:]):
        length = haversine_m(a, b)
        if length <= 0:
            continue
        brg = bearing_deg(a, b)
        n = max(1, math.ceil(length / step_m))
        part = length / n
        for k in range(n):
            t = (k + 0.5) / n
            mid = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            samples.append((mid, brg, part))
    return samples
