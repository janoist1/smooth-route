"""Flip the stored RQI numbering: x -> 6 - x (1 = best  <->  5 = best).

ACTIVE since 2026-11-26 (owner: "5 kiváló mehet"). Runbook and history:
shared/README.md. Dry-run on a DB (read-only, describes what upgrade() would
do): backend/scripts/rqi_flip_dry_run.py.

Revision ID: 0006
Revises: 0005

Mirrored (every stored value on the 1-5 RQI scale, continuous ones too):
  training_data.manual_rqi                         human labels (1.5 -> 4.5 ...)
  street_view_images.rqi_score                     YOLO damage-derived level
  street_view_images.dino_rqi_score                DINO level
  street_view_images.analysis_metadata.dino_score  continuous DINO estimate
  street_view_images.analysis_metadata.dino_rqi_score_prev  pre-rescore class
                                                   (scripts/rescore_dino.py)
  road_segments.score, road_segments.rqi           only if the table exists
  training_data.manual_dino_rqi                    legacy, unused column (only if present)
Not touched: probabilities (dino_p_bad, road_segments.p_bad, confidence). They
describe "bad road", the same event on either numbering. Legacy heuristic
metadata (damage_score, damage_percent, rqi_thresholds) is not on the RQI scale.

x -> 6 - x is its own inverse, so downgrade() runs the same statements. The
numbers are frozen here on purpose (a migration must not change meaning when
app code evolves). The only app import is the guard below.

Guard: upgrade() refuses to run unless the deployed scale
(backend/app/core/rqi_scale.json) already says direction=higher_is_better, so
moving this file into versions/ without flipping the JSON fails loudly instead
of silently inverting the data. downgrade() has no guard (rollback = `alembic
downgrade <previous>` with the flipped code, then revert the flip commit; keep
the app stopped in between).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIRROR = 6  # min + max of the 1-5 scale

# (table, column) holding an RQI value; required tables must exist.
COLUMN_TARGETS = (
    ("training_data", "manual_rqi"),
    ("street_view_images", "rqi_score"),
    ("street_view_images", "dino_rqi_score"),
)
# Mirrored only when present: road_segments comes from the road-segment work
# (0005); manual_dino_rqi is a pre-Alembic leftover no code reads any more
# (see 0001_baseline) that still holds 1-5 values on old dev databases.
OPTIONAL_COLUMN_TARGETS = (
    ("road_segments", "score"),
    ("road_segments", "rqi"),
    ("training_data", "manual_dino_rqi"),
)
# (table, json column, key, decimals kept): RQI values inside a JSON document.
JSON_TARGETS = (
    ("street_view_images", "analysis_metadata", "dino_score", 3),
    ("street_view_images", "analysis_metadata", "dino_rqi_score_prev", 3),
)


def mirror_expr(column: str) -> str:
    return f"({MIRROR} - {column})"


def json_value_expr(column: str, key: str) -> str:
    return f"({column}->>'{key}')::numeric"


def json_mirror_expr(column: str, key: str, decimals: int) -> str:
    return f"round({MIRROR} - {json_value_expr(column, key)}, {decimals})"


def column_update_sql(table: str, column: str) -> str:
    return (f"UPDATE {table} SET {column} = {mirror_expr(column)} "
            f"WHERE {column} IS NOT NULL")


def json_update_sql(table: str, column: str, key: str, decimals: int,
                    column_type: str = "json") -> str:
    # jsonb_set needs jsonb; cast back to the column's own type (json here).
    return (f"UPDATE {table} SET {column} = jsonb_set({column}::jsonb, "
            f"'{{{key}}}', to_jsonb({json_mirror_expr(column, key, decimals)}))"
            f"::{column_type} "
            f"WHERE {column}->>'{key}' IS NOT NULL")


def flip_statements(bind) -> list:
    """The UPDATEs for this database (optional tables only if they exist)."""
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    stmts = []
    for table, column in COLUMN_TARGETS:
        stmts.append(column_update_sql(table, column))
    for table, column in OPTIONAL_COLUMN_TARGETS:
        if table in tables and column in {c["name"] for c in insp.get_columns(table)}:
            stmts.append(column_update_sql(table, column))
    for table, column, key, decimals in JSON_TARGETS:
        col_type = next(c["type"] for c in insp.get_columns(table) if c["name"] == column)
        type_name = "jsonb" if "JSONB" in str(col_type).upper() else "json"
        stmts.append(json_update_sql(table, column, key, decimals, type_name))
    return stmts


def _deployed_direction() -> str:
    from app.core.rqi_scale import load_scale  # read fresh, not the cached SCALE
    return load_scale().direction


def _apply() -> None:
    bind = op.get_bind()
    for stmt in flip_statements(bind):
        op.execute(stmt)


def upgrade() -> None:
    direction = _deployed_direction()
    if direction != "higher_is_better":
        raise RuntimeError(
            f"RQI flip refused: backend/app/core/rqi_scale.json says direction="
            f"{direction!r}. Flip shared/rqi_scale.json and run "
            f"scripts/sync_rqi_scale.py in the SAME change that activates this "
            f"migration (runbook: shared/README.md).")
    _apply()


def downgrade() -> None:
    _apply()  # x -> 6 - x is its own inverse
