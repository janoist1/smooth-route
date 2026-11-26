"""Snap points to polylines: nearest line within a radius whose local bearing
fits the point's heading (pure, stdlib only).

Used twice:

- the segment builder snaps Street View frames to OSM ways
  (radius ~20 m, |Δbearing| < 45° modulo 180), and
- ``routeQuality`` snaps samples of a planned route to stored road segments
  (radius ~15 m, same bearing rule).

The bearing rule works modulo 180° — a frame shot while driving north and one
shot driving south on the same carriageway describe the same asphalt, so both
directions merge. It is what keeps a frame from snapping to a crossing street
at a junction, or to a ramp passing overhead.

``LineIndex`` is a uniform lat/lon grid over the edges of the lines; a lookup
only inspects the handful of edges in the cells around the point.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Hashable, Iterable, Optional, Protocol, Sequence

from app.services.segment_geometry import (
    LatLon,
    bearing_deg,
    bearing_diff_mod180,
    cumulative_lengths,
    end_overshoot_m,
    project_on_edge,
)

DEFAULT_MAX_DISTANCE_M = 20.0
DEFAULT_MAX_BEARING_DIFF_DEG = 45.0
# Shared with the builder's minimum disambiguation neighbourhood (twice this).
ROUTE_BUFFER_M = 15.0

# Grid cell in degrees (~56 m N-S, ~38 m E-W at 47°N): larger than the snapping
# radius, so a lookup touches at most a 3×3 block of cells.
_CELL_DEG = 0.0005
_M_PER_DEG_LAT = 111_320.0


class Line(Protocol):
    """Anything with an id and ``(lat, lon)`` vertices (an OSM way, a segment)."""

    @property
    def id(self) -> Hashable: ...

    @property
    def coords(self) -> Sequence[LatLon]: ...


@dataclass(frozen=True)
class Match:
    line_id: Hashable
    offset_m: float       # linear reference: metres from the line's first vertex
    distance_m: float     # point → line
    bearing_diff: float   # 0–90°, heading vs. the matched edge


class LineIndex:
    """Grid index over the edges of a set of polylines."""

    def __init__(self, lines: Iterable[Line], cell_deg: float = _CELL_DEG):
        self._cell = cell_deg
        self._coords: list[Sequence[LatLon]] = []
        self._ids: list[Hashable] = []
        self._cum: list[list[float]] = []
        self._bearings: list[list[float]] = []
        # cell → [(line number, edge number), ...]
        self._grid: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for line in lines:
            coords = line.coords
            if len(coords) < 2:
                continue
            n = len(self._ids)
            self._ids.append(line.id)
            self._coords.append(coords)
            self._cum.append(cumulative_lengths(coords))
            self._bearings.append(
                [bearing_deg(a, b) for a, b in zip(coords, coords[1:])]
            )
            for e, (a, b) in enumerate(zip(coords, coords[1:])):
                y0, y1 = sorted((self._row(a[0]), self._row(b[0])))
                x0, x1 = sorted((self._col(a[1]), self._col(b[1])))
                for y in range(y0, y1 + 1):
                    for x in range(x0, x1 + 1):
                        self._grid[(y, x)].append((n, e))

    def __len__(self) -> int:
        return len(self._ids)

    def _row(self, lat: float) -> int:
        return math.floor(lat / self._cell)

    def _col(self, lon: float) -> int:
        return math.floor(lon / self._cell)

    def _candidates(self, p: LatLon, radius_m: float) -> set[tuple[int, int]]:
        # 1 % slack: the search box must never be tighter than the exact
        # distance test applied to the candidates afterwards.
        dlat = 1.01 * radius_m / _M_PER_DEG_LAT
        dlon = dlat / max(0.01, math.cos(math.radians(p[0])))
        found: set[tuple[int, int]] = set()
        for y in range(self._row(p[0] - dlat), self._row(p[0] + dlat) + 1):
            for x in range(self._col(p[1] - dlon), self._col(p[1] + dlon) + 1):
                cell = self._grid.get((y, x))
                if cell:
                    found.update(cell)
        return found

    def snap(
        self,
        p: LatLon,
        heading: Optional[float],
        *,
        max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
        max_bearing_diff_deg: float = DEFAULT_MAX_BEARING_DIFF_DEG,
        max_end_overshoot_m: Optional[float] = None,
    ) -> Optional[Match]:
        """Nearest bearing-compatible line within ``max_distance_m``, or None.

        ``heading=None`` disables the bearing test (nearest line wins). Ties in
        distance go to the smaller line id so the result is deterministic.

        ``max_end_overshoot_m`` (off by default) rejects a line when the point
        lies more than that many metres beyond its first/last vertex along the
        line's axis — i.e. the search area gets flat ends instead of round
        caps. Length bookkeeping (route coverage) wants that; snapping noisy
        frame positions does not.
        """
        best: Optional[tuple[float, str, int, int, float, float]] = None
        for n, e in self._candidates(p, max_distance_m):
            coords = self._coords[n]
            if heading is None:
                diff = 0.0
            else:
                diff = bearing_diff_mod180(heading, self._bearings[n][e])
                if diff >= max_bearing_diff_deg:
                    continue
            t, dist = project_on_edge(p, coords[e], coords[e + 1])
            if dist > max_distance_m:
                continue
            if max_end_overshoot_m is not None and (
                (t <= 0.0 and e == 0) or (t >= 1.0 and e == len(coords) - 2)
            ):
                if end_overshoot_m(p, coords[e], coords[e + 1]) > max_end_overshoot_m:
                    continue
            key = (round(dist, 6), str(self._ids[n]), n, e, t, diff)
            if best is None or key[:2] < best[:2]:
                best = key
        if best is None:
            return None
        dist, _, n, e, t, diff = best
        cum = self._cum[n]
        return Match(
            line_id=self._ids[n],
            offset_m=cum[e] + t * (cum[e + 1] - cum[e]),
            distance_m=dist,
            bearing_diff=diff,
        )
