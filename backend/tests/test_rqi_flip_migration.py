"""The pending RQI direction-flip migration (phase 2): shape and guard, no DB.

The real data path is exercised by scripts/rqi_flip_dry_run.py (read-only)
and scripts/rqi_flip_rehearsal.py (throwaway container).
"""
import importlib.util
import os

import pytest

from app.core.rqi_scale import SCALE

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING = os.path.join(BACKEND, "alembic", "pending", "rqi_flip_direction.py")


@pytest.fixture()
def M():
    spec = importlib.util.spec_from_file_location("rqi_flip_direction_under_test", PENDING)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mirror_constant_matches_the_scale(M):
    assert M.MIRROR == SCALE.min_value + SCALE.max_value == 6


def test_targets_cover_every_stored_rqi_value(M):
    assert set(M.COLUMN_TARGETS) == {
        ("training_data", "manual_rqi"),
        ("street_view_images", "rqi_score"),
        ("street_view_images", "dino_rqi_score"),
    }
    assert ("street_view_images", "analysis_metadata", "dino_score", 3) in M.JSON_TARGETS
    # rescore_dino.py keeps the class a frame had before re-scoring
    assert ("street_view_images", "analysis_metadata", "dino_rqi_score_prev", 3) in M.JSON_TARGETS
    # probabilities describe the same event on either numbering -> never mirrored
    flat = " ".join(str(t) for t in M.COLUMN_TARGETS + M.OPTIONAL_COLUMN_TARGETS + M.JSON_TARGETS)
    assert "p_bad" not in flat and "confidence" not in flat


def test_sql_is_its_own_inverse(M):
    assert M.column_update_sql("t", "c") == "UPDATE t SET c = (6 - c) WHERE c IS NOT NULL"
    sql = M.json_update_sql("t", "meta", "dino_score", 3)
    assert "jsonb_set(meta::jsonb, '{dino_score}'" in sql
    assert "round(6 - (meta->>'dino_score')::numeric, 3)" in sql and sql.endswith(
        "WHERE meta->>'dino_score' IS NOT NULL")
    for x in (1, 1.5, 2.482, 3.5, 4, 5):
        assert M.MIRROR - (M.MIRROR - x) == pytest.approx(x)


def test_upgrade_refuses_until_the_json_is_flipped(M):
    M._deployed_direction = lambda: "lower_is_better"
    with pytest.raises(RuntimeError, match="RQI flip refused"):
        M.upgrade()


def test_is_not_active_yet():
    # Phase 1: the file must stay out of alembic/versions (startup and
    # publish.py run `upgrade head`). Moving it is step 3 of the flip runbook.
    versions = os.path.join(BACKEND, "alembic", "versions")
    assert "rqi_flip_direction.py" not in os.listdir(versions)
    assert os.path.exists(PENDING)
