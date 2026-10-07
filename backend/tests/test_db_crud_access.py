from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.models import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def _review(session, review_id, project_id, reviewer_id=None, year=2026):
    review = await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform="Android",
        status="pending_approval", project_name="P",
        created_at=datetime(year, 3, 1, tzinfo=timezone.utc), completed_at=None,
        total_score_pct=50, llm_provider="azure", llm_model=None, compile_check_mode="compiler",
        source="upload", workbook_path=None, result_data={},
    )
    if reviewer_id:
        await crud.set_review_reviewer(session, review_id, reviewer_id)
    return review


async def _seed(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_project(session, "p2", "Two")
    await crud.create_user(session, "pm1", "pm1@example.com", "h", "project_manager", name="Pat Manager")
    await crud.create_user(session, "pm2", "pm2@example.com", "h", "project_manager")


async def test_create_user_stores_name(session):
    await _seed(session)
    assert (await crud.get_user_by_id(session, "pm1")).name == "Pat Manager"


async def test_update_user_name_and_clear(session):
    await _seed(session)
    await crud.update_user(session, "pm2", name="  Sam  ")
    assert (await crud.get_user_by_id(session, "pm2")).name == "Sam"
    await crud.update_user(session, "pm2", name="")
    assert (await crud.get_user_by_id(session, "pm2")).name is None


async def test_set_managers_replaces_the_set(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1", "pm2"])
    await crud.set_managers_for_project(session, "p1", ["pm2"])
    assert await crud.get_manager_ids_for_projects(session, ["p1", "p2"]) == {"p1": ["pm2"], "p2": []}
    assert await crud.get_project_ids_for_manager(session, "pm2") == {"p1"}
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()


async def test_get_project_ids_for_managers_bulk(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1"])
    await crud.set_managers_for_project(session, "p2", ["pm1"])
    assert await crud.get_project_ids_for_managers(session, ["pm1", "pm2"]) == {"pm1": ["p1", "p2"], "pm2": []}


async def test_clear_projects_for_manager(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1"])
    await crud.clear_projects_for_manager(session, "pm1")
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()


async def test_list_projects_scoped(session):
    await _seed(session)
    assert {p.id for p in await crud.list_projects(session, project_ids={"p2"})} == {"p2"}
    assert await crud.list_projects(session, project_ids=set()) == []
    assert len(await crud.list_projects(session)) == 2


async def test_list_reviews_and_years_scoped(session):
    await _seed(session)
    await _review(session, "r1", "p1", year=2025)
    await _review(session, "r2", "p2", year=2026)
    await _review(session, "r3", None, year=2026)
    assert [r.id for r in await crud.list_reviews(session, year=2026, project_ids={"p2"})] == ["r2"]
    assert await crud.list_reviews(session, year=2026, project_ids=set()) == []
    assert {r.id for r in await crud.list_reviews(session, year=2026)} == {"r2", "r3"}
    assert await crud.list_review_years(session, project_ids={"p1"}) == [2025]
    assert await crud.list_review_years(session, project_ids=set()) == []


async def test_list_reviews_for_reviewer(session):
    await _seed(session)
    await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer")
    await _review(session, "r1", "p1", reviewer_id="rev")
    await _review(session, "r2", "p2")
    assert [r.id for r in await crud.list_reviews_for_reviewer(session, "rev")] == ["r1"]


async def test_review_counts_and_delete_project(session):
    await _seed(session)
    await _review(session, "r1", "p1")
    await crud.set_managers_for_project(session, "p2", ["pm1"])
    assert await crud.count_reviews_by_project(session) == {"p1": 1}
    assert await crud.count_reviews_for_project(session, "p1") == 1
    assert await crud.delete_project(session, "p2") is True
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()
    assert await crud.delete_project(session, "nope") is False


async def test_list_reviewer_candidates_by_roles(session):
    await _seed(session)
    await crud.create_user(session, "m1", "m@example.com", "h", "management")
    await crud.create_user(session, "c1", "c@example.com", "h", "coordinator")
    candidates = await crud.list_reviewer_candidates(session, frozenset({"management", "reviewer", "admin"}))
    assert [u.id for u in candidates] == ["m1"]
