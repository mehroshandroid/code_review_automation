from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.backfills import backfill_project_platforms
from app.db.models import Base


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    sessionmaker.engine = engine
    yield sessionmaker
    await engine.dispose()


async def _review(session, review_id, project_id, platform, status="pending_approval", when=datetime(2026, 5, 1, tzinfo=timezone.utc)):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform=platform, status=status,
        project_name="P", created_at=when, completed_at=None, total_score_pct=1, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None, result_data={},
    )


async def test_platforms_roundtrip(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.create_project(s, "p2", "Two")
        await crud.set_platforms_for_project(s, "p1", [".NET", "Android", "Android"])
        assert await crud.get_platforms_for_projects(s, ["p1", "p2"]) == {"p1": ["Android", ".NET"], "p2": []}
        await crud.set_platforms_for_project(s, "p1", ["iOS"])
        assert (await crud.get_platforms_for_projects(s, ["p1"]))["p1"] == ["iOS"]


async def test_backfill_from_non_errored_reviews(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await _review(s, "r1", "p1", "android")
        await _review(s, "r2", "p1", "Android")
        await _review(s, "r3", "p1", "iOS", status="error")
        await _review(s, "r4", "p1", "Web (React)")
        await _review(s, "r5", None, ".NET")
    async with maker.engine.begin() as conn:
        await conn.run_sync(backfill_project_platforms)
    async with maker() as s:
        assert await crud.get_platforms_for_projects(s, ["p1"]) == {"p1": ["Android"]}


async def test_create_and_read_cycle(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        cycle = await crud.create_cycle(s, "c1", "p1", 2026, 4, "rev", [("Android", "rev")])
        assert cycle.initiated_at is not None
        assert (await crud.get_cycle(s, "p1", 2026, 4)).id == "c1"
        assert await crud.get_cycle(s, "p1", 2026, 3) is None
        assert [c.id for c in await crud.list_cycles_for_projects_in_year(s, ["p1"], 2026)] == ["c1"]
        assignments = await crud.get_cycle_assignments(s, ["c1"])
        assert [(a.platform, a.reviewer_id) for a in assignments["c1"]] == [("Android", "rev")]
        assert (await crud.get_users_by_ids(s, ["rev", "ghost"]))["rev"].name == "Rae"


async def test_delete_project_removes_platforms_and_cycles(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.set_platforms_for_project(s, "p1", ["Android"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None)])
        assert await crud.delete_project(s, "p1") is True
        assert await crud.get_cycle(s, "p1", 2026, 4) is None
        assert await crud.get_platforms_for_projects(s, ["p1"]) == {"p1": []}
        assert await crud.get_cycle_assignments(s, ["c1"]) == {"c1": []}


async def test_coverage_rows_are_lightweight_and_exclude_errors(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await _review(s, "r1", "p1", "Android")
        await _review(s, "r2", "p1", "iOS", status="error")
        await _review(s, "r3", "p1", "Android", when=datetime(2025, 5, 1, tzinfo=timezone.utc))
        rows = await crud.list_review_coverage_rows(s, ["p1"], 2026)
    assert [(r.id, r.project_id, r.platform) for r in rows] == [("r1", "p1", "Android")]
    assert set(rows[0]._fields) == {"id", "project_id", "platform", "created_at"}
