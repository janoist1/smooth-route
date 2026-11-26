"""Add capture_date to street_view_images (Street View panorama capture month).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18

pano_id already exists (0003). Existing rows stay NULL until
`backend/scripts/backfill_capture_date.py` fills them from the free Street View
Metadata API.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "street_view_images", sa.Column("capture_date", sa.Date(), nullable=True)
    )
    op.create_index(
        "ix_street_view_images_capture_date", "street_view_images", ["capture_date"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_street_view_images_capture_date", table_name="street_view_images"
    )
    op.drop_column("street_view_images", "capture_date")
