import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.settings as settings_module
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
    monkeypatch.setattr(settings_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def _as(role):
    user = User(id="u1", email=f"{role}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_get_llm_provider_settings_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/settings/llm-provider")
    assert response.status_code == 401


def test_get_llm_provider_settings_forbidden_for_user_role():
    _as("user")
    response = client.get("/api/settings/llm-provider")
    assert response.status_code == 403


def test_get_llm_provider_settings_allowed_for_reviewer(test_sessionmaker):
    _as("reviewer")
    response = client.get("/api/settings/llm-provider")
    assert response.status_code == 200


def test_get_llm_provider_settings_allowed_for_admin(test_sessionmaker):
    _as("admin")
    response = client.get("/api/settings/llm-provider")
    assert response.status_code == 200


def test_list_clause_checklists_forbidden_for_user_role():
    _as("user")
    response = client.get("/api/settings/clause-checklists")
    assert response.status_code == 403


def test_list_sample_templates_forbidden_for_user_role():
    _as("user")
    response = client.get("/api/settings/sample-templates")
    assert response.status_code == 403
