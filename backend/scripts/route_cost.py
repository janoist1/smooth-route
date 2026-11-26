"""How many Street View images would a route job cost? (dry run)

Usage (from backend/):
    ../.venv/bin/python scripts/route_cost.py "ORIGIN" "DESTINATION" [--spacing M]

Asks Google Directions for the route (ONE Directions request — no Street View
request, no image) and prints:

- the route length and the number of first-pass sample points at
  ``sampling.base_spacing_m`` (50 m) — the ceiling of the first pass: one
  image per point at most, fewer where a point has no panorama, shares one
  with its neighbour, or already has a frame;
- how many of those points already have a stored frame within 10 m;
- the ceiling of the second pass if EVERY segment came out low-confidence
  (``dense_spacing_m``, 30 m — normally only a fraction is revisited);
- the month's quota counter and the per-job cap the job would run under.

Nothing is written anywhere.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def estimate(route: list[tuple[float, float]], base_spacing_m: float, dense_spacing_m: float
             ) -> dict:
    """Pure cost model of a route job (image ceilings, not forecasts)."""
    from app.services.network_sampling import sample_route
    from app.services.segment_geometry import polyline_length_m

    first = len(sample_route(route, base_spacing_m))
    dense = len(sample_route(route, dense_spacing_m))
    return {
        "length_m": polyline_length_m(route),
        "first_pass_max": first,
        # A dense point within half a dense step of a first-pass frame is not
        # taken again, so the second pass adds at most the difference.
        "second_pass_max": max(0, dense - first),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("origin")
    ap.add_argument("destination")
    ap.add_argument("--spacing", type=float, default=None, help="override base_spacing_m")
    args = ap.parse_args()

    from app.services.google_maps import google_maps_service
    from app.services.network_sampling import load_sampling, sample_route
    from app.services.sv_quota import DEFAULT_JOB_CAP, cap_from_env, default_quota

    sampling = load_sampling()
    spacing = args.spacing or sampling.base_spacing_m
    route = [(p["lat"], p["lng"]) for p in google_maps_service.get_route(args.origin, args.destination)]
    if len(route) < 2:
        sys.exit("No route found.")
    cost = estimate(route, spacing, sampling.dense_spacing_m)

    already = "n/a (no database)"
    try:
        from app.core.database import SessionLocal
        from app.services.frame_store import DbFrameStore

        db = SessionLocal()
        try:
            store = DbFrameStore(db, "unused")
            points = sample_route(route, spacing)
            already = sum(1 for lat, lon in points if store.near_existing(lat, lon, 10.0))
        finally:
            db.close()
    except Exception as exc:  # the estimate is still useful without the DB
        already = f"n/a ({type(exc).__name__})"

    quota = default_quota()
    job_cap = cap_from_env("GOOGLE_SV_JOB_CAP", DEFAULT_JOB_CAP)
    print(f"route: {cost['length_m'] / 1000:.1f} km")
    print(f"first pass ({spacing:g} m): at most {cost['first_pass_max']} images "
          f"(points that already have a frame within 10 m: {already})")
    print(f"second pass ({sampling.dense_spacing_m:g} m, low-confidence segments only): "
          f"at most {cost['second_pass_max']} more")
    print(f"{quota.summary()}; per-job cap {job_cap}")
    worst = cost["first_pass_max"] + cost["second_pass_max"]
    if worst > min(job_cap, quota.remaining()):
        print(f"NOTE: the ceiling ({worst}) is above what this job may fetch "
              f"({min(job_cap, quota.remaining())}); the job would stop at the cap and "
              f"leave the rest queued.")


if __name__ == "__main__":
    main()
