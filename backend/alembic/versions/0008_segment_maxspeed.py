"""road_segments.maxspeed_kmh: OSM speed limit for speed-weighted route scoring.

Nullable; NULL means "not tagged" and the route scorer uses the highway-class
default from config/route_scoring.json. Filled by scripts/build_segments.py.
Additive and idempotent (skips a missing table or an existing column).

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("road_segments"):
        return set()
    return {c["name"] for c in insp.get_columns("road_segments")}


def upgrade() -> None:
    cols = _columns()
    if cols and "maxspeed_kmh" not in cols:
        op.add_column("road_segments", sa.Column("maxspeed_kmh", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "maxspeed_kmh" in _columns():
        op.drop_column("road_segments", "maxspeed_kmh")
