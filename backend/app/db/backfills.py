"""Data backfills shared by Alembic migrations and their tests (sync connections)."""
from sqlalchemy import text

from app.quarterly import canonical_platform


def backfill_project_platforms(connection) -> None:
    """Give each project the tracked platforms it has already been reviewed on."""
    rows = connection.execute(text(
        "SELECT DISTINCT project_id, platform FROM platform_reviews "
        "WHERE project_id IS NOT NULL AND status <> 'error'"
    )).all()
    pairs = {(project_id, canonical_platform(platform)) for project_id, platform in rows}
    for project_id, platform in sorted(p for p in pairs if p[1] is not None):
        connection.execute(
            text("INSERT INTO project_platforms (project_id, platform) VALUES (:project_id, :platform)"),
            {"project_id": project_id, "platform": platform},
        )
