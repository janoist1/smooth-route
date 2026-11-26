"""Quality summary of a planned route from the stored road segments (pure).

The route polyline is sampled every ~10 m; each sample is snapped to the
nearest road segment within ``buffer_m`` whose direction fits the route's
local bearing (|Δ| < 45° modulo 180 — see ``map_matching``). Every sample
stands for a known number of metres, so the summary is plain bookkeeping:

- ``total_length_m``    the whole path
- ``covered_length_m``  metres whose sample matched a segment WITH data
- ``length_by_rqi``     those metres split by the segment's class (1–4)
- ``mean_score``        length-weighted mean of the segments' scores
- ``matched_m``         metres matched per segment id (for the worst-list)

No DB access here: the resolver loads the candidate segments and passes them
in, which keeps this unit-testable and torch/numpy-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Optional, Sequence

from app.services.map_matching import LineIndex
from app.services.segment_geometry import LatLon, densify

ROUTE_BUFFER_M = 15.0
ROUTE_MAX_BEARING_DIFF_DEG = 45.0
ROUTE_SAMPLE_STEP_M = 10.0
# The buffer is cut (almost) flat at a segment's ends: a sample further than
# this beyond the last vertex is not "on" the segment. Without it every data
# gap would be credited ~15 m of coverage on each side. The few metres of
# slack keep the outside of a bend between two segments matched.
ROUTE_END_SLACK_M = 5.0
WORST_SEGMENTS_LIMIT = 5
# A segment only counts as "driven" for the worst-list when the route runs
# along a real stretch of it — not when it merely brushes it at a junction.
MIN_MATCHED_M = 25.0
MIN_MATCHED_FRACTION = 0.5


@dataclass(frozen=True)
class SegmentRef:
    """A stored segment as the route matcher sees it."""

    id: Hashable
    coords: Sequence[LatLon]
    rqi: Optional[int]
    score: Optional[float]
    length_m: float = 0.0


@dataclass
class RouteStats:
    total_length_m: float = 0.0
    covered_length_m: float = 0.0
    length_by_rqi: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    mean_score: Optional[float] = None
    matched_m: dict[Hashable, float] = field(default_factory=dict)


def compute_route_stats(
    path: Sequence[LatLon],
    segments: Sequence[SegmentRef],
    *,
    buffer_m: float = ROUTE_BUFFER_M,
    max_bearing_diff_deg: float = ROUTE_MAX_BEARING_DIFF_DEG,
    step_m: float = ROUTE_SAMPLE_STEP_M,
) -> RouteStats:
    """Match ``path`` (``[(lat, lon), ...]``) to ``segments`` and add it up.

    Segments without data (``rqi`` / ``score`` None) are ignored: a stretch
    covered only by them counts as uncovered.
    """
    stats = RouteStats()
    usable = [s for s in segments if s.rqi is not None and s.score is not None]
    by_id = {s.id: s for s in usable}
    index = LineIndex(usable)

    weighted_score = 0.0
    for point, bearing, length in densify(path, step_m):
        stats.total_length_m += length
        match = index.snap(
            point, bearing,
            max_distance_m=buffer_m, max_bearing_diff_deg=max_bearing_diff_deg,
            max_end_overshoot_m=ROUTE_END_SLACK_M,
        )
        if match is None:
            continue
        seg = by_id[match.line_id]
        stats.covered_length_m += length
        stats.length_by_rqi[min(4, max(1, int(seg.rqi))) - 1] += length
        weighted_score += seg.score * length
        stats.matched_m[seg.id] = stats.matched_m.get(seg.id, 0.0) + length

    if stats.covered_length_m > 0:
        stats.mean_score = weighted_score / stats.covered_length_m
    return stats


def worst_segment_ids(
    stats: RouteStats,
    segments: Sequence[SegmentRef],
    eligible: Optional[set] = None,
    limit: int = WORST_SEGMENTS_LIMIT,
) -> list[Hashable]:
    """Ids of the worst segments actually driven, worst (highest score) first.

    ``eligible`` restricts the list (the resolver passes the ids whose
    confidence is not "low"). A segment qualifies when the route covers at
    least ``MIN_MATCHED_M`` of it, or half of a segment shorter than that.
    """
    by_id = {s.id: s for s in segments}
    candidates = []
    for seg_id, metres in stats.matched_m.items():
        seg = by_id.get(seg_id)
        if seg is None or seg.score is None:
            continue
        if eligible is not None and seg_id not in eligible:
            continue
        needed = MIN_MATCHED_M
        if seg.length_m > 0:
            needed = min(MIN_MATCHED_M, MIN_MATCHED_FRACTION * seg.length_m)
        if metres + 1e-9 < needed:
            continue
        candidates.append((-seg.score, -metres, str(seg_id), seg_id))
    candidates.sort()
    return [c[3] for c in candidates[:limit]]
