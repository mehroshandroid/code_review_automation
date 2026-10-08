"""retire the 'completed' review status: reviews are pending_approval -> approved

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 'completed' meant the same as 'approved' (a reviewer had signed it off).
    op.execute("UPDATE platform_reviews SET approved_at = COALESCE(approved_at, completed_at, created_at) WHERE status = 'completed'")
    op.execute("UPDATE platform_reviews SET status = 'approved' WHERE status = 'completed'")


def downgrade() -> None:
    # Not reversible: the migrated rows are indistinguishable from approved ones.
    pass
