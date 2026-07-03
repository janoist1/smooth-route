"""Baseline: the pre-Alembic schema as create_all produced it.

Captures street_view_images, jobs and training_data exactly as
Base.metadata.create_all built them on 2026-07-03. Existing databases are
adopted by stamping this revision (see app/core/migrations.py); fresh
databases run it for real.

Known drift on pre-existing dev databases (documented, not healed here):
ix_street_view_images_dino_rqi_score may be missing (column was added by
hand after the table existed), training_data may carry a legacy
manual_dino_rqi column, and an orphaned analysis_settings table may exist.

Revision ID: 0001
Revises:
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "street_view_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("pitch", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        # spatial_index=False: both indexes are created explicitly below so
        # the migration does not depend on geoalchemy2 DDL event listeners.
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("rqi_score", sa.Float(), nullable=True),
        sa.Column("damage_count", sa.Integer(), nullable=True),
        sa.Column("damage_types", sa.JSON(), nullable=True),
        sa.Column("analysis_metadata", sa.JSON(), nullable=True),
        sa.Column("dino_rqi_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_street_view_images_id", "street_view_images", ["id"])
    op.create_index("ix_street_view_images_latitude", "street_view_images", ["latitude"])
    op.create_index("ix_street_view_images_longitude", "street_view_images", ["longitude"])
    op.create_index("ix_street_view_images_heading", "street_view_images", ["heading"])
    op.create_index("ix_street_view_images_rqi_score", "street_view_images", ["rqi_score"])
    op.create_index("ix_street_view_images_dino_rqi_score", "street_view_images", ["dino_rqi_score"])
    op.create_index(
        "idx_street_view_images_location",
        "street_view_images",
        ["location"],
        postgresql_using="gist",
    )
    # Faithful replica of Column(index=True) on the geometry column: create_all
    # emitted this redundant btree index alongside the gist one.
    op.create_index("ix_street_view_images_location", "street_view_images", ["location"])

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("current_step", sa.String(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_jobs_job_id", "jobs", ["job_id"])

    op.create_table(
        "training_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_filename", sa.String(), nullable=True),
        sa.Column("manual_rqi", sa.Float(), nullable=True),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("rqi_area_percent", sa.Float(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_data_id", "training_data", ["id"])
    op.create_index(
        "ix_training_data_image_filename",
        "training_data",
        ["image_filename"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("training_data")
    op.drop_table("jobs")
    op.drop_table("street_view_images")
