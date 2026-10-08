from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.queue as queue_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"
NOW = datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(queue_module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_project(s, "p1", "Alpha")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.update_org_settings(s, "azure", None)
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None), (".NET", None)])
        await crud.create_cycle(s, "c2", "p1", 2026, 3, None, [("Android", None)])
        rows = {
            ("c1", "Android"): dict(run_status="running", started_at=NOW, run_phase="scoring", run_progress=40),
            ("c1", "iOS"): dict(run_status="queued", queued_at=NOW, devops_url=URL),
            ("c1", ".NET"): dict(run_status="queued", queued_at=NOW + timedelta(minutes=1), devops_url=URL),
            ("c2", "Android"): dict(run_status="failed", failure_kind="url", run_error="nope", finished_at=NOW),
        }
        for (cycle_id, platform), fields in rows.items():
            await crud.update_assignment(s, await crud.get_assignment(s, cycle_id, platform), **fields)
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_snapshot(db):
    _as("admin")
    body = client.get("/api/queue").json()
    assert body["paused"] is False and body["waiting_for_url"] == 0
    assert [(i["platform"], i["queue_position"]) for i in body["queued"]] == [("iOS", 1), (".NET", 2)]
    assert body["running"][0]["project_name"] == "Alpha" and body["running"][0]["quarter"] == 4
    assert body["failed"][0]["cycle_id"] == "c2" and body["completed"] == []
    assert body["defaults"] == {"llm_provider": "azure", "llm_model": None,
                                "compile_modes": {"Android": "compiler", ".NET": "compiler", "iOS": "static"}}


async def test_pause_requests_cancel_of_running_and_resume(db):
    _as("admin")
    body = client.post("/api/queue/pause").json()
    assert body["paused"] is True and body["paused_by_name"] == "Ada"
    assert body["running"][0]["cancel_requested"] == "pause"
    assert client.post("/api/queue/resume").json()["paused"] is False


def test_stop_only_running(db):
    _as("admin")
    assert client.post("/api/queue/items/c1/Android/stop").json()["cancel_requested"] == "stop"
    response = client.post("/api/queue/items/c1/iOS/stop")
    assert response.status_code == 409 and response.json()["detail"] == "Only a running review can be stopped."


async def test_remove_notifies_pms(db):
    _as("admin")
    body = client.post("/api/queue/items/c1/iOS/remove").json()
    assert body["run_status"] == "waiting_for_url" and body["devops_url"] == URL and body["queued_at"] is None
    assert client.post("/api/queue/items/c1/Android/remove").status_code == 409
    async with db() as s:
        rows = await crud.list_notifications(s, "review_removed_from_queue")
    assert [n.recipient_user_id for n in rows] == ["pm"] and rows[0].payload["platform"] == "iOS"


def test_front_moves_item_first(db):
    _as("admin")
    client.post("/api/queue/items/c1/.NET/front")
    assert [i["platform"] for i in client.get("/api/queue").json()["queued"]] == [".NET", "iOS"]
    client.post("/api/queue/items/c1/.NET/front")
    assert [i["platform"] for i in client.get("/api/queue").json()["queued"]] == [".NET", "iOS"]
    assert client.post("/api/queue/items/c2/Android/front").status_code == 409


def test_run_settings(db):
    _as("admin")
    body = client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": "ollama", "llm_model": " qwen ", "compile_mode": "compiler"}).json()
    assert (body["override_llm_provider"], body["override_llm_model"], body["override_compile_mode"]) == ("ollama", "qwen", "compiler")
    cleared = client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": None, "llm_model": "x", "compile_mode": None}).json()
    assert (cleared["override_llm_provider"], cleared["override_llm_model"], cleared["override_compile_mode"]) == (None, None, None)
    assert client.put("/api/queue/items/c2/Android/settings", json={"compile_mode": "local"}).status_code == 200
    assert client.put("/api/queue/items/c1/Android/settings", json={}).status_code == 409
    assert client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": "gpt"}).status_code == 400
    assert client.put("/api/queue/items/c1/iOS/settings", json={"compile_mode": "local"}).status_code == 400
    assert client.put("/api/queue/items/c9/iOS/settings", json={}).status_code == 404


@pytest.mark.parametrize("role", ["management", "coordinator", "project_manager"])
def test_queue_is_admin_only(db, role):
    _as(role, "x")
    assert client.get("/api/queue").status_code == 403
    assert client.post("/api/queue/pause").status_code == 403
    assert client.post("/api/queue/items/c1/iOS/front").status_code == 403


def test_pause_does_not_override_an_earlier_stop(db):
    _as("admin")
    client.post("/api/queue/items/c1/Android/stop")
    body = client.post("/api/queue/pause").json()
    assert body["running"][0]["cancel_requested"] == "stop"
