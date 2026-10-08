"""automated cycle reviews: assignment run state, org PAT/compile modes, notification outbox

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ASSIGNMENT_COLUMNS = [
    sa.Column("devops_url", sa.String(), nullable=True),
    sa.Column("devops_branch", sa.String(), nullable=True),
    sa.Column("url_submitted_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("url_submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("run_status", sa.String(), nullable=False, server_default="waiting_for_url"),
    sa.Column("run_phase", sa.String(), nullable=True),
    sa.Column("run_progress", sa.Integer(), nullable=True),
    sa.Column("run_error", sa.Text(), nullable=True),
    sa.Column("failure_kind", sa.String(), nullable=True),
    sa.Column("review_id", sa.String(), sa.ForeignKey("platform_reviews.id", ondelete="SET NULL"), nullable=True),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("reviewer_assigned_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("reviewer_assigned_at", sa.DateTime(timezone=True), nullable=True),
]
_ORG_COLUMNS = [
    sa.Column("devops_pat_encrypted", sa.Text(), nullable=True),
    sa.Column("devops_pat_last4", sa.String(), nullable=True),
    sa.Column("devops_pat_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("devops_pat_updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("auto_compile_modes", sa.JSON(), nullable=True),
]


def upgrade() -> None:
    for column in _ASSIGNMENT_COLUMNS:
        op.add_column("review_cycle_assignments", column)
    for column in _ORG_COLUMNS:
        op.add_column("org_settings", column)
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("recipient_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("notification_outbox")
    for column in reversed(_ORG_COLUMNS):
        op.drop_column("org_settings", column.name)
    for column in reversed(_ASSIGNMENT_COLUMNS):
        op.drop_column("review_cycle_assignments", column.name)
