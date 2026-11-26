"""The frame-location backfill is a single guarded UPDATE, with no destructive rollback."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0010_frame_location.py"
    spec = importlib.util.spec_from_file_location("frame_location_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_location_migration_follows_current_head(migration):
    assert (migration.revision, migration.down_revision) == ("0010", "0009")


def test_location_backfill_is_one_idempotent_update(monkeypatch, migration):
    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.upgrade()
    assert [" ".join(str(sql).split()) for sql in statements] == [
        "UPDATE street_view_images "
        "SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
        "WHERE location IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL"
    ]


def test_location_backfill_downgrade_preserves_geometry(monkeypatch, migration):
    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.downgrade()
    assert statements == []
