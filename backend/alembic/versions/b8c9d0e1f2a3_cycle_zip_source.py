"""cycle assignments can be sourced from an uploaded zip instead of a DevOps URL

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("review_cycle_assignments", sa.Column("source_type", sa.String(), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("source_zip_path", sa.String(), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("source_zip_name", sa.String(), nullable=True))
    op.execute("UPDATE review_cycle_assignments SET source_type = 'devops' WHERE devops_url IS NOT NULL")


def downgrade() -> None:
    for name in ("source_zip_name", "source_zip_path", "source_type"):
        op.drop_column("review_cycle_assignments", name)
