from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


async def _review(session, review_id, project_id, reviewer_id=None):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform="Android", status="pending_approval",
        project_name="P", created_at=NOW, completed_at=NOW, total_score_pct=50, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None,
        result_data={"category_scores": []},
    )
    if reviewer_id:
        await crud.set_review_reviewer(session, review_id, reviewer_id)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    async with sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_project(session, "p2", "Two")
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(session, "mgmt", "mgmt@example.com", "h", "management")
        await crud.create_user(session, "coord", "coord@example.com", "h", "coordinator")
        await crud.set_managers_for_project(session, "p1", ["pm"])
        await _review(session, "in-scope", "p1")
        await _review(session, "out-scope", "p2", reviewer_id="rev")
        await _review(session, "unlinked", None, reviewer_id="rev")
    yield sessionmaker
    await engine.dispose()


def _as(role, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_pm_lists_only_assigned_reviews(db):
    _as("project_manager", "pm")
    assert [r["id"] for r in client.get("/api/reviews?year=2026").json()["reviews"]] == ["in-scope"]
    assert client.get("/api/reviews/years").json() == {"years": [2026]}


def test_unlinked_review_hidden_from_pm(db):
    _as("project_manager", "pm")
    assert client.get("/api/reviews/unlinked").status_code == 404


def test_pm_cannot_open_review_outside_assigned_projects(db):
    _as("project_manager", "pm")
    assert client.get("/api/reviews/out-scope").status_code == 404
    assert client.get("/api/reviews/out-scope/download").status_code == 404
    assert client.get("/api/reviews/in-scope").status_code == 200


def test_assigned_reviewer_can_open_unlinked_review(db):
    _as("reviewer", "rev")
    assert client.get("/api/reviews/unlinked").status_code == 200
    assert client.get("/api/reviews/in-scope").status_code == 404


def test_reviewer_has_no_dashboard_data(db):
    _as("reviewer", "rev")
    assert client.get("/api/reviews?year=2026").json()["reviews"] == []
    assert client.get("/api/reviews/years").json() == {"years": []}


def test_my_reviews(db):
    _as("reviewer", "rev")
    ids = [r["id"] for r in client.get("/api/my/reviews").json()["reviews"]]
    assert set(ids) == {"out-scope", "unlinked"}
    _as("project_manager", "pm")
    assert client.get("/api/my/reviews").status_code == 403


def test_assigned_reviewer_can_finalize(db):
    _as("reviewer", "rev")
    response = client.patch("/api/reviews/out-scope", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_unassigned_reviewer_cannot_finalize(db):
    _as("reviewer", "someone-else")
    assert client.patch("/api/reviews/out-scope", json={"status": "approved"}).status_code == 404


def test_pm_can_see_but_not_edit(db):
    _as("project_manager", "pm")
    assert client.patch("/api/reviews/in-scope", json={"status": "approved"}).status_code == 403


def test_management_can_edit_any(db):
    _as("management", "mgmt")
    assert client.patch("/api/reviews/in-scope", json={"status": "approved"}).status_code == 200


def test_reviewer_cannot_reassign(db):
    _as("reviewer", "rev")
    assert client.patch("/api/reviews/out-scope/reviewer", json={"reviewer_id": None}).status_code == 403


def test_coordinator_can_assign_reviewer(db):
    _as("coordinator", "coord")
    response = client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "mgmt"})
    assert response.status_code == 200
    assert response.json()["reviewer_id"] == "mgmt"


def test_cannot_assign_pm_as_reviewer(db):
    _as("coordinator", "coord")
    assert client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "pm"}).status_code == 400


def test_reviewer_candidates_include_management(db):
    _as("coordinator", "coord")
    reviewers = client.get("/api/reviewers").json()["reviewers"]
    assert {r["id"] for r in reviewers} == {"rev", "mgmt"}
    assert {"id": "rev", "email": "rev@example.com", "name": "Rae"} in reviewers


@pytest.mark.parametrize("role", ["coordinator", "reviewer", "project_manager"])
def test_only_creators_can_start_or_upload(db, role):
    _as(role, "x")
    assert client.post("/api/reviews", data={"platform": "Android"}).status_code == 403
    assert client.post("/api/reviews/clause-preview", data={"platform": "Android"}).status_code == 403
    assert client.get("/api/reviews/nonexistent/progress").status_code == 403


def test_delete_review_admin_only(db):
    _as("management", "mgmt")
    assert client.delete("/api/reviews/in-scope").status_code == 403


def test_assigning_reviewer_does_not_leak_report_to_a_caller_who_cannot_see_it(db):
    _as("coordinator", "coord")
    body = client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "mgmt"}).json()
    assert body == {"id": "in-scope", "reviewer_id": "mgmt"}


def test_assigning_reviewer_returns_full_report_to_a_caller_who_can_see_it(db):
    _as("management", "mgmt")
    body = client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "rev"}).json()
    assert body["reviewer_id"] == "rev"
    assert "category_scores" in body
