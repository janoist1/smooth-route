"""Where to take new Street View frames: sample points along roads (pure).

Used by ``scripts/collect_network.py`` (collect by road network, no route
needed) and by the route collector's second pass. Three questions, all
answered without touching Google or the database:

1. WHERE along a road — one candidate every ``spacing_m`` (first pass 50 m),
   placed at the middle of each step, with the road's bearing there as the
   camera heading.
2. WHICH stretches are still empty — existing frames are snapped to the
   roads with the segment engine's own rule (``map_matching``); a candidate
   with a frame of the same road within ``min_gap_m`` along it is dropped.
3. IN WHAT ORDER — candidates are grouped into ~1 km cells and the cells are
   visited one at a time, round-robin across ~5 km "districts", so a limited
   image budget is spread over many places instead of being spent in one.

Second pass ("densify"): the same sampling at ``dense_spacing_m`` (30 m), but
only along segments whose confidence is low.

The spacing numbers come from the ``sampling`` block of
``backend/config/segment_aggregation.json`` (mirrors ``ml/segment_recipe.json``).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Hashable, Iterable, Mapping, Optional, Sequence

from app.services.map_matching import DEFAULT_MAX_DISTANCE_M, Line, LineIndex
from app.services.segment_aggregation import CONFIG_PATH
from app.services.segment_geometry import (
    LatLon,
    bearing_deg,
    cumulative_lengths,
    point_at_offset,
)

CELL_M = 1000.0            # one collection unit
DISTRICT_CELLS = 5         # a "district" is a 5 × 5 block of cells
_M_PER_DEG_LAT = 111_320.0

DENSIFY_LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class SamplingConfig:
    base_spacing_m: float = 50.0
    dense_spacing_m: float = 30.0
    densify_if: tuple[str, ...] = (DENSIFY_LOW_CONFIDENCE,)


def sampling_from_dict(data: Any) -> SamplingConfig:
    """The ``sampling`` block of the segment config; defaults when absent."""
    if data is None:
        return SamplingConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'sampling' must be an object")
    cfg = SamplingConfig(
        base_spacing_m=float(data.get("base_spacing_m", SamplingConfig.base_spacing_m)),
        dense_spacing_m=float(data.get("dense_spacing_m", SamplingConfig.dense_spacing_m)),
        densify_if=tuple(str(x) for x in data.get("densify_if", SamplingConfig.densify_if)),
    )
    if cfg.base_spacing_m <= 0 or cfg.dense_spacing_m <= 0:
        raise ValueError("sampling spacings must be > 0")
    if cfg.dense_spacing_m > cfg.base_spacing_m:
        raise ValueError("sampling.dense_spacing_m must not exceed base_spacing_m")
    return cfg


def load_sampling(path: Optional[Path | str] = None) -> SamplingConfig:
    p = Path(path) if path else CONFIG_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"segment aggregation config not found: {p}") from exc
    return sampling_from_dict(data.get("sampling"))


@dataclass(frozen=True)
class Candidate:
    """One place where a frame would be taken."""

    line_id: Hashable
    offset_m: float      # metres from the line's first vertex
    lat: float
    lon: float
    heading: float       # road bearing at that point

    @property
    def key(self) -> str:
        """Stable id for resume files: line + offset in decimetres."""
        return f"{self.line_id}:{round(self.offset_m * 10)}"


# --------------------------------------------------------------------------
# 1. Where along a road
# --------------------------------------------------------------------------

def bearing_at_offset(coords: Sequence[LatLon], cum: Sequence[float], offset_m: float) -> float:
    """Bearing of the edge that contains ``offset_m``."""
    i = bisect.bisect_right(cum, offset_m) - 1
    i = max(0, min(len(coords) - 2, i))
    return bearing_deg(coords[i], coords[i + 1])


def sample_line(line: Line, spacing_m: float) -> list[Candidate]:
    """Candidates every ``spacing_m`` along a line: a line of length L gets
    ``round(L / spacing)`` evenly spread points (at least one once it is half
    a step long), each in the middle of its stretch."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be > 0")
    coords = line.coords
    if len(coords) < 2:
        return []
    cum = cumulative_lengths(coords)
    total = cum[-1]
    n = int(math.floor(total / spacing_m + 0.5))
    if n < 1:
        return []
    step = total / n
    out = []
    for k in range(n):
        offset = (k + 0.5) * step
        lat, lon = point_at_offset(coords, cum, offset)
        out.append(Candidate(line.id, offset, lat, lon, bearing_at_offset(coords, cum, offset)))
    return out


def sample_route(route: Sequence[LatLon], spacing_m: float) -> list[LatLon]:
    """Points every ``spacing_m`` along a route polyline. Their number is the
    route's first-pass image ceiling: one image per point at most."""
    from types import SimpleNamespace

    return [(c.lat, c.lon)
            for c in sample_line(SimpleNamespace(id="route", coords=list(route)), spacing_m)]


# --------------------------------------------------------------------------
# 2. Which stretches are still empty
# --------------------------------------------------------------------------

