"""Add road_segments (OSM road pieces with aggregated quality).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26

Purely additive: one new table, nothing existing is touched. The table is
derived data — `backend/scripts/build_segments.py` fills it from
street_view_images + cached OSM geometry.

The upgrade is idempotent on purpose (skips when the table already exists):
the table may have been created on a shared dev database before this revision
reached every checkout, and stamping a revision that other checkouts do not
know yet would break their startup migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("road_segments"):
        return

    op.create_table(
        "road_segments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("osm_way_id", sa.BigInteger(), nullable=False),
        sa.Column("piece_index", sa.Integer(), nullable=False),
        # spatial_index=False: the GiST index is created explicitly below so
        # the migration does not depend on geoalchemy2 DDL event listeners.
        sa.Column(
            "geom",
            Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column("road_name", sa.String(), nullable=True),
        sa.Column("highway", sa.String(), nullable=True),
        sa.Column("n_images", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rqi", sa.Integer(), nullable=True),
        sa.Column("p_bad", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("capture_date_min", sa.Date(), nullable=True),
        sa.Column("capture_date_max", sa.Date(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("osm_way_id", "piece_index", name="uq_road_segments_way_piece"),
    )
    op.create_index("ix_road_segments_osm_way_id", "road_segments", ["osm_way_id"])
    op.create_index(
        "idx_road_segments_geom", "road_segments", ["geom"], postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_index("idx_road_segments_geom", table_name="road_segments")
    op.drop_index("ix_road_segments_osm_way_id", table_name="road_segments")
    op.drop_table("road_segments")
