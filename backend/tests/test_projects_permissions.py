import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
from app.auth.dependencies import get_current_user
from app.db.models import Base, User
from main import app

client = TestClient(app)


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(projects_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def _as(role):
    user = User(id="u1", email=f"{role}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_projects_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/projects")
    assert response.status_code == 401


def test_list_projects_allowed_for_pm(test_sessionmaker):
    _as("project_manager")
    assert client.get("/api/projects").status_code == 200


def test_create_project_forbidden_for_pm(test_sessionmaker):
    _as("project_manager")
    assert client.post("/api/projects", json={"name": "Nope"}).status_code == 403


def test_rename_project_forbidden_for_reviewer(test_sessionmaker):
    _as("reviewer")
    assert client.patch("/api/projects/does-not-matter", json={"name": "Renamed"}).status_code == 403


def test_rename_project_allowed_for_coordinator_reaches_the_404_not_the_403(test_sessionmaker):
    _as("coordinator")
    assert client.patch("/api/projects/does-not-exist", json={"name": "Renamed"}).status_code == 404
