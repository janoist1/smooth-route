"""Publish local road data to the public (Neon) read-only DB.

Usage (from backend/):
    PUBLISH_DATABASE_URL='postgresql://...neon...' ../.venv/bin/python scripts/publish.py
    ../.venv/bin/python scripts/publish.py --dry-run     # read + report, write nothing

Release order and rollback: docs/RELEASE.md. Run it from the commit you are
about to deploy: the migrations and the column list must match that code.

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

The replace uses DELETE, not TRUNCATE: TRUNCATE holds an ACCESS EXCLUSIVE lock
until commit, so every live read on the public site would hang for the whole
upload. With DELETE, readers keep seeing the old rows until the commit.

--dry-run with PUBLISH_DATABASE_URL set also reports the target's state (Alembic
revision, pending migrations, row counts) over a read-only transaction.

The target URL is read from PUBLISH_DATABASE_URL (never hard-code it / commit it).
Use Neon's direct (unpooled) URL: migrations need a session, not PgBouncer.
"""
import argparse
import os
import sys

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import command  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine, inspect, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.migrations import alembic_config  # noqa: E402
from app.core.secret_scan import find_secrets  # noqa: E402
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

# Tables publish.py full-replaces, in this order, inside one transaction.
REPLACED_TABLES = (StreetViewImage.__tablename__, RoadSegment.__tablename__)


def replace_statements() -> list[str]:
    """Row-level deletes (readers keep the old snapshot until commit)."""
    return [f"DELETE FROM {table}" for table in REPLACED_TABLES]


def alembic_url(url: str) -> str:
    """Alembic's config is a ConfigParser: a literal '%' (URL-encoded password)
    must be doubled or set_main_option raises."""
    return url.replace("%", "%%")


def pending_revisions(cfg, current: str | None) -> list[str]:
    """Revisions `upgrade head` would apply after `current`, oldest first."""
    script = ScriptDirectory.from_config(cfg)
    revs = [r.revision for r in script.walk_revisions("base", "heads")]
    revs.reverse()  # walk_revisions yields newest first
    if current is None:
        return revs
    if current not in revs:
        raise SystemExit(f"Target is at unknown revision {current!r}; this checkout "
                         f"knows {revs[0]}..{revs[-1]}. Publish from the release commit.")
    return revs[revs.index(current) + 1:]


def target_state(target_url: str) -> dict:
    """Read-only look at the target: revision and row counts."""
    engine = create_engine(target_url)
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        insp = inspect(conn)
        state = {"revision": None, "has_app_tables": insp.has_table("street_view_images")}
        if insp.has_table("alembic_version"):
            state["revision"] = conn.execute(
                text("SELECT version_num FROM alembic_version")).scalar()
        for table in REPLACED_TABLES:
            state[table] = (conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                            if insp.has_table(table) else None)
    engine.dispose()
    return state


def check_target(cfg, target_url: str) -> list[str]:
    """Print the target's state; refuse a target Alembic cannot upgrade safely."""
    state = target_state(target_url)
    if state["has_app_tables"] and state["revision"] is None:
        raise SystemExit("Target has tables but no alembic_version row: upgrade would "
                         "try to recreate them. Stamp it first (docs/RELEASE.md).")
    pending = pending_revisions(cfg, state["revision"])
    print(f"target revision: {state['revision'] or '(empty database)'}; "
          f"pending migrations: {', '.join(pending) or 'none'}")
    print("target rows now: " + ", ".join(
        f"{t}={state[t] if state[t] is not None else '(no table)'}" for t in REPLACED_TABLES))
    return pending


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
                         "the target (if set) is only read, never written")
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

    # Never ship a credential (e.g. a Street View Static URL with ?key= in a
    # local image_url). image_url is already dropped; this guards every column.
    leaks = find_secrets(payload) + find_secrets(segments)
    if leaks:
        for row_id, column, kind in leaks[:20]:
            print(f"SECRET in row {row_id} column {column}: {kind}")
        sys.exit(f"Refusing to publish: {len(leaks)} value(s) look like credentials.")

    cfg = alembic_config()
    if target_url:
        cfg.set_main_option("sqlalchemy.url", alembic_url(target_url))
        check_target(cfg, target_url)

    if args.dry_run:
        print(f"DRY RUN: would publish {len(payload)} rows and {len(segments)} "
              f"road segments; target untouched")
        return

    # 1) Ensure the target schema (PostGIS + tables on a fresh DB; no-op after).
    command.upgrade(cfg, "head")

    tgt_engine = create_engine(target_url)

    # 2) Full-replace both target tables in one transaction. Live readers see
    #    the previous publish until COMMIT (see replace_statements).
    with tgt_engine.begin() as conn:
        for stmt in replace_statements():
            conn.execute(text(stmt))
        for i in range(0, len(payload), BATCH):
            conn.execute(StreetViewImage.__table__.insert(), payload[i : i + BATCH])
        for i in range(0, len(segments), BATCH):
            conn.execute(RoadSegment.__table__.insert(), segments[i : i + BATCH])

    print(f"published {len(payload)} rows (image_url + location dropped) "
          f"and {len(segments)} road segments")


if __name__ == "__main__":
    main()
