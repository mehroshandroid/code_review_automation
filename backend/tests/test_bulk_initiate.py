from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.quarterly as quarterly_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(quarterly_module, "new_session", lambda: maker())
    monkeypatch.setattr(quarterly_module, "_today", lambda: date(2026, 10, 12))
    async with maker() as s:
        for user_id, role, name in (("rev", "reviewer", "Rae"), ("rev2", "reviewer", "Sam"), ("revoff", "reviewer", "Off"),
                                    ("pm", "project_manager", "Pat"), ("co", "coordinator", "Cora")):
            await crud.create_user(s, user_id, f"{user_id}@example.com", "h", role, name=name)
        await crud.update_user(s, "revoff", is_active=False)
        for project_id, name in (("p1", "Alpha"), ("p2", "Beta"), ("p3", "Gamma"), ("p4", "Delta")):
            project = await crud.create_project(s, project_id, name)
            project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        await s.commit()
        await crud.set_platforms_for_project(s, "p1", ["Android", "iOS"])
        await crud.set_platforms_for_project(s, "p3", ["Android"])
        await crud.set_platforms_for_project(s, "p4", ["Android", ".NET"])
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.set_managers_for_project(s, "p4", ["pm"])
        await crud.create_cycle(s, "g4", "p3", 2026, 4, "co", [("Android", "rev")])          # Gamma: already initiated
        await crud.create_cycle(s, "d3", "p4", 2026, 3, "co", [("Android", "rev2"), (".NET", "revoff")])  # Delta's last cycle
    yield maker
    await engine.dispose()


def _as(role, user_id="co"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _preview(quarter=4):
    return client.get(f"/api/quarterly/bulk-preview?year=2026&quarter={quarter}")


def test_preview_lists_eligible_and_skipped_with_reasons(db):
    _as("coordinator")
    body = _preview().json()
    assert [p["project_name"] for p in body["eligible"]] == ["Alpha", "Delta"]
    alpha = body["eligible"][0]
    assert alpha["platforms"] == ["Android", "iOS"] and alpha["managers"] == [{"id": "pm", "name": "Pat"}]
    assert {(p["project_name"], p["reason"]) for p in body["skipped"]} == {
        ("Beta", "No platforms set"), ("Gamma", "Already initiated"),
    }


def test_preview_prefills_reviewers_from_last_cycle_only_if_still_valid(db):
    _as("coordinator")
    eligible = {p["project_name"]: p for p in _preview().json()["eligible"]}
    assert eligible["Delta"]["suggested_reviewers"] == {"Android": "rev2", ".NET": None}  # revoff is inactive
    assert eligible["Alpha"]["suggested_reviewers"] == {"Android": None, "iOS": None}


def _bulk(projects, quarter=4):
    return client.post("/api/quarterly/bulk-initiate", json={"year": 2026, "quarter": quarter, "projects": projects})


ALPHA = {"project_id": "p1", "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}]}
DELTA = {"project_id": "p4", "assignments": [{"platform": "Android", "reviewer_id": "rev2"}, {"platform": ".NET", "reviewer_id": "rev"}]}


async def test_bulk_initiate_starts_projects_and_returns_results(db):
    _as("coordinator")
    results = _bulk([ALPHA, DELTA]).json()["results"]
    assert [(r["project_name"], r["status"]) for r in results] == [("Alpha", "started"), ("Delta", "started")]
    async with db() as s:
        assert await crud.get_cycle(s, "p1", 2026, 4) is not None
        assert (await crud.get_cycle(s, "p4", 2026, 4)).initiated_by == "co"


async def test_bulk_projects_succeed_or_fail_independently(db):
    _as("coordinator")
    gamma = {"project_id": "p3", "assignments": [{"platform": "Android", "reviewer_id": "rev"}]}
    bad_delta = {"project_id": "p4", "assignments": [{"platform": "Android", "reviewer_id": "revoff"}, {"platform": ".NET", "reviewer_id": "rev"}]}
    results = {r["project_name"]: r for r in _bulk([gamma, ALPHA, bad_delta]).json()["results"]}
    assert results["Alpha"]["status"] == "started"
    assert results["Gamma"] == {"project_id": "p3", "project_name": "Gamma", "status": "skipped",
                                "reason": "This quarter's review has already been initiated."}
    assert results["Delta"]["status"] == "skipped" and "active reviewer" in results["Delta"]["reason"]
    async with db() as s:
        assert await crud.get_cycle(s, "p4", 2026, 4) is None


async def test_bulk_sends_one_digest_per_pm_and_reviewer(db):
    _as("coordinator")
    _bulk([ALPHA, DELTA])
    async with db() as s:
        rows = await crud.list_notifications(s)
    events = sorted((n.event, n.recipient_user_id) for n in rows)
    assert events == [
        ("cycles_initiated_digest", "pm"),
        ("reviewer_assigned_digest", "rev"),
        ("reviewer_assigned_digest", "rev2"),
    ]
    pm_digest = next(n for n in rows if n.event == "cycles_initiated_digest")
    assert pm_digest.payload == {"year": 2026, "quarter": 4, "projects": ["Alpha", "Delta"], "link": "/"}
    rev_digest = next(n for n in rows if n.recipient_user_id == "rev")
    assert rev_digest.payload["assignments"] == [
        {"project_name": "Alpha", "platform": "Android"}, {"project_name": "Alpha", "platform": "iOS"},
        {"project_name": "Delta", "platform": ".NET"},
    ]


def test_bulk_is_forbidden_without_cycles_initiate(db):
    _as("project_manager", "pm")
    assert _preview().status_code == 403
    assert _bulk([ALPHA]).status_code == 403


def test_bad_quarter_is_400(db):
    _as("coordinator")
    assert _preview(quarter=5).status_code == 400
    assert _bulk([ALPHA], quarter=0).status_code == 400
