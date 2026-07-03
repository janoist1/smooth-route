"""Publish local road data to the public (Neon) read-only DB.

Usage (from backend/):
    PUBLISH_DATABASE_URL='postgresql://...neon...' ../.venv/bin/python scripts/publish.py

Full-replaces street_view_images on the target with the public columns from the
local DB. Drops image_url (the public site links out to Street View instead of
serving stored images) and location (the map reads use plain lat/lng). Ensures
the target schema first via Alembic — on a fresh Neon DB this also runs
`CREATE EXTENSION postgis` and creates the tables.

The target URL is read from PUBLISH_DATABASE_URL (never hard-code it / commit it).
"""
import os
import sys

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import command  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.migrations import alembic_config  # noqa: E402
from app.models.models import StreetViewImage  # noqa: E402

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
    "created_at",
]

BATCH = 2000


def main() -> None:
    target_url = os.environ.get("PUBLISH_DATABASE_URL")
    if not target_url:
        sys.exit("Set PUBLISH_DATABASE_URL to the target (Neon) connection string.")
    source_url = settings.DATABASE_URL
    print(f"source: {source_url.split('@')[-1]}  →  target: {target_url.split('@')[-1]}")

    # 1) Ensure the target schema (PostGIS + tables on a fresh DB; no-op after).
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", target_url)
    command.upgrade(cfg, "head")

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    with Session(src_engine) as src:
        rows = src.execute(
            select(*[getattr(StreetViewImage, c) for c in PUBLIC_COLUMNS])
        ).all()
    print(f"read {len(rows)} rows from source")

    payload = [
        {**dict(zip(PUBLIC_COLUMNS, row)), "image_url": None, "location": None}
        for row in rows
    ]

    # 2) Full-replace the target table in one transaction.
    with tgt_engine.begin() as conn:
        conn.execute(text("TRUNCATE street_view_images"))
        for i in range(0, len(payload), BATCH):
            conn.execute(StreetViewImage.__table__.insert(), payload[i : i + BATCH])

    print(f"published {len(payload)} rows (image_url + location dropped)")


if __name__ == "__main__":
    main()
