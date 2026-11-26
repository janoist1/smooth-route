"""Backfill missing frame geometry from latitude/longitude.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE street_view_images
        SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE location IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
    """)


def downgrade() -> None:
    # Derived geometry is still valid for older code; never erase it on rollback.
    pass
