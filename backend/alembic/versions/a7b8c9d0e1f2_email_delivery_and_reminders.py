"""email delivery state on the outbox; reminder timestamps on assignments

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Rows recorded before delivery existed are stale -- never send them.
SKIP_EXISTING_SQL = "UPDATE notification_outbox SET status = 'skipped'"


def upgrade() -> None:
    op.add_column("notification_outbox", sa.Column("status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("notification_outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notification_outbox", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("notification_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification_outbox", sa.Column("subject", sa.String(), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("pm_reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("reviewer_reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(SKIP_EXISTING_SQL)


def downgrade() -> None:
    op.drop_column("review_cycle_assignments", "reviewer_reminded_at")
    op.drop_column("review_cycle_assignments", "pm_reminded_at")
    for name in ("subject", "next_attempt_at", "last_error", "attempts", "status"):
        op.drop_column("notification_outbox", name)
