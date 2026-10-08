"""review queue monitor: queue pause state, per-run overrides, cancellation requests

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("cancel_requested", "override_llm_provider", "override_llm_model", "override_compile_mode")


def upgrade() -> None:
    op.create_table(
        "review_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paused_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name in _COLUMNS:
        op.add_column("review_cycle_assignments", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("review_cycle_assignments", name)
    op.drop_table("review_queue_state")
