from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.quarterly as quarterly_module
import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, quarterly_module, reviews_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        for user_id, role in (("rev", "reviewer"), ("rev2", "reviewer"), ("pm", "project_manager"), ("pm2", "project_manager"), ("adm", "admin")):
            await crud.create_user(s, user_id, f"{user_id}@example.com", "h", role)
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_project(s, "p2", "Beta")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.set_managers_for_project(s, "p2", ["pm2"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        await crud.create_cycle(s, "c2", "p2", 2026, 4, None, [("Android", "rev")])
    yield maker
    await engine.dispose()


def _as(role, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


async def _complete(maker, platform="Android", review_status="pending_approval"):
    async with maker() as s:
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform=platform, status=review_status, project_name="Alpha",
            created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=80, llm_provider="azure",
            llm_model=None, compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        await crud.set_review_reviewer(s, "r1", "rev")
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="completed", review_id="r1", devops_url=URL)


def test_my_cycles_scoped_to_pm(db):
    _as("project_manager", "pm")
    cycles = client.get("/api/my/cycles").json()["cycles"]
    assert [c["id"] for c in cycles] == ["c1"]
    assert cycles[0]["project_name"] == "Alpha" and cycles[0]["quarter"] == 4
    assert [a["platform"] for a in cycles[0]["assignments"]] == ["Android", "iOS"]
    assert cycles[0]["assignments"][0]["run_status"] == "waiting_for_url"
    _as("coordinator", "co")
    assert {c["id"] for c in client.get("/api/my/cycles").json()["cycles"]} == {"c1", "c2"}
    _as("reviewer", "rev")
    assert client.get("/api/my/cycles").status_code == 403


def test_submit_url_queues(db):
    _as("project_manager", "pm")
    response = client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL, "devops_branch": "develop"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_status"] == "queued" and body["queue_position"] == 1 and body["devops_branch"] == "develop"
    second = client.put("/api/cycles/c1/assignments/iOS/url", json={"devops_url": URL}).json()
    assert second["queue_position"] == 2 and second["devops_branch"] is None
    assert client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL}).status_code == 409


def test_submit_url_validation(db):
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": "https://github.com/x/y"}).status_code == 400
    assert client.put("/api/cycles/c1/assignments/.NET/url", json={"devops_url": URL}).status_code == 404
    assert client.put("/api/cycles/nope/assignments/Android/url", json={"devops_url": URL}).status_code == 404


def test_pm_cannot_touch_other_projects_cycles(db):
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c2/assignments/Android/url", json={"devops_url": URL}).status_code == 404
    assert client.post("/api/cycles/c2/assignments/Android/retry").status_code == 404


async def test_retry_only_when_failed(db):
    _as("project_manager", "pm")
    assert client.post("/api/cycles/c1/assignments/Android/retry").status_code == 409
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="failed", failure_kind="url", run_error="Repository or branch not found.", devops_url=URL)
    body = client.post("/api/cycles/c1/assignments/Android/retry").json()
    assert body["run_status"] == "queued" and body["run_error"] is None
    fixed = None
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="failed", failure_kind="url")
    fixed = client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL + "2"}).json()
    assert fixed["run_status"] == "queued" and fixed["devops_url"] == URL + "2"


async def test_rerun_rules(db):
    _as("project_manager", "pm")
    await _complete(db)
    assert client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL}).status_code == 403
    _as("coordinator", "co")
    body = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL + "-fixed"}).json()
    assert body["run_status"] == "queued" and body["devops_url"] == URL + "-fixed"
    assert client.post("/api/cycles/c1/assignments/iOS/rerun", json={"devops_url": URL}).status_code == 409


async def test_rerun_blocked_after_approval(db):
    await _complete(db, review_status="approved")
    _as("coordinator", "co")
    response = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL})
    assert response.status_code == 409