def covered_offsets(
    index: LineIndex, frames: Iterable, max_distance_m: float = DEFAULT_MAX_DISTANCE_M
) -> dict[Hashable, list[float]]:
    """Per line, the sorted offsets of the existing frames (objects with
    lat / lon / heading) that belong to it by the segment engine's rule."""
    covered: dict[Hashable, list[float]] = defaultdict(list)
    for frame in frames:
        match = index.snap((frame.lat, frame.lon), frame.heading, max_distance_m=max_distance_m)
        if match is not None:
            covered[match.line_id].append(match.offset_m)
    return {line_id: sorted(offsets) for line_id, offsets in covered.items()}


def is_covered(offsets: Sequence[float], offset_m: float, min_gap_m: float) -> bool:
    """Is there an existing frame within ``min_gap_m`` along the line?"""
    i = bisect.bisect_left(offsets, offset_m - min_gap_m)
    return i < len(offsets) and offsets[i] <= offset_m + min_gap_m


def uncovered(
    candidates: Iterable[Candidate], covered: Mapping[Hashable, Sequence[float]], min_gap_m: float
) -> list[Candidate]:
    return [
        c for c in candidates
        if not is_covered(covered.get(c.line_id, ()), c.offset_m, min_gap_m)
    ]


# --------------------------------------------------------------------------
# 3. In what order
# --------------------------------------------------------------------------

Cell = tuple[int, int]


def cell_of(lat: float, lon: float, cell_m: float = CELL_M, ref_lat: float = 47.5) -> Cell:
    """~``cell_m`` grid cell of a point. The east-west size is fixed at
    ``ref_lat`` so cell ids do not depend on the point's own latitude."""
    dlat = cell_m / _M_PER_DEG_LAT
    dlon = cell_m / (_M_PER_DEG_LAT * math.cos(math.radians(ref_lat)))
    return (math.floor(lat / dlat), math.floor(lon / dlon))


def district_of(cell: Cell, block: int = DISTRICT_CELLS) -> Cell:
    return (cell[0] // block, cell[1] // block)


def _stable_rank(value: Any, seed: str) -> str:
    return hashlib.sha1(f"{seed}|{value}".encode()).hexdigest()


def order_cells(cells: Iterable[Cell], seed: str = "smooth-route") -> list[Cell]:
    """Visit order: round-robin over districts, one cell per district per
    round, districts and cells each in a fixed pseudo-random order — the same
    input always gives the same order (so a stopped job resumes identically).
    """
    by_district: dict[Cell, list[Cell]] = defaultdict(list)
    for cell in set(cells):
        by_district[district_of(cell)].append(cell)
    districts = sorted(by_district, key=lambda d: _stable_rank(d, seed))
    for district in districts:
        by_district[district].sort(key=lambda c: _stable_rank(c, seed))
    ordered: list[Cell] = []
    round_no = 0
    while len(ordered) < sum(len(v) for v in by_district.values()):
        for district in districts:
            if round_no < len(by_district[district]):
                ordered.append(by_district[district][round_no])
        round_no += 1
    return ordered


def group_by_cell(candidates: Iterable[Candidate]) -> dict[Cell, list[Candidate]]:
    """Candidates per cell, each cell's list ordered along its roads."""
    groups: dict[Cell, list[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[cell_of(c.lat, c.lon)].append(c)
    for members in groups.values():
        members.sort(key=lambda c: (str(c.line_id), c.offset_m))
    return groups


def plan_collection(
    lines: Mapping[Hashable, Line],
    existing_frames: Iterable,
    spacing_m: float,
    *,
    bounds: Optional[tuple[float, float, float, float]] = None,
    min_gap_m: Optional[float] = None,
    seed: str = "smooth-route",
) -> list[tuple[Cell, list[Candidate]]]:
    """The whole first-pass plan: ``[(cell, [candidates…]), …]`` in visit
    order. ``bounds`` = (south, west, north, east) keeps only candidates
    inside the target area (roads are returned whole by Overpass and may
    stick out). ``min_gap_m`` defaults to half the spacing.
    """
    gap = spacing_m / 2.0 if min_gap_m is None else min_gap_m
    index = LineIndex(lines.values())
    covered = covered_offsets(index, existing_frames)
    candidates: list[Candidate] = []
    for line_id in sorted(lines, key=str):
        candidates.extend(sample_line(lines[line_id], spacing_m))
    if bounds is not None:
        south, west, north, east = bounds
        candidates = [c for c in candidates if south <= c.lat <= north and west <= c.lon <= east]
    groups = group_by_cell(uncovered(candidates, covered, gap))
    return [(cell, groups[cell]) for cell in order_cells(groups, seed)]


def take_budget(
    plan: Sequence[tuple[Cell, list[Candidate]]], max_candidates: int
) -> list[tuple[Cell, list[Candidate]]]:
    """The leading cells of a plan that fit in ``max_candidates`` — whole
    cells only, so every visited place gets complete stretches."""
    out, used = [], 0
    for cell, members in plan:
        if used + len(members) > max_candidates:
            break
        out.append((cell, members))
        used += len(members)
    return out
