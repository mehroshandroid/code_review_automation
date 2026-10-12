"""a cycle platform can be reinitiated after approval: rounds and their history

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("review_cycle_assignments", sa.Column("round", sa.Integer(), nullable=False, server_default="1"))
    op.create_table(
        "review_cycle_rounds",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("cycle_id", sa.String(), sa.ForeignKey("review_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.String(), sa.ForeignKey("platform_reviews.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("cycle_id", "platform", "round", name="uq_review_cycle_rounds_round"),
    )
    op.create_index("ix_review_cycle_rounds_cycle_id", "review_cycle_rounds", ["cycle_id"])


def downgrade() -> None:
    op.drop_index("ix_review_cycle_rounds_cycle_id", table_name="review_cycle_rounds")
    op.drop_table("review_cycle_rounds")
    op.drop_column("review_cycle_assignments", "round")
