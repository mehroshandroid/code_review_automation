from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.db import crud
from app.db.models import Base

NOW = datetime.now(timezone.utc)


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = async_sessionmaker(engine, expire_on_commit=False)
    m.engine = engine
    async with m() as s:
        await crud.create_user(s, "u1", "u1@example.com", "h", "reviewer")
    yield m
    await engine.dispose()


async def test_add_notifications_returns_rows_with_pending_status(maker):
    async with maker() as s:
        rows = await crud.add_notifications(s, "test_email", ["u1"], {"x": 1})
    assert len(rows) == 1 and rows[0].status == "pending" and rows[0].attempts == 0


async def test_due_and_recent_listing(maker):
    async with maker() as s:
        due, later, sent = [r for rows in [await crud.add_notifications(s, "e", ["u1"], {}) for _ in range(3)] for r in rows]
        await crud.update_notification(s, later, next_attempt_at=NOW + timedelta(minutes=5))
        await crud.update_notification(s, sent, status="sent")
        assert [r.id for r in await crud.list_due_notifications(s, NOW, 10)] == [due.id]
        assert len(await crud.list_recent_notifications(s, 2)) == 2
        assert (await crud.get_notification(s, due.id)).id == due.id


async def test_migration_sql_skips_existing_rows(maker):
    spec = importlib.util.spec_from_file_location(
        "mig", Path(__file__).parent.parent / "alembic/versions/a7b8c9d0e1f2_email_delivery_and_reminders.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with maker() as s:
        await crud.add_notifications(s, "old", ["u1"], {})
    async with maker.engine.begin() as conn:
        await conn.execute(text(module.SKIP_EXISTING_SQL))
    async with maker() as s:
        assert [r.status for r in await crud.list_recent_notifications(s, 10)] == ["skipped"]


async def test_assignment_dict_has_stage_timestamps(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "u1")])
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform="Android", status="approved", project_name="Alpha",
            created_at=NOW, completed_at=NOW, total_score_pct=90, llm_provider="azure", llm_model=None,
            compile_check_mode="compiler", source="devops", workbook_path=None, result_data={}, approved_at=NOW,
        )
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, url_submitted_at=NOW, review_id="r1", pm_reminded_at=NOW, run_status="completed")
        row = (await assignment_dicts(s, [a]))[0]
    assert row["url_submitted_at"] and row["review_approved_at"] and row["pm_reminded_at"]
    assert row["reviewer_reminded_at"] is None
