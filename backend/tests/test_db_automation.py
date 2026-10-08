from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.automation.config import effective_compile_modes
from app.automation.notify import admin_ids, notify, project_manager_ids
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def s():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await crud.create_project(session, "p1", "Alpha")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(session, "adm", "adm@example.com", "h", "admin")
        await crud.create_user(session, "adm2", "adm2@example.com", "h", "admin")
        await crud.update_user(session, "adm2", is_active=False)
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.set_managers_for_project(session, "p1", ["pm"])
        await crud.create_cycle(session, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        yield session
    await engine.dispose()


async def test_new_assignments_wait_for_url(s):
    a = await crud.get_assignment(s, "c1", "Android")
    assert a.run_status == "waiting_for_url" and a.attempts == 0


async def test_queue_order_claim_and_requeue(s):
    now = datetime.now(timezone.utc)
    android = await crud.get_assignment(s, "c1", "Android")
    ios = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, ios, run_status="queued", queued_at=now)
    await crud.update_assignment(s, android, run_status="queued", queued_at=now + timedelta(seconds=1))
    assert await crud.list_queued_keys(s) == [("c1", "iOS"), ("c1", "Android")]
    claimed = await crud.claim_next_queued(s)
    assert (claimed.platform, claimed.run_status, claimed.attempts) == ("iOS", "running", 1)
    await crud.update_assignment(s, android, run_status="failed", failure_kind="url")
    assert await crud.requeue_assignments(s, include_running=True) == 1
    assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "queued"
    assert (await crud.get_assignment(s, "c1", "Android")).run_status == "failed"
    await crud.update_assignment(s, android, run_status="failed", failure_kind="system")
    assert await crud.requeue_assignments(s, include_running=False) == 1
    assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"


async def test_open_cycles_and_scope(s):
    assert [c.id for c in await crud.list_open_cycles(s, None)] == ["c1"]
    assert [c.id for c in await crud.list_open_cycles(s, {"p1"})] == ["c1"]
    assert await crud.list_open_cycles(s, set()) == []
    for platform in ("Android", "iOS"):
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", platform), run_status="completed")
    assert await crud.list_open_cycles(s, None) == []


async def test_notify_skips_inactive_and_duplicates(s):
    await notify(s, "review_failed", await admin_ids(s) + ["adm2", "adm", None], {"x": 1})
    rows = await crud.list_notifications(s, "review_failed")
    assert [(r.recipient_user_id, r.payload) for r in rows] == [("adm", {"x": 1})]
    assert await project_manager_ids(s, "p1") == ["pm"]


async def test_assignment_dicts(s):
    a = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, a, run_status="queued", queued_at=datetime.now(timezone.utc), devops_url="https://dev.azure.com/o/p/_git/r")
    rows = await assignment_dicts(s, [await crud.get_assignment(s, "c1", "iOS"), await crud.get_assignment(s, "c1", "Android")])
    assert [r["platform"] for r in rows] == ["Android", "iOS"]
    ios = rows[1]
    assert ios["queue_position"] == 1 and ios["reviewer_name"] == "Rae" and ios["devops_url"].endswith("/r")
    assert rows[0]["queue_position"] is None and rows[0]["review_status"] is None


async def test_org_automation_settings(s):
    settings = await crud.update_devops_pat(s, "enc", "abcd", "adm")
    assert (settings.devops_pat_encrypted, settings.devops_pat_last4, settings.devops_pat_updated_by) == ("enc", "abcd", "adm")
    settings = await crud.update_auto_compile_modes(s, {"iOS": "compiler"})
    assert effective_compile_modes(settings.auto_compile_modes) == {"Android": "compiler", ".NET": "compiler", "iOS": "compiler"}
    assert effective_compile_modes(None) == {"Android": "compiler", ".NET": "compiler", "iOS": "static"}
