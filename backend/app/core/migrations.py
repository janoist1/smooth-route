"""Programmatic Alembic runner used at app startup.

Replaces the old Base.metadata.create_all: the schema is owned by the
migrations under backend/alembic. Databases created before Alembic existed
(no alembic_version table but the legacy tables present) are adopted by
stamping the baseline revision, then upgraded to head like everyone else.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"

# Serializes concurrent startup migrations (multiple workers, uvicorn --reload
# restarts). Arbitrary app-unique constant for pg_advisory_lock.
MIGRATION_LOCK_KEY = 7245001


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def ensure_database_schema() -> None:
    """Bring the database to the current migration head.

    Holds a Postgres advisory lock for the duration so that concurrent app
    starts (dev reload, multi-worker deployments) cannot interleave DDL.
    """
    from app.core.database import engine

    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        try:
            # Re-inspect inside the lock: another process may have just migrated.
            inspector = inspect(engine)
            pre_alembic = not inspector.has_table("alembic_version") and inspector.has_table(
                "street_view_images"
            )

            cfg = alembic_config()
            if pre_alembic:
                logger.info(
                    "Pre-Alembic database detected — stamping baseline %s", BASELINE_REVISION
                )
                command.stamp(cfg, BASELINE_REVISION)
            command.upgrade(cfg, "head")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
