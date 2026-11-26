"""road_segments.unlabelled_area: the unlabelled-area confidence cap flag.

True when the segment builder capped the segment's confidence because no
human-labelled frame lies within segment_aggregation.json
unlabelled_area.radius_km (confidenceReason "unlabelled_area"). Idempotent:
skips when the table is missing or the column already exists.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("road_segments"):
        return set()
    return {c["name"] for c in insp.get_columns("road_segments")}


def upgrade() -> None:
    cols = _columns()
    if cols and "unlabelled_area" not in cols:
        op.add_column("road_segments", sa.Column(
            "unlabelled_area", sa.Boolean(), nullable=False,
            server_default=sa.false()))


def downgrade() -> None:
    if "unlabelled_area" in _columns():
        op.drop_column("road_segments", "unlabelled_area")
