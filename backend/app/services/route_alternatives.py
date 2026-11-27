"""Which of Google's alternative routes is the fastest and which the smoothest.

Pure (no DB, Google or GraphQL) and direction-agnostic: quality scores are
compared with the canonical scale (app.core.rqi_scale), so the 5 = Kiváló
flip needs no change here.

Smoothest = the lowest speed-weighted impact (route_scoring: a defect at
90 km/h counts 1.8x, at 30 km/h 0.6x; falls back to the plain length-weighted
mean quality when a route has no impact score) among routes that are
  (a) at most ``max_extra_duration`` slower than the fastest (default +20 %),
  (b) covered by quality data on at least ``min_coverage`` of their length
      (default 10 % floor).
This selects a relative winner even with sparse data; the API separately
reports whether its coverage is high enough for a confident badge. None
when no route qualifies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


SMOOTHEST_COVERAGE_FLOOR = 0.1


@dataclass(frozen=True)
class RouteCandidate:
    duration_s: float
    distance_m: float
    mean_score: Optional[float]   # canonical scale, None = no data
    covered_m: float
    total_m: float
    impact_score: Optional[float] = None  # lower is better

    @property
    def coverage(self) -> float:
        return self.covered_m / self.total_m if self.total_m > 0 else 0.0


def rank_routes(routes: Sequence[RouteCandidate], scale,
                max_extra_duration: float = 0.2,
                min_coverage: float = SMOOTHEST_COVERAGE_FLOOR) -> tuple[Optional[int], Optional[int]]:
    """(fastest index, smoothest index or None)."""
    if not routes:
        return None, None
    fastest = min(range(len(routes)), key=lambda i: (routes[i].duration_s, i))
    limit = routes[fastest].duration_s * (1.0 + max_extra_duration)
    smoothest: Optional[int] = None
    use_impact = all(r.impact_score is not None for r in routes if r.mean_score is not None)
    for i, r in enumerate(routes):
        if r.mean_score is None or r.coverage < min_coverage or r.duration_s > limit + 1e-9:
            continue
        if smoothest is None:
            smoothest = i
            continue
        best = routes[smoothest]
        if use_impact:
            # use_impact: every measured route has an impact score
            assert r.impact_score is not None and best.impact_score is not None
            better = r.impact_score < best.impact_score
            tie = r.impact_score == best.impact_score
        else:
            better = scale.better_than(r.mean_score, best.mean_score)
            tie = r.mean_score == best.mean_score
        if better or (tie and r.duration_s < best.duration_s):
            smoothest = i
    return fastest, smoothest