async def test_reviewer_change_moves_finished_review_and_notifies(db):
    await _complete(db)
    _as("coordinator", "co")
    body = client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev2"}).json()
    assert body["reviewer_id"] == "rev2"
    async with db() as s:
        assert (await crud.get_review_by_id(s, "r1")).reviewer_id == "rev2"
        assigned = await crud.list_notifications(s, "reviewer_assigned")
        unassigned = await crud.list_notifications(s, "reviewer_unassigned")
        a = await crud.get_assignment(s, "c1", "Android")
    assert [n.recipient_user_id for n in assigned] == ["rev2"] and assigned[0].payload["link"] == "/reports/r1"
    assert [n.recipient_user_id for n in unassigned] == ["rev"]
    assert a.reviewer_assigned_by == "co" and a.reviewer_assigned_at is not None


async def test_reviewer_change_to_same_reviewer_is_a_noop(db):
    _as("coordinator", "co")
    client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev"})
    async with db() as s:
        assert await crud.list_notifications(s) == []


async def test_reviewer_change_blocked_after_approval(db):
    await _complete(db, review_status="approved")
    _as("coordinator", "co")
    response = client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev2"})
    assert response.status_code == 409
    assert client.put("/api/cycles/c1/assignments/iOS/reviewer", json={"reviewer_id": "pm"}).status_code == 400
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c1/assignments/iOS/reviewer", json={"reviewer_id": "rev2"}).status_code == 403


async def test_initiation_records_notifications(db, monkeypatch):
    from datetime import date
    monkeypatch.setattr(quarterly_module, "_today", lambda: date(2026, 10, 7))
    async with db() as s:
        project = await crud.get_project(s, "p2")
        project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        await s.commit()
        await crud.set_platforms_for_project(s, "p2", ["Android"])
    _as("coordinator", "co")
    response = client.post("/api/projects/p2/cycles", json={"year": 2026, "quarter": 3, "assignments": [{"platform": "Android", "reviewer_id": "rev2"}]})
    assert response.status_code == 200
    assert response.json()["cycle"]["assignments"][0]["run_status"] == "waiting_for_url"
    async with db() as s:
        initiated = await crud.list_notifications(s, "cycle_initiated")
        assigned = await crud.list_notifications(s, "reviewer_assigned")
    assert [n.recipient_user_id for n in initiated] == ["pm2"]
    assert initiated[0].payload == {"project_name": "Beta", "platform": None, "year": 2026, "quarter": 3, "link": "/"}
    assert [n.recipient_user_id for n in assigned] == ["rev2"]


async def test_approving_a_cycle_review_notifies_pms(db):
    await _complete(db)
    _as("reviewer", "rev")
    assert client.patch("/api/reviews/r1", json={"status": "approved"}).status_code == 200
    async with db() as s:
        finalized = await crud.list_notifications(s, "review_finalized")
    assert [n.recipient_user_id for n in finalized] == ["pm"]
    assert finalized[0].payload["review_id"] == "r1" and finalized[0].payload["link"] == "/reports/r1"


async def test_report_page_reviewer_change_on_a_cycle_review_follows_cycle_rules(db):
    # The older PATCH /api/reviews/{id}/reviewer (report page) must keep the
    # cycle assignment in sync and notify, exactly like the cycle endpoint.
    await _complete(db)
    _as("coordinator", "co")
    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "rev2"})
    assert response.status_code == 200
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        assigned = await crud.list_notifications(s, "reviewer_assigned")
    assert a.reviewer_id == "rev2" and a.reviewer_assigned_by == "co"
    assert [n.recipient_user_id for n in assigned] == ["rev2"]


async def test_report_page_reviewer_change_blocked_after_cycle_review_approved(db):
    await _complete(db, review_status="approved")
    _as("coordinator", "co")
    assert client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "rev2"}).status_code == 409


async def test_rerun_keeps_the_branch_unless_a_new_one_is_given(db):
    await _complete(db)
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, devops_branch="release/2026Q4")
    _as("coordinator", "co")
    kept = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL + "-fixed"}).json()
    assert kept["devops_branch"] == "release/2026Q4"
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="completed")
    changed = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL, "devops_branch": "main"}).json()
    assert changed["devops_branch"] == "main"


async def test_old_review_cannot_be_approved_while_its_rerun_is_pending(db):
    await _complete(db)
    _as("coordinator", "co")
    client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL})
    _as("reviewer", "rev")
    response = client.patch("/api/reviews/r1", json={"status": "approved"})
    assert response.status_code == 409
    async with db() as s:
        assert await crud.list_notifications(s, "review_finalized") == []
