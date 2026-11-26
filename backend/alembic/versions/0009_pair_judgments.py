"""pair_judgments: pairwise "which frame shows the worse road?" judgments.

Additive and idempotent (skips when the table exists). Written by the
quick-rate page's pairwise mode; read by ml/pairwise_scores.py.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("pair_judgments"):
        return
    op.create_table(
        "pair_judgments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(), nullable=False, unique=True),
        sa.Column("frame_a_id", sa.Integer(), nullable=False, index=True),
        sa.Column("frame_b_id", sa.Integer(), nullable=False, index=True),
        sa.Column("result", sa.String(5), nullable=False),
        sa.Column("labeller", sa.String(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("result IN ('A', 'B', 'EQUAL')", name="ck_pair_judgments_result"),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("pair_judgments"):
        op.drop_table("pair_judgments")
