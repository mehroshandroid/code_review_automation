from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
from app.db import crud
from app.db.models import Base
from main import app


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(projects_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def test_create_project_returns_the_created_project(test_sessionmaker):
    with TestClient(app) as client:
        response = client.post("/api/projects", json={"name": "Payments Service"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Payments Service"
    assert body["id"]
    assert body["created_at"]


def test_create_project_returns_409_on_duplicate_name(test_sessionmaker):
    with TestClient(app) as client:
        client.post("/api/projects", json={"name": "Payments Service"})
        response = client.post("/api/projects", json={"name": "Payments Service"})

    assert response.status_code == 409


def test_list_projects_returns_empty_list_initially(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_list_projects_returns_created_projects_newest_first(test_sessionmaker):
    with TestClient(app) as client:
        client.post("/api/projects", json={"name": "First"})
        client.post("/api/projects", json={"name": "Second"})
        response = client.get("/api/projects")

    names = [p["name"] for p in response.json()["projects"]]
    assert names == ["Second", "First"]


def test_update_project_renames_and_returns_it(test_sessionmaker):
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Old Name"}).json()["id"]
        response = client.patch(f"/api/projects/{project_id}", json={"name": "New Name"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project_id
    assert body["name"] == "New Name"


def test_update_project_returns_404_for_unknown_project(test_sessionmaker):
    with TestClient(app) as client:
        response = client.patch("/api/projects/nonexistent", json={"name": "New Name"})

    assert response.status_code == 404


def test_update_project_returns_409_on_duplicate_name(test_sessionmaker):
    with TestClient(app) as client:
        client.post("/api/projects", json={"name": "Taken"})
        project_id = client.post("/api/projects", json={"name": "Original"}).json()["id"]
        response = client.patch(f"/api/projects/{project_id}", json={"name": "Taken"})

    assert response.status_code == 409


async def _persist(session, review_id, project_id, platform="Android", created_at=None, total_score_pct=None):
    return await crud.persist_review_result(
        session,
        review_id=review_id,
        project_id=project_id,
        platform=platform,
        status="pending_approval",
        project_name="MyApp",
        created_at=created_at or datetime.now(timezone.utc),
        completed_at=created_at or datetime.now(timezone.utc),
        total_score_pct=total_score_pct,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path=None,
        result_data={"category_scores": []},
    )


async def test_list_project_reviews_returns_only_that_projects_reviews_newest_first(test_sessionmaker):
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Payments Service"}).json()["id"]
        other_project_id = client.post("/api/projects", json={"name": "Other"}).json()["id"]

        async with test_sessionmaker() as session:
            await _persist(session, "r1", project_id, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), total_score_pct=80)
            await _persist(session, "r2", project_id, created_at=datetime(2026, 2, 1, tzinfo=timezone.utc), total_score_pct=90)
            await _persist(session, "r3", other_project_id, created_at=datetime(2026, 3, 1, tzinfo=timezone.utc))

        response = client.get(f"/api/projects/{project_id}/reviews")

    assert response.status_code == 200
    reviews = response.json()["reviews"]
    assert [r["id"] for r in reviews] == ["r2", "r1"]
    assert reviews[0]["total_score_pct"] == 90
    assert reviews[0]["platform"] == "Android"
    assert reviews[0]["status"] == "pending_approval"
    assert "result_data" not in reviews[0]


async def test_list_project_reviews_returns_empty_list_when_project_has_none(test_sessionmaker):
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Payments Service"}).json()["id"]
        response = client.get(f"/api/projects/{project_id}/reviews")

    assert response.status_code == 200
    assert response.json() == {"reviews": []}
