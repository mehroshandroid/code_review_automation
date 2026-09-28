import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.auth as auth_module
import app.auth.dependencies as deps_module
from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password
from app.db import crud
from app.db.models import Base
from main import app

client = TestClient(app)


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth_module, "new_session", lambda: sessionmaker())
    monkeypatch.setattr(deps_module, "new_session", lambda: sessionmaker())
    # This file tests the real auth flow, not the conftest default-admin
    # override -- remove it for the duration of each test here.
    app.dependency_overrides.pop(get_current_user, None)
    yield sessionmaker
    await engine.dispose()


async def _create_user(sessionmaker, email="admin@example.com", password="correct horse", role="admin"):
    async with sessionmaker() as session:
        await crud.create_user(session, user_id="u1", email=email, password_hash=hash_password(password), role=role)


async def test_login_sets_a_cookie_and_returns_the_user_on_correct_credentials(test_sessionmaker):
    await _create_user(test_sessionmaker, email="admin@example.com", password="correct horse")

    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct horse"})

    assert response.status_code == 200
    assert response.json() == {"id": "u1", "email": "admin@example.com", "role": "admin"}
    assert "access_token" in response.cookies


async def test_login_rejects_a_wrong_password(test_sessionmaker):
    await _create_user(test_sessionmaker, email="admin@example.com", password="correct horse")

    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"})

    assert response.status_code == 401


async def test_login_rejects_an_unknown_email(test_sessionmaker):
    response = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"})

    assert response.status_code == 401


async def test_login_rejects_a_deactivated_account(test_sessionmaker):
    await _create_user(test_sessionmaker, email="admin@example.com", password="correct horse")
    async with test_sessionmaker() as session:
        await crud.update_user(session, "u1", is_active=False)

    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct horse"})

    assert response.status_code == 401


async def test_me_returns_the_logged_in_user_after_login(test_sessionmaker):
    await _create_user(test_sessionmaker, email="admin@example.com", password="correct horse")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct horse"})

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"


def test_me_rejects_when_not_logged_in(test_sessionmaker):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


async def test_logout_clears_the_session_so_me_then_rejects(test_sessionmaker):
    await _create_user(test_sessionmaker, email="admin@example.com", password="correct horse")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct horse"})

    logout_response = client.post("/api/auth/logout")
    me_response = client.get("/api/auth/me")

    assert logout_response.status_code == 200
    assert me_response.status_code == 401


def test_microsoft_login_redirects_to_the_authorization_url_and_sets_a_state_cookie(test_sessionmaker, monkeypatch):
    captured = {}

    def fake_get_authorization_url(state):
        captured["state"] = state
        return "https://login.microsoftonline.com/mock-tenant/authorize?mock=1"

    monkeypatch.setattr(auth_module.microsoft_auth, "get_authorization_url", fake_get_authorization_url)

    response = client.get("/api/auth/microsoft/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://login.microsoftonline.com/mock-tenant/authorize?mock=1"
    assert response.cookies["sso_state"] == captured["state"]
