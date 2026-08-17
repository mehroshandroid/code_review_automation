"""seed default org settings and the existing dotnet 2.4 checklist

Revision ID: d88bf1c5135c
Revises: 35a49ddb7794
Create Date: 2026-08-07 21:04:23.525836

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd88bf1c5135c'
down_revision: Union[str, None] = '35a49ddb7794'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Preserves the exact wording that lived in CLAUSE_CHECKLISTS[(".NET", "2.4")]
# in llm_prompts.py before this phase moved it into the DB, so behavior
# doesn't change until someone edits it via the new settings page.
DOTNET_2_4_CHECKLIST = (
    "(1) every controller action that should require authentication has an "
    "[Authorize] attribute -- flag any [AllowAnonymous] or missing [Authorize] "
    "on an endpoint that looks like it handles user/account/payment data; "
    "(2) JWT bearer configuration (AddJwtBearer/TokenValidationParameters) "
    "explicitly sets ValidateAudience=true and ValidateIssuer=true with real, "
    "non-default expected values; (3) UseAuthentication/UseAuthorization "
    "middleware is registered, in the correct order, in Program.cs/Startup.cs."
)

org_settings = sa.table(
    "org_settings",
    sa.column("id", sa.Integer),
    sa.column("default_llm_provider", sa.String),
    sa.column("default_ollama_model", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

clause_checklists = sa.table(
    "clause_checklists",
    sa.column("id", sa.String),
    sa.column("platform", sa.String),
    sa.column("sub_id", sa.String),
    sa.column("checklist_text", sa.String),
)


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        org_settings,
        [{"id": 1, "default_llm_provider": "ollama", "default_ollama_model": None, "updated_at": now}],
    )
    op.bulk_insert(
        clause_checklists,
        [{"id": str(uuid.uuid4()), "platform": ".NET", "sub_id": "2.4", "checklist_text": DOTNET_2_4_CHECKLIST}],
    )


def downgrade() -> None:
    op.execute(org_settings.delete().where(org_settings.c.id == 1))
    op.execute(clause_checklists.delete().where(clause_checklists.c.platform == ".NET", clause_checklists.c.sub_id == "2.4"))
