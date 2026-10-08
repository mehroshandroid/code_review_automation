from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def s():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await crud.create_user(session, "adm", "adm@example.com", "h", "admin")
        await crud.create_project(session, "p1", "Alpha")
        await crud.create_cycle(session, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None), (".NET", None)])
        yield session
    await engine.dispose()


async def test_queue_state_defaults_and_pause(s):
    state = await crud.get_queue_state(s)
    assert state.paused is False and state.paused_by is None
    state = await crud.set_queue_paused(s, True, "adm")
    assert state.paused is True and state.paused_by == "adm" and state.paused_at is not None
    state = await crud.set_queue_paused(s, False, "adm")
    assert state.paused is False and state.paused_by is None and state.paused_at is None


async def test_list_count_and_front(s):
    now = datetime.now(timezone.utc)
    for platform, offset in (("Android", 2), ("iOS", 1)):
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="queued", queued_at=now + timedelta(minutes=offset))
    queued = await crud.list_assignments_with_status(s, "queued")
    assert [a.platform for a in queued] == ["iOS", "Android"]
    assert await crud.count_assignments_with_status(s, "waiting_for_url") == 1
    front = await crud.front_of_queue_time(s)
    android = await crud.get_assignment(s, "c1", "Android")
    await crud.update_assignment(s, android, queued_at=front)
    assert [a.platform for a in await crud.list_assignments_with_status(s, "queued")] == ["Android", "iOS"]


async def test_failed_newest_first_with_limit(s):
    now = datetime.now(timezone.utc)
    for platform, offset in (("Android", 1), ("iOS", 3), (".NET", 2)):
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="failed", finished_at=now + timedelta(minutes=offset))
    rows = await crud.list_assignments_with_status(s, "failed", newest_finished_first=True, limit=2)
    assert [a.platform for a in rows] == ["iOS", ".NET"]


async def test_requeue_clears_cancel_requested_and_skips_stopped(s):
    android = await crud.get_assignment(s, "c1", "Android")
    ios = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, android, run_status="running", cancel_requested="stop")
    await crud.update_assignment(s, ios, run_status="failed", failure_kind="stopped")
    assert await crud.requeue_assignments(s, include_running=True) == 1
    android = await crud.get_assignment(s, "c1", "Android")
    assert android.run_status == "queued" and android.cancel_requested is None
    assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"


async def test_assignment_dicts_keep_order_and_new_fields(s):
    android = await crud.get_assignment(s, "c1", "Android")
    await crud.update_assignment(s, android, override_llm_provider="claude", override_compile_mode="static")
    ios = await crud.get_assignment(s, "c1", "iOS")
    rows = await assignment_dicts(s, [ios, android], keep_order=True)
    assert [r["platform"] for r in rows] == ["iOS", "Android"]
    assert rows[1]["override_llm_provider"] == "claude" and rows[1]["override_compile_mode"] == "static"
    assert rows[0]["cycle_id"] == "c1" and rows[0]["cancel_requested"] is None
    assert [r["platform"] for r in await assignment_dicts(s, [ios, android])] == ["Android", "iOS"]
