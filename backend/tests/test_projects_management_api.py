from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
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
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(projects_module, "new_session", lambda: sessionmaker())
    async with sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_project(session, "p2", "Two")
        await crud.create_user(session, "pm1", "pm1@example.com", "h", "project_manager", name="Pat")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer")
        await crud.persist_review_result(
            session, review_id="r1", project_id="p1", platform="Android", status="approved",
            project_name="One", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=80,
            llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
            workbook_path=None, result_data={},
        )
    yield sessionmaker
    await engine.dispose()


def _as(role, user_id="u1"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_coordinator_lists_all_projects_with_managers_and_counts(db):
    _as("coordinator")
    projects = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert set(projects) == {"p1", "p2"}
    assert projects["p1"]["review_count"] == 1
    assert projects["p2"]["manager_ids"] == []


def test_pm_lists_only_assigned_projects_without_manager_ids(db):
    _as("coordinator")
    client.put("/api/projects/p2/managers", json={"user_ids": ["pm1"]})
    _as("project_manager", "pm1")
    projects = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in projects] == ["p2"]
    assert "manager_ids" not in projects[0]


def test_reviewer_sees_no_projects(db):
    _as("reviewer", "rev")
    assert client.get("/api/projects").json()["projects"] == []


@pytest.mark.parametrize("role", ["admin", "management", "coordinator"])
def test_project_staff_can_create_and_rename(db, role):
    _as(role)
    created = client.post("/api/projects", json={"name": f"New {role}"})
    assert created.status_code == 200
    renamed = client.patch(f"/api/projects/{created.json()['id']}", json={"name": f"Renamed {role}"})
    assert renamed.status_code == 200


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_others_cannot_create_or_rename(db, role):
    _as(role)
    assert client.post("/api/projects", json={"name": "X"}).status_code == 403
    assert client.patch("/api/projects/p1", json={"name": "X"}).status_code == 403


def test_assign_managers_replaces_set(db):
    _as("coordinator")
    response = client.put("/api/projects/p1/managers", json={"user_ids": ["pm1"]})
    assert response.status_code == 200
    assert response.json()["manager_ids"] == ["pm1"]
    response = client.put("/api/projects/p1/managers", json={"user_ids": []})
    assert response.json()["manager_ids"] == []


def test_assign_managers_rejects_non_pm_and_unknown(db):
    _as("coordinator")
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["rev"]}).status_code == 400
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["ghost"]}).status_code == 404
    assert client.put("/api/projects/nope/managers", json={"user_ids": []}).status_code == 404


def test_assign_managers_forbidden_for_pm(db):
    _as("project_manager", "pm1")
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["pm1"]}).status_code == 403


def test_coordinator_cannot_delete(db):
    _as("coordinator")
    assert client.delete("/api/projects/p2").status_code == 403


@pytest.mark.parametrize("role", ["admin", "management"])
def test_delete_empty_project(db, role):
    _as(role)
    assert client.delete("/api/projects/p2").status_code == 204
    assert client.delete("/api/projects/p2").status_code == 404


def test_delete_project_with_reviews_conflicts(db):
    _as("admin")
    response = client.delete("/api/projects/p1")
    assert response.status_code == 409
    assert response.json()["detail"] == "This project has 1 reviews and can't be deleted."


def test_list_project_managers(db):
    _as("coordinator")
    assert client.get("/api/project-managers").json() == {
        "managers": [{"id": "pm1", "email": "pm1@example.com", "name": "Pat"}],
    }
    _as("reviewer")
    assert client.get("/api/project-managers").status_code == 403


def test_project_reviews_404_outside_scope(db):
    _as("project_manager", "pm1")
    assert client.get("/api/projects/p1/reviews").status_code == 404
    _as("admin")
    assert len(client.get("/api/projects/p1/reviews").json()["reviews"]) == 1
