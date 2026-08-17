"""constrain total_score_pct to numeric(4,1)

Revision ID: c8f53ea38307
Revises: d88bf1c5135c
Create Date: 2026-08-17 12:09:04.445163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f53ea38307'
down_revision: Union[str, None] = 'd88bf1c5135c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The column was created as an unconstrained NUMERIC, which stores the
    # exact binary expansion of a Python float (e.g. round(x, 1) producing
    # 88.4 gets stored as 88.400000000000005684...) instead of rounding to
    # a sane scale. USING re-rounds every existing row to 1 decimal place
    # as part of the type change, fixing already-corrupted data in the
    # same statement that fixes the schema.
    op.alter_column(
        "platform_reviews",
        "total_score_pct",
        type_=sa.Numeric(4, 1),
        postgresql_using="round(total_score_pct, 1)",
    )


def downgrade() -> None:
    op.alter_column(
        "platform_reviews",
        "total_score_pct",
        type_=sa.Numeric(),
    )
