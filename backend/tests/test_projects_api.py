import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
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
