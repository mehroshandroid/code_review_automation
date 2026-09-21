"""add reviewer_id to platform_reviews

Revision ID: a1b2c3d4e5f6
Revises: e0afb9c97caa
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e0afb9c97caa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platform_reviews", sa.Column("reviewer_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_platform_reviews_reviewer_id_users",
        "platform_reviews", "users",
        ["reviewer_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_platform_reviews_reviewer_id_users", "platform_reviews", type_="foreignkey")
    op.drop_column("platform_reviews", "reviewer_id")
