"""project platforms and quarterly review cycles

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.backfills import backfill_project_platforms


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_platforms",
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("platform", sa.String(), primary_key=True),
    )
    op.create_table(
        "review_cycles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("initiated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "year", "quarter"),
    )
    op.create_table(
        "review_cycle_assignments",
        sa.Column("cycle_id", sa.String(), sa.ForeignKey("review_cycles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("platform", sa.String(), primary_key=True),
        sa.Column("reviewer_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    backfill_project_platforms(op.get_bind())


def downgrade() -> None:
    op.drop_table("review_cycle_assignments")
    op.drop_table("review_cycles")
    op.drop_table("project_platforms")
