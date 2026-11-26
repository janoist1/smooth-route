"""Publish local road data to the public (Neon) read-only DB.

Usage (from backend/):
    PUBLISH_DATABASE_URL='postgresql://...neon...' ../.venv/bin/python scripts/publish.py
    ../.venv/bin/python scripts/publish.py --dry-run     # read + report, write nothing

Full-replaces street_view_images on the target with the public columns from the
local DB. Drops image_url (the public site links out to Street View instead of
serving stored images) and location (the map reads use plain lat/lng). Ensures
the target schema first via Alembic — on a fresh Neon DB this also runs
`CREATE EXTENSION postgis` and creates the tables.

road_segments (the road-segment layer, built locally by
scripts/build_segments.py) is full-replaced as well, in the SAME transaction,
so the public site never shows points and segments from different publishes.
Run build_segments.py before publishing; if the local table is missing or
empty the target's segments are emptied too (and a warning is printed).

The target URL is read from PUBLISH_DATABASE_URL (never hard-code it / commit it).
"""
import argparse
import os
import sys

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import command  # noqa: E402
from sqlalchemy import create_engine, inspect, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.migrations import alembic_config  # noqa: E402
from app.models.models import RoadSegment, StreetViewImage  # noqa: E402

# Columns the public site reads. image_url + location are intentionally omitted
# (published as NULL): the site shows a Street View deep-link, not stored images.
PUBLIC_COLUMNS = [
    "id",
    "latitude",
    "longitude",
    "heading",
    "pitch",
    "rqi_score",
    "dino_rqi_score",
    "damage_count",
    "damage_types",
    "analysis_metadata",
    "pano_id",
    "capture_date",  # Street View capture month → "Kép készült" on the card
    "created_at",
]

# road_segments is derived, public-by-nature data (OSM geometry + aggregates):
# every column is published as is.
SEGMENT_COLUMNS = [c.name for c in RoadSegment.__table__.columns]

BATCH = 2000


def read_segments(src_engine) -> list[dict]:
    """All local road segments as insertable dicts ([] if never built)."""
    if not inspect(src_engine).has_table(RoadSegment.__tablename__):
        print("WARNING: source has no road_segments table — run the migrations "
              "and scripts/build_segments.py; publishing 0 segments")
        return []
    with Session(src_engine) as src:
        rows = src.execute(
            select(*[getattr(RoadSegment, c) for c in SEGMENT_COLUMNS])
        ).all()
    if not rows:
        print("WARNING: source road_segments is empty — run "
              "scripts/build_segments.py; publishing 0 segments")
    # geom travels as a geoalchemy2 WKBElement (with its SRID) and is bound
    # back through ST_GeomFromEWKB on insert.
    return [dict(zip(SEGMENT_COLUMNS, row)) for row in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="read the source and report what would be published; "
                         "the target is not contacted")
    args = ap.parse_args()

    target_url = os.environ.get("PUBLISH_DATABASE_URL")
    if not target_url and not args.dry_run:
        sys.exit("Set PUBLISH_DATABASE_URL to the target (Neon) connection string.")
    source_url = settings.DATABASE_URL
    target_label = target_url.split("@")[-1] if target_url else "(not set)"
    print(f"source: {source_url.split('@')[-1]}  →  target: {target_label}")

    src_engine = create_engine(source_url)

    with Session(src_engine) as src:
        rows = src.execute(
            select(*[getattr(StreetViewImage, c) for c in PUBLIC_COLUMNS])
        ).all()
    print(f"read {len(rows)} rows from source")

    payload = [
        {**dict(zip(PUBLIC_COLUMNS, row)), "image_url": None, "location": None}
        for row in rows
    ]
    segments = read_segments(src_engine)
    with_data = sum(1 for s in segments if s["n_images"])
    print(f"read {len(segments)} road segments from source ({with_data} with data)")

    if args.dry_run:
        print(f"DRY RUN: would publish {len(payload)} rows and {len(segments)} "
              f"road segments; target untouched")
        return

    # 1) Ensure the target schema (PostGIS + tables on a fresh DB; no-op after).
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", target_url)
    command.upgrade(cfg, "head")

    tgt_engine = create_engine(target_url)

    # 2) Full-replace both target tables in one transaction.
    with tgt_engine.begin() as conn:
        conn.execute(text("TRUNCATE street_view_images"))
        for i in range(0, len(payload), BATCH):
            conn.execute(StreetViewImage.__table__.insert(), payload[i : i + BATCH])
        conn.execute(text("TRUNCATE road_segments"))
        for i in range(0, len(segments), BATCH):
            conn.execute(RoadSegment.__table__.insert(), segments[i : i + BATCH])

    print(f"published {len(payload)} rows (image_url + location dropped) "
          f"and {len(segments)} road segments")


if __name__ == "__main__":
    main()
