"""Route alternatives: ranking (pure), the single Directions call, the resolver.
No DB, no network: Google and the segment engine are faked."""
from types import SimpleNamespace

import pytest

from app.core.auth import Identity
from app.core.rqi_scale import SCALE
from app.services.route_alternatives import RouteCandidate, rank_routes

USER = Identity(user_id="u1", clerk_id="user_1", email=None, role="user")
BEST, WORST = SCALE.best, SCALE.worst
MID = (BEST + WORST) / 2


def toward_best(x, by):
    """A score `by` levels better than x, in whatever direction the scale runs."""
    return x - by if SCALE.lower_is_better else x + by


def cand(duration, score, coverage=1.0, total=1000.0):
    return RouteCandidate(duration_s=duration, distance_m=total, mean_score=score,
                          covered_m=total * coverage, total_m=total)


class TestRank:
    def test_smoothest_is_best_quality_within_the_duration_budget(self):
        routes = [cand(600, MID), cand(700, toward_best(MID, 1)), cand(900, BEST)]
        # 900 s is > +20 % of 600 s: not eligible although it is the best road.
        assert rank_routes(routes, SCALE) == (0, 1)

    def test_low_coverage_route_is_never_called_smooth(self):
        routes = [cand(600, MID), cand(610, BEST, coverage=0.3)]
        assert rank_routes(routes, SCALE) == (0, 0)
        assert rank_routes(routes, SCALE, min_coverage=0.2) == (0, 1)

    def test_no_route_qualifies(self):
        routes = [cand(600, None), cand(650, BEST, coverage=0.1)]
        assert rank_routes(routes, SCALE) == (0, None)
        assert rank_routes([], SCALE) == (None, None)

    def test_tie_goes_to_the_faster_route(self):
        assert rank_routes([cand(650, MID), cand(600, MID)], SCALE) == (1, 1)

    def test_direction_flip_changes_nothing_but_the_scale(self):
        flipped = SCALE.mirrored()
        mirror = lambda x: BEST + WORST - x  # noqa: E731
        routes = [cand(600, MID), cand(700, toward_best(MID, 1))]
        mirrored = [cand(r.duration_s, mirror(r.mean_score)) for r in routes]
        assert rank_routes(routes, SCALE) == rank_routes(mirrored, flipped) == (0, 1)


def _google_route(seconds, metres, summary):
    return {"overview_polyline": {"points": "_p~iF~ps|U_ulLnnqC"},  # 2-point polyline
            "legs": [{"distance": {"value": metres}, "duration": {"value": seconds}}],
            "summary": summary}


def test_get_routes_is_one_directions_call_with_alternatives():
    from app.services.google_maps import GoogleMapsService

    calls = []

    def directions(origin, destination, mode, alternatives):
        calls.append(alternatives)
        return [_google_route(600, 5000, "A"), _google_route(700, 5200, "B"),
                _google_route(800, 5400, "C"), _google_route(900, 6000, "D")]

    svc = GoogleMapsService.__new__(GoogleMapsService)
    svc.client = SimpleNamespace(directions=directions)
    routes = svc.get_routes("a", "b")
    assert calls == [True]
    assert [r["summary"] for r in routes] == ["A", "B", "C"]
    assert routes[0]["duration_s"] == 600 and routes[0]["distance_m"] == 5000
    assert len(routes[0]["points"]) == 2 and set(routes[0]["points"][0]) == {"lat", "lng"}


class TestResolver:
    QUERY = ('{ routeAlternatives(origin: "47.5,19.05", destination: "47.48,19.08") '
             "{ fastestIndex smoothestIndex routes { index isFastest isSmoothest coverage "
             "durationS summary quality { meanScore coveredLengthM } points { lat } } } }")

    def test_marks_fastest_and_smoothest_from_one_google_call(self, monkeypatch):
        import app.graphql.route_alternatives as mod
        from app.services import google_maps, segment_read

        calls = []

        def fake_routes(origin, destination):
            calls.append((origin, destination))
            pts = [{"lat": 47.5, "lng": 19.05}, {"lat": 47.49, "lng": 19.06}]
            return [{"points": pts, "distance_m": 5000.0, "duration_s": 600.0, "summary": "fast"},
                    {"points": pts + [{"lat": 47.48, "lng": 19.08}], "distance_m": 5300.0,
                     "duration_s": 660.0, "summary": "smooth"}]

        def fake_quality(db, path):
            better = len(path) == 3
            score = toward_best(MID, 1) if better else MID
            return SimpleNamespace(total_length_m=1000.0, length_by_rqi=[900.0, 0, 0, 0],
                                   mean_score=score, worst_segments=[])

        monkeypatch.setattr(google_maps.google_maps_service, "get_routes", fake_routes)
        monkeypatch.setattr(segment_read, "route_quality", fake_quality)
        monkeypatch.setattr(mod, "get_db_session", lambda: SimpleNamespace(close=lambda: None))
        from app.graphql.schema import schema

        res = schema.execute_sync(self.QUERY, context_value={"identity": USER})
        assert res.errors is None, res.errors
        data = res.data["routeAlternatives"]
        assert calls == [("47.5,19.05", "47.48,19.08")]
        assert data["fastestIndex"] == 0 and data["smoothestIndex"] == 1
        assert [r["isSmoothest"] for r in data["routes"]] == [False, True]
        assert data["routes"][1]["coverage"] == pytest.approx(0.9)

    def test_anonymous_is_denied_on_the_full_schema(self):
        from app.graphql.schema import schema

        res = schema.execute_sync(self.QUERY, context_value={"identity": None})
        assert res.data is None and "Authentication required" in res.errors[0].message


def test_public_schema_allows_one_paid_alternatives_call_per_request():
    from app.graphql.schema import read_schema

    q = ('{ a: routeAlternatives(origin: "Budapest", destination: "Győr") { fastestIndex }'
         ' b: routeAlternatives(origin: "Budapest", destination: "Pécs") { fastestIndex } }')
    res = read_schema.execute_sync(q, context_value={"identity": None})
    assert res.data is None
    assert "At most 1 routeAlternatives per request" in res.errors[0].message
