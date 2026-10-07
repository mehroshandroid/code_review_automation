from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
import app.api.quarterly as quarterly_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


async def _review(session, review_id, project_id, platform, when, status="pending_approval"):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform=platform, status=status,
        project_name="P", created_at=when, completed_at=None, total_score_pct=1, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None, result_data={},
    )


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(quarterly_module, "new_session", lambda: maker())
    monkeypatch.setattr(projects_module, "new_session", lambda: maker())
    monkeypatch.setattr(quarterly_module, "_today", lambda: date(2026, 10, 7))
    async with maker() as s:
        for project in (await crud.create_project(s, "p1", "Alpha"), await crud.create_project(s, "p2", "Beta")):
            project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)  # tracked for all of 2026
        await s.commit()
        await crud.set_platforms_for_project(s, "p1", ["Android", "iOS"])
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await _review(s, "a2", "p1", "Android", datetime(2026, 5, 2, tzinfo=timezone.utc))
        await _review(s, "i2", "p1", "ios", datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc))
        await _review(s, "a3", "p1", "Android", datetime(2026, 8, 1, tzinfo=timezone.utc))
        await _review(s, "i3err", "p1", "iOS", datetime(2026, 8, 2, tzinfo=timezone.utc), status="error")
    yield maker
    await engine.dispose()


def _as(role, user_id="u1"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _quarters(body, project_id="p1"):
    project = next(p for p in body["projects"] if p["id"] == project_id)
    return {q["quarter"]: q for q in project["quarters"]}


def test_quarterly_statuses(db):
    _as("coordinator")
    body = client.get("/api/quarterly?year=2026").json()
    assert body["year"] == 2026 and body["today"] == "2026-10-07"
    assert [p["name"] for p in body["projects"]] == ["Alpha", "Beta"]
    quarters = _quarters(body)
    assert {q: e["status"] for q, e in quarters.items()} == {1: "overdue", 2: "done", 3: "overdue", 4: "not_started"}
    assert quarters[2]["start"] == "2026-04-01" and quarters[2]["end"] == "2026-06-30"
    assert quarters[3]["missing"] == ["iOS"]
    assert [c["review_id"] for c in quarters[3]["covered"]] == ["a3"]
    assert quarters[4]["can_initiate"] is True and quarters[2]["can_initiate"] is False


def test_coverage_ignores_errors_and_matches_platform_case(db):
    _as("coordinator")
    quarters = _quarters(client.get("/api/quarterly?year=2026").json())
    assert [c["platform"] for c in quarters[2]["covered"]] == ["Android", "iOS"]
    assert "iOS" in quarters[3]["missing"]


def test_project_without_platforms_has_no_quarters(db):
    _as("coordinator")
    beta = next(p for p in client.get("/api/quarterly?year=2026").json()["projects"] if p["id"] == "p2")
    assert beta["platforms"] == [] and beta["quarters"] == []


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_quarterly_forbidden(db, role):
    _as(role)
    assert client.get("/api/quarterly").status_code == 403


def test_initiate_cycle(db):
    _as("coordinator", "coord")
    response = client.post("/api/projects/p1/cycles", json={
        "year": 2026, "quarter": 4,
        "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}],
    })
    assert response.status_code == 200
    entry = response.json()
    assert entry["status"] == "in_progress" and entry["can_initiate"] is False
    assert entry["cycle"]["assignments"] == [
        {"platform": "Android", "reviewer_id": "rev", "reviewer_name": "Rae"},
        {"platform": "iOS", "reviewer_id": "rev", "reviewer_name": "Rae"},
    ]


def test_initiate_twice_conflicts(db):
    _as("coordinator", "coord")
    payload = {"year": 2026, "quarter": 3, "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}]}
    assert client.post("/api/projects/p1/cycles", json=payload).status_code == 200
    response = client.post("/api/projects/p1/cycles", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "This quarter's review has already been initiated."


def test_initiate_rejects_future_and_done_quarters(db):
    _as("coordinator", "coord")
    both = [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2027, "quarter": 1, "assignments": both}).status_code == 400
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 2, "assignments": both}).status_code == 400


def test_initiate_validation(db):
    _as("coordinator", "coord")
    android_only = [{"platform": "Android", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": android_only}).status_code == 400
    bad_reviewer = [{"platform": "Android", "reviewer_id": "pm"}, {"platform": "iOS", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": bad_reviewer}).status_code == 400
    assert client.post("/api/projects/p2/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 400
    assert client.post("/api/projects/nope/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 404


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_initiate_forbidden(db, role):
    _as(role)
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 403


def test_set_platforms(db):
    _as("coordinator")
    response = client.put("/api/projects/p2/platforms", json={"platforms": [".net", "Android"]})
    assert response.status_code == 200
    assert response.json()["platforms"] == ["Android", ".NET"]
    listed = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert listed["p2"]["platforms"] == ["Android", ".NET"]


def test_set_platforms_validation_and_permissions(db):
    _as("coordinator")
    assert client.put("/api/projects/p2/platforms", json={"platforms": ["Web (React)"]}).status_code == 400
    assert client.put("/api/projects/nope/platforms", json={"platforms": []}).status_code == 404
    _as("project_manager")
    assert client.put("/api/projects/p2/platforms", json={"platforms": ["iOS"]}).status_code == 403


async def test_reviews_older_than_the_project_record_are_tracked(db):
    # Projects created in the app after their history was uploaded: the first
    # review, not the record's created_at, marks when tracking starts.
    async with db() as s:
        project = await crud.create_project(s, "p3", "Gamma")
        project.created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
        await s.commit()
        await crud.set_platforms_for_project(s, "p3", ["Android"])
        await _review(s, "g2", "p3", "Android", datetime(2025, 5, 2, tzinfo=timezone.utc))
    _as("coordinator")
    quarters = _quarters(client.get("/api/quarterly?year=2025").json(), "p3")
    assert {q: e["status"] for q, e in quarters.items()} == {1: "not_applicable", 2: "done", 3: "overdue", 4: "overdue"}


def test_concurrent_initiate_loser_gets_409_not_500(db, monkeypatch):
    # Simulates a second coordinator creating the cycle after this request's
    # existence check passed: the DB unique constraint must surface as 409.
    real_create_cycle = crud.create_cycle

    async def racing_create_cycle(session, cycle_id, project_id, year, quarter, initiated_by, assignments):
        async with db() as other:
            await real_create_cycle(other, "winner", project_id, year, quarter, None, assignments)
        return await real_create_cycle(session, cycle_id, project_id, year, quarter, initiated_by, assignments)

    monkeypatch.setattr(quarterly_module.crud, "create_cycle", racing_create_cycle)
    _as("coordinator", "coord")
    response = client.post("/api/projects/p1/cycles", json={
        "year": 2026, "quarter": 4,
        "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}],
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "This quarter's review has already been initiated."
