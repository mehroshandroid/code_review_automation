from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.email_admin as email_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
NOW = datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, email_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_project(s, "p1", "Alpha")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev"), (".NET", "rev")])
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform="iOS", status="pending_approval", project_name="Alpha",
            created_at=NOW, completed_at=NOW, total_score_pct=80, llm_provider="azure", llm_model=None,
            compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "iOS"), run_status="completed", review_id="r1")
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", ".NET"), run_status="failed", failure_kind="system")
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _remind(platform, target):
    return client.post(f"/api/cycles/c1/assignments/{platform}/remind", json={"target": target})


async def test_remind_rules(db):
    _as("coordinator", "co")
    body = _remind("Android", "pm").json()
    assert body["pm_reminded_at"] is not None
    assert _remind("iOS", "reviewer").json()["reviewer_reminded_at"] is not None
    for platform, target in (("Android", "reviewer"), ("iOS", "pm"), (".NET", "pm"), (".NET", "reviewer")):
        response = _remind(platform, target)
        assert response.status_code == 409 and response.json()["detail"] == "A reminder isn't needed at this stage."
    assert _remind("Android", "everyone").status_code == 400
    assert client.post("/api/cycles/c9/assignments/Android/remind", json={"target": "pm"}).status_code == 404
    async with db() as s:
        pm = await crud.list_notifications(s, "reminder_pm")
        reviewer = await crud.list_notifications(s, "reminder_reviewer")
    assert [n.recipient_user_id for n in pm] == ["pm"] and pm[0].payload["link"] == "/"
    assert [n.recipient_user_id for n in reviewer] == ["rev"] and reviewer[0].payload["link"] == "/reports/r1"


async def test_remind_pm_after_url_failure(db):
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="url")
    _as("coordinator", "co")
    assert _remind("Android", "pm").status_code == 200


def test_remind_permissions(db):
    _as("project_manager", "pm")
    assert _remind("Android", "pm").status_code == 403


def test_email_status_and_admin_only(db, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "log")
    _as("admin")
    assert client.get("/api/email/status").json()["mode"] == "log"
    _as("management", "m")
    assert client.get("/api/email/status").status_code == 403
    assert client.get("/api/email/outbox").status_code == 403


async def test_test_email_and_outbox_listing(db):
    _as("admin")
    row = client.post("/api/email/test").json()
    assert row["event"] == "test_email" and row["recipient_email"] == "adm@example.com" and row["status"] == "pending"
    listed = client.get("/api/email/outbox?limit=5").json()["emails"]
    assert listed[0]["id"] == row["id"] and listed[0]["recipient_name"] == "Ada"


async def test_retry_only_failed(db):
    _as("admin")
    row = client.post("/api/email/test").json()
    assert client.post(f"/api/email/outbox/{row['id']}/retry").status_code == 409
    async with db() as s:
        r = await crud.get_notification(s, row["id"])
        await crud.update_notification(s, r, status="failed", attempts=5, last_error="boom")
    body = client.post(f"/api/email/outbox/{row['id']}/retry").json()
    assert (body["status"], body["attempts"], body["last_error"]) == ("pending", 0, None)
    assert client.post("/api/email/outbox/nope/retry").status_code == 404
