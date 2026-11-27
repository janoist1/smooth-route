"""routeAlternatives: Google's alternative routes, each with its road quality.

ONE Directions request per plan (alternatives=true, same billing as getRoute);
the quality of every route comes from the stored road segments (no Google
call). Same permission as getRoute: signed-in users (anonymous only on the
public read-only deploy). Ranking: app/services/route_alternatives.py.
"""
from __future__ import annotations

from typing import List, Optional

import strawberry
from starlette.concurrency import run_in_threadpool

from app.graphql.permissions import IsAuthenticatedUnlessPublicRead
from app.graphql.queries import RouteStep, route_quality_type
from app.graphql.resolver_helpers import get_db_session
from app.graphql.types import RouteQuality


@strawberry.type
class RouteOption:
    index: int  # Google's order (0 = its recommended route)
    points: List[RouteStep]
    distance_m: float
    duration_s: float
    summary: str
    quality: RouteQuality
    coverage: float  # covered share of the route, 0..1
    is_fastest: bool
    is_smoothest: bool = strawberry.field(
        description="Lowest impact among routes within the duration budget and coverage floor; may be uncertain.")
    smoothest_confident: bool = strawberry.field(
        description="True only for the smoothest route when coverage meets ROUTE_SMOOTH_MIN_COVERAGE.")


@strawberry.type
class RouteAlternatives:
    routes: List[RouteOption]
    fastest_index: Optional[int]
    smoothest_index: Optional[int]  # null: no route meets the duration budget and coverage floor
    max_extra_duration: float
    min_coverage: float  # eligibility floor, separate from the confidence threshold


def measurable(route: dict) -> bool:
    """Whether the route's quality may be computed on this request.

    Google decides the route, so a text destination outside the country can
    return a 2 000 km drive x 3 alternatives. Quality is measured only within
    the public routeQuality caps (limits.MAX_PATH_KM / MAX_PATH_POINTS); a
    longer route is returned with no quality data instead of failing the
    request after the paid Directions call.
    """
    from app.graphql.limits import MAX_PATH_KM, MAX_PATH_POINTS

    return (route["distance_m"] <= MAX_PATH_KM * 1000
            and len(route["points"]) <= MAX_PATH_POINTS)


def unmeasured_quality(route: dict):
    """A RouteQualityResult with nothing covered (no DB, no matching)."""
    from app.services.segment_read import RouteQualityResult, load_config

    return RouteQualityResult(
        total_length_m=route["distance_m"], covered_length_m=0.0,
        length_by_rqi=[0.0] * len(load_config().scale.best_to_worst), mean_score=None,
        worst_segments=[])


@strawberry.type
class RouteAlternativesQuery:
    @strawberry.field(permission_classes=[IsAuthenticatedUnlessPublicRead])
    async def route_alternatives(self, origin: str, destination: str) -> RouteAlternatives:
        return await run_in_threadpool(_route_alternatives, origin, destination)


def _route_alternatives(origin: str, destination: str) -> RouteAlternatives:
    """Up to 3 driving routes from one routing call (OSRM or Google), each with
    its RouteQuality; marks the fastest and the smoothest (lowest
    speed-weighted impact, RouteQuality.impactScore, within +ROUTE_SMOOTH_MAX_EXTRA_DURATION of the
    fastest, with at least SMOOTHEST_COVERAGE_FLOOR of it measured).
    Confidence additionally requires ROUTE_SMOOTH_MIN_COVERAGE."""
    from app.core.config import settings
    from app.core.rqi_scale import SCALE
    from app.graphql.limits import validate_route_endpoints
    from app.services.routing import routing_service
    from app.services.route_alternatives import SMOOTHEST_COVERAGE_FLOOR, RouteCandidate, rank_routes
    from app.services.segment_read import route_quality as compute

    validate_route_endpoints(origin, destination)
    routes = routing_service.get_routes(origin, destination)
    qualities = []
    db = get_db_session()
    try:
        for r in routes:
            if not measurable(r):
                qualities.append(route_quality_type(unmeasured_quality(r)))
                continue
            path = [[p["lat"], p["lng"]] for p in r["points"]]
            qualities.append(route_quality_type(compute(db, path)))
    finally:
        db.close()
    cands = [RouteCandidate(duration_s=r["duration_s"], distance_m=r["distance_m"],
                            mean_score=q.mean_score, covered_m=q.covered_length_m,
                            total_m=q.total_length_m, impact_score=q.impact_score)
             for r, q in zip(routes, qualities)]
    extra = settings.ROUTE_SMOOTH_MAX_EXTRA_DURATION
    confident_coverage = settings.ROUTE_SMOOTH_MIN_COVERAGE
    fastest, smoothest = rank_routes(cands, SCALE, extra)
    return RouteAlternatives(
        routes=[RouteOption(
            index=i,
            points=[RouteStep(lat=p["lat"], lng=p["lng"]) for p in r["points"]],
            distance_m=round(r["distance_m"], 1), duration_s=round(r["duration_s"], 1),
            summary=r["summary"], quality=q, coverage=round(c.coverage, 3),
            is_fastest=i == fastest, is_smoothest=i == smoothest,
            smoothest_confident=i == smoothest and c.coverage >= confident_coverage,
        ) for i, (r, q, c) in enumerate(zip(routes, qualities, cands))],
        fastest_index=fastest, smoothest_index=smoothest,
        max_extra_duration=extra, min_coverage=SMOOTHEST_COVERAGE_FLOOR,
    )
