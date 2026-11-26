"""Rebuild the road-segment layer (road_segments) from frames + OSM geometry.

Usage (from backend/):
    ../.venv/bin/python scripts/build_segments.py [--bbox W,S,E,N] [--dry-run]
        [--offline] [--cached-only] [--prefetch-bbox W,S,E,N] [--no-merge] [--config PATH]
        [--segment-length M] [--aggregator NAME]

- Full rebuild by default: consecutive OSM ways of the same road are stitched
  into lines, every scored Street View frame is snapped to the nearest
  bearing-compatible line (20 m, |Δ| < 45° mod 180), each line with frames is
  cut into ~segment_length_m pieces and aggregated per piece, and the table
  is replaced in one transaction. Idempotent — safe to re-run.
- ``--bbox minLng,minLat,maxLng,maxLat`` (same order as the GraphQL bbox)
  rewrites only the lines touching that box. It turns into a full rebuild by
  itself when the OSM tiles / config changed since the last full rebuild.
- ``--prefetch-bbox minLng,minLat,maxLng,maxLat`` only downloads the OSM
  tiles covering that box into the cache (one request at a time) and exits:
  no database access, nothing is built. Use it ahead of a collection job so
  the rebuild afterwards needs no network.
- ``--cached-only`` builds a PARTIAL layer from the tiles already cached and
  leaves out the frames of the others (for when Overpass is slow/unreachable).
- ``--no-merge`` cuts every OSM way on its own (no stitching) — for
  comparison; expect many short, low-confidence pieces in cities.
- OSM ways come from the public Overpass API, one tile at a time, and the raw
  responses are cached under data/osm/ — a rebuild normally needs no network.
  ``--offline`` forbids fetching (fails if a tile is missing from the cache).
- Aggregation parameters: backend/config/segment_aggregation.json
  (see app/services/segment_aggregation.py). The two flags override it for
  experiments without editing the file.
- ``--dry-run`` computes and prints the stats but writes nothing.

Needs the local DB (table from Alembic revision 0005). Geometry
© OpenStreetMap contributors (ODbL).
"""
from __future__ import annotations

import argparse
import os
import sys

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.segment_aggregation import AGGREGATORS, load_config, with_overrides  # noqa: E402


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """``minLng,minLat,maxLng,maxLat`` → (south, west, north, east)."""
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "bbox must be 'minLng,minLat,maxLng,maxLat'"
        ) from exc
    if min_lng > max_lng or min_lat > max_lat:
        raise argparse.ArgumentTypeError("bbox min must not exceed max")
    return (min_lat, min_lng, max_lat, max_lng)


def prefetch_tiles(bounds: tuple[float, float, float, float]) -> int:
    """Cache every OSM tile overlapping ``bounds``; returns the exit code."""
    import time

    from app.core.paths import data_path
    from app.services.osm_overpass import OverpassClient, OverpassError, tiles_in_bounds

    client = OverpassClient(data_path("osm"))
    tiles = tiles_in_bounds(bounds, client.tile_deg)
    missing = [t for t in tiles if not client.is_cached(t)]
    print(f"{len(tiles)} tiles cover the box, {len(tiles) - len(missing)} already cached, "
          f"{len(missing)} to fetch (one at a time)", flush=True)
    failed = []
    for i, tile in enumerate(missing, 1):
        started = time.monotonic()
        try:
            client.fetch_tile(tile)
            print(f"  {i}/{len(missing)} {tile} cached ({time.monotonic() - started:.0f}s)", flush=True)
        except OverpassError as exc:
            failed.append(tile)
            print(f"  {i}/{len(missing)} {tile} FAILED: {exc}", flush=True)
    print(f"done: {len(missing) - len(failed)} fetched, {len(failed)} failed {failed or ''}",
          flush=True)
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", type=parse_bbox, default=None,
                    help="minLng,minLat,maxLng,maxLat — rebuild only this area")
    ap.add_argument("--prefetch-bbox", type=parse_bbox, default=None,
                    help="only cache the OSM tiles covering this box, then exit (no DB)")
    ap.add_argument("--dry-run", action="store_true", help="compute stats, write nothing")
    ap.add_argument("--offline", action="store_true",
                    help="use only cached OSM tiles (no Overpass requests)")
    ap.add_argument("--cached-only", action="store_true",
                    help="build from the tiles already cached and leave out the frames "
                         "of the others (partial layer; no Overpass requests)")
    ap.add_argument("--no-merge", action="store_true",
                    help="do not stitch consecutive ways of a road; cut each OSM way")
    ap.add_argument("--config", default=None, help="alternative aggregation config JSON")
    ap.add_argument("--segment-length", type=float, default=None,
                    help="override segment_length_m")
    ap.add_argument("--aggregator", choices=AGGREGATORS, default=None,
                    help="override aggregator")
    args = ap.parse_args()

    if args.prefetch_bbox is not None:
        sys.exit(prefetch_tiles(args.prefetch_bbox))

    try:
        cfg = load_config(args.config)
        overrides = {}
        if args.segment_length is not None:
            overrides["segment_length_m"] = args.segment_length
        if args.aggregator is not None:
            overrides["aggregator"] = args.aggregator
        if overrides:
            cfg = with_overrides(cfg, **overrides)
    except ValueError as exc:
        sys.exit(f"Bad aggregation config: {exc}")

    from sqlalchemy import inspect

    from app.core.database import SessionLocal, engine
    from app.services.osm_overpass import OverpassError
    from app.services.road_segments import rebuild_segments

    if not args.dry_run and not inspect(engine).has_table("road_segments"):
        sys.exit("Table road_segments is missing — run the migrations first "
                 "(alembic upgrade head, or start the backend once).")

    print(f"config: segment_length_m={cfg.segment_length_m:g} aggregator={cfg.aggregator} "
          f"thresholds={list(cfg.thresholds)} classes={list(cfg.scale.classes)} "
          f"({'higher' if cfg.scale.higher_is_worse else 'lower'} = worse) "
          f"min_images={cfg.min_images}")
    db = SessionLocal()
    try:
        stats = rebuild_segments(
            db, bbox=args.bbox, cfg=cfg, allow_fetch=not args.offline,
            cached_only=args.cached_only, merge=not args.no_merge, dry_run=args.dry_run,
        )
    except OverpassError as exc:
        sys.exit(f"OSM data unavailable, nothing written: {exc}")
    finally:
        db.close()

    print("\n".join(stats.report()))


if __name__ == "__main__":
    main()
