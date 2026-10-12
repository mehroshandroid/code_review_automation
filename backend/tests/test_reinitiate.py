from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.quarterly as quarterly_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, ReviewCycleRound, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"
APPROVED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, quarterly_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        for user_id, role, name in (("rev", "reviewer", "Rae"), ("rev2", "reviewer", "Sam"), ("pm", "project_manager", "Pat"), ("off", "reviewer", "Off")):
            await crud.create_user(s, user_id, f"{user_id}@example.com", "h", role, name=name)
        await crud.update_user(s, "off", is_active=False)
        project = await crud.create_project(s, "p1", "Alpha")
        project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        await s.commit()
        await crud.set_platforms_for_project(s, "p1", ["Android", "iOS"])
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
    yield maker
    await engine.dispose()


def _as(role, user_id="co"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


async def _finish(maker, review_id, status="approved", when=None, **assignment_fields):
    async with maker() as s:
        await crud.persist_review_result(
            s, review_id=review_id, project_id="p1", platform="Android", status=status, project_name="Alpha",
            created_at=when or datetime(2026, 10, 3, tzinfo=timezone.utc), completed_at=None, total_score_pct=80,
            llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        review = await crud.get_review_by_id(s, review_id)
        review.approved_at = APPROVED_AT if status == "approved" else None
        await s.commit()
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="completed", review_id=review_id, devops_url=URL, **assignment_fields)


def _reinit(reviewer_id="rev2", platform="Android"):
    return client.post(f"/api/cycles/c1/assignments/{platform}/reinitiate", json={"reviewer_id": reviewer_id})


async def test_only_an_approved_review_can_be_reinitiated(db):
    _as("coordinator")
    assert _reinit().status_code == 409  # waiting for a URL
    await _finish(db, "r1", status="pending_approval")
    response = _reinit()
    assert response.status_code == 409 and response.json()["detail"] == "Only an approved review can be reinitiated."


async def test_reinitiate_archives_the_round_and_resets_the_platform(db, monkeypatch):
    deleted = []
    monkeypatch.setattr(cycles_module, "delete_zip", lambda path: deleted.append(path))
    await _finish(db, "r1", source_type="zip", source_zip_path="/uploads/c1/a.zip", source_zip_name="a.zip",
                  devops_branch="main", attempts=2, run_phase="done", run_progress=100,
                  started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                  pm_reminded_at=datetime.now(timezone.utc), reviewer_reminded_at=datetime.now(timezone.utc),
                  override_llm_provider="claude", override_compile_mode="skip")
    _as("coordinator")
    response = _reinit()
    assert response.status_code == 200
    body = response.json()
    assert body["round"] == 2 and body["reviewer_id"] == "rev2" and body["run_status"] == "waiting_for_url"
    assert body["approved_rounds"] == 1 and body["can_reinitiate"] is False
    (archived,) = body["history"]
    assert {k: archived[k] for k in ("round", "review_id", "reviewer_name")} == {"round": 1, "review_id": "r1", "reviewer_name": "Rae"}
    assert archived["approved_at"].startswith("2026-10-05T12:00:00")  # SQLite drops the zone
    for field in ("devops_url", "devops_branch", "review_id", "review_status", "run_phase", "run_progress", "run_error",
                  "failure_kind", "queued_at", "started_at", "finished_at", "source_type", "source_zip_name",
                  "pm_reminded_at", "reviewer_reminded_at", "url_submitted_at", "cancel_requested",
                  "override_llm_provider", "override_llm_model", "override_compile_mode"):
        assert body[field] is None, field
    assert body["attempts"] == 0
    assert deleted == ["/uploads/c1/a.zip"]
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        assert a.source_zip_path is None and a.reviewer_assigned_by == "co"
        rounds = await crud.list_rounds(s, ["c1"])
        assert [(r.platform, r.round, r.review_id, r.reviewer_id, r.archived_by) for r in rounds] == [("Android", 1, "r1", "rev", "co")]
        pm_mail = await crud.list_notifications(s, "cycle_reinitiated")
        rev_mail = await crud.list_notifications(s, "reviewer_assigned")
    assert [n.recipient_user_id for n in pm_mail] == ["pm"]
    assert pm_mail[0].payload["round"] == 2 and pm_mail[0].payload["platform"] == "Android"
    assert [(n.recipient_user_id, n.payload["round"]) for n in rev_mail] == [("rev2", 2)]


async def test_reinitiate_validation_and_permissions(db):
    await _finish(db, "r1")
    _as("coordinator")
    assert _reinit(reviewer_id="off").status_code == 400
    assert _reinit(reviewer_id="pm").status_code == 400
    assert client.post("/api/cycles/c1/assignments/.NET/reinitiate", json={"reviewer_id": "rev"}).status_code == 404
    _as("project_manager", "pm")
    assert _reinit().status_code == 403
    _as("reviewer", "rev")
    assert _reinit().status_code == 403


def _q4():
    project = client.get("/api/quarterly?year=2026").json()["projects"][0]
    return project["quarters"][3]


async def test_round_one_keeps_covering_the_quarter_and_the_newest_review_wins(db):
    await _finish(db, "r1")
    _as("coordinator")
    assert _reinit().status_code == 200
    q4 = _q4()
    assert {c["platform"]: c["review_id"] for c in q4["covered"]} == {"Android": "r1"}
    android = next(a for a in q4["cycle"]["assignments"] if a["platform"] == "Android")
    assert android["round"] == 2 and android["approved_rounds"] == 1

    await _finish(db, "r2", when=datetime(2026, 10, 9, tzinfo=timezone.utc))
    q4 = _q4()
    assert {c["platform"]: c["review_id"] for c in q4["covered"]} == {"Android": "r2"}
    android = next(a for a in q4["cycle"]["assignments"] if a["platform"] == "Android")
    assert android["approved_rounds"] == 2 and android["can_reinitiate"] is True
    async with db() as s:
        assert await crud.list_cycle_review_ids(s, ["p1"]) == {"r1", "r2"}


async def test_round_reviews_dated_in_another_quarter_count_for_the_cycle(db):
    # A round-1 review run late (January) still counts for Q4, not Q1 of the next year.
    await _finish(db, "r1", when=datetime(2027, 1, 10, tzinfo=timezone.utc))
    _as("coordinator")
    assert _reinit().status_code == 200
    async with db() as s:
        assert "r1" in await crud.list_cycle_review_ids(s, ["p1"])


async def test_deleting_the_project_removes_its_rounds(db):
    await _finish(db, "r1")
    _as("coordinator")
    assert _reinit().status_code == 200
    async with db() as s:
        await crud.delete_project(s, "p1")
        assert (await s.execute(select(func.count()).select_from(ReviewCycleRound))).scalar_one() == 0
