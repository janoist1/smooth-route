"""routeAlternatives: Google's alternative routes, each with its road quality.

ONE Directions request per plan (alternatives=true, same billing as getRoute);
the quality of every route comes from the stored road segments (no Google
call). Same permission as getRoute: signed-in users (anonymous only on the
public read-only deploy). Ranking: app/services/route_alternatives.py.
"""
from __future__ import annotations

from typing import List, Optional

import strawberry

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
    is_smoothest: bool


@strawberry.type
class RouteAlternatives:
    routes: List[RouteOption]
    fastest_index: Optional[int]
    smoothest_index: Optional[int]  # null: no route is fast enough AND covered enough
    max_extra_duration: float
    min_coverage: float


@strawberry.type
class RouteAlternativesQuery:
    @strawberry.field(permission_classes=[IsAuthenticatedUnlessPublicRead])
    def route_alternatives(self, origin: str, destination: str) -> RouteAlternatives:
        """Up to 3 driving routes from one Google Directions call, each with
        its RouteQuality; marks the fastest and the smoothest (best
        length-weighted quality within +ROUTE_SMOOTH_MAX_EXTRA_DURATION of the
        fastest, with at least ROUTE_SMOOTH_MIN_COVERAGE of it measured)."""
        from app.core.config import settings
        from app.core.rqi_scale import SCALE
        from app.graphql.limits import validate_route_endpoints
        from app.services.google_maps import google_maps_service
        from app.services.route_alternatives import RouteCandidate, rank_routes
        from app.services.segment_read import route_quality as compute

        validate_route_endpoints(origin, destination)
        routes = google_maps_service.get_routes(origin, destination)
        qualities = []
        db = get_db_session()
        try:
            for r in routes:
                path = [[p["lat"], p["lng"]] for p in r["points"]]
                qualities.append(route_quality_type(compute(db, path)))
        finally:
            db.close()
        cands = [RouteCandidate(duration_s=r["duration_s"], distance_m=r["distance_m"],
                                mean_score=q.mean_score, covered_m=q.covered_length_m,
                                total_m=q.total_length_m)
                 for r, q in zip(routes, qualities)]
        extra = settings.ROUTE_SMOOTH_MAX_EXTRA_DURATION
        min_cov = settings.ROUTE_SMOOTH_MIN_COVERAGE
        fastest, smoothest = rank_routes(cands, SCALE, extra, min_cov)
        return RouteAlternatives(
            routes=[RouteOption(
                index=i,
                points=[RouteStep(lat=p["lat"], lng=p["lng"]) for p in r["points"]],
                distance_m=round(r["distance_m"], 1), duration_s=round(r["duration_s"], 1),
                summary=r["summary"], quality=q, coverage=round(c.coverage, 3),
                is_fastest=i == fastest, is_smoothest=i == smoothest,
            ) for i, (r, q, c) in enumerate(zip(routes, qualities, cands))],
            fastest_index=fastest, smoothest_index=smoothest,
            max_extra_duration=extra, min_coverage=min_cov,
        )
