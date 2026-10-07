from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.auth.dependencies as deps_module
from app.auth.dependencies import COOKIE_NAME, get_current_user
from app.auth.permissions import require_permission
from app.auth.token import create_access_token
from app.db import crud
from app.db.models import Base

_auth_test_app = FastAPI()


@_auth_test_app.get("/whoami")
async def whoami(user=Depends(get_current_user)):
    return {"id": user.id, "role": user.role}


@_auth_test_app.get("/admin-only")
async def admin_only(user=Depends(require_permission("users.manage"))):
    return {"ok": True}


client = TestClient(_auth_test_app)


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(deps_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


async def _create_user(sessionmaker, user_id="u1", email="a@example.com", role="user", is_active=True):
    async with sessionmaker() as session:
        user = await crud.create_user(session, user_id=user_id, email=email, password_hash="h", role=role)
        if not is_active:
            await crud.update_user(session, user_id, is_active=False)
        return user


def test_get_current_user_rejects_a_request_with_no_cookie(test_sessionmaker):
    response = client.get("/whoami")
    assert response.status_code == 401


def test_get_current_user_rejects_an_invalid_token(test_sessionmaker):
    client.cookies.set(COOKIE_NAME, "not-a-real-token")
    response = client.get("/whoami")
    client.cookies.delete(COOKIE_NAME)
    assert response.status_code == 401


async def test_get_current_user_accepts_a_valid_token_for_an_active_user(test_sessionmaker):
    await _create_user(test_sessionmaker, user_id="u1", role="reviewer")
    token = create_access_token("u1")
    client.cookies.set(COOKIE_NAME, token)

    response = client.get("/whoami")
    client.cookies.delete(COOKIE_NAME)

    assert response.status_code == 200
    assert response.json() == {"id": "u1", "role": "reviewer"}


async def test_get_current_user_rejects_a_token_for_a_deactivated_user(test_sessionmaker):
    await _create_user(test_sessionmaker, user_id="u1", is_active=False)
    token = create_access_token("u1")
    client.cookies.set(COOKIE_NAME, token)

    response = client.get("/whoami")
    client.cookies.delete(COOKIE_NAME)

    assert response.status_code == 401


async def test_get_current_user_rejects_a_token_for_a_since_deleted_user(test_sessionmaker):
    token = create_access_token("never-existed")
    client.cookies.set(COOKIE_NAME, token)

    response = client.get("/whoami")
    client.cookies.delete(COOKIE_NAME)

    assert response.status_code == 401


async def test_require_permission_allows_a_role_holding_the_capability(test_sessionmaker):
    await _create_user(test_sessionmaker, user_id="u1", role="admin")
    token = create_access_token("u1")
    client.cookies.set(COOKIE_NAME, token)

    response = client.get("/admin-only")
    client.cookies.delete(COOKIE_NAME)

    assert response.status_code == 200


async def test_require_permission_rejects_a_role_without_the_capability(test_sessionmaker):
    await _create_user(test_sessionmaker, user_id="u1", role="management")
    token = create_access_token("u1")
    client.cookies.set(COOKIE_NAME, token)

    response = client.get("/admin-only")
    client.cookies.delete(COOKIE_NAME)

    assert response.status_code == 403
