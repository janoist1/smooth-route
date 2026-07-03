"""Add pano_id to street_view_images (R1.1 — Street View deep-link).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "street_view_images", sa.Column("pano_id", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_street_view_images_pano_id", "street_view_images", ["pano_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_street_view_images_pano_id", table_name="street_view_images")
    op.drop_column("street_view_images", "pano_id")
