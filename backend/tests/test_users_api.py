import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.users as users_module
from app.auth.dependencies import get_current_user
from app.auth.hashing import verify_password
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(users_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def test_create_user_requires_admin_role(test_sessionmaker):
    non_admin = User(id="u2", email="reviewer@example.com", role="reviewer", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: non_admin

    response = client.post("/api/users", json={"email": "new@example.com", "password": "correct horse", "role": "user"})

    assert response.status_code == 403


def test_create_user_succeeds_for_admin(test_sessionmaker):
    response = client.post("/api/users", json={"email": "new@example.com", "password": "correct horse", "role": "user"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert "password" not in body
    assert "password_hash" not in body


def test_create_user_rejects_a_short_password(test_sessionmaker):
    response = client.post("/api/users", json={"email": "new@example.com", "password": "short", "role": "user"})

    assert response.status_code == 400


def test_create_user_rejects_a_duplicate_email(test_sessionmaker):
    client.post("/api/users", json={"email": "dup@example.com", "password": "correct horse", "role": "user"})

    response = client.post("/api/users", json={"email": "dup@example.com", "password": "correct horse", "role": "user"})

    assert response.status_code == 409


def test_list_users_returns_created_users(test_sessionmaker):
    client.post("/api/users", json={"email": "one@example.com", "password": "correct horse", "role": "user"})

    response = client.get("/api/users")

    assert response.status_code == 200
    emails = [u["email"] for u in response.json()["users"]]
    assert "one@example.com" in emails


def test_update_user_changes_role_and_active_flag(test_sessionmaker):
    created = client.post("/api/users", json={"email": "one@example.com", "password": "correct horse", "role": "user"}).json()

    response = client.patch(f"/api/users/{created['id']}", json={"role": "reviewer", "is_active": False})

    assert response.status_code == 200
    assert response.json()["role"] == "reviewer"
    assert response.json()["is_active"] is False


def test_update_user_returns_404_for_an_unknown_id(test_sessionmaker):
    response = client.patch("/api/users/does-not-exist", json={"role": "admin"})

    assert response.status_code == 404


async def test_update_user_can_set_a_new_password(test_sessionmaker):
    created = client.post("/api/users", json={"email": "one@example.com", "password": "correct horse", "role": "user"}).json()

    response = client.patch(f"/api/users/{created['id']}", json={"password": "a brand new password"})

    assert response.status_code == 200
    async with test_sessionmaker() as session:
        user = await crud.get_user_by_id(session, created["id"])
    assert verify_password("a brand new password", user.password_hash)


def test_update_user_rejects_a_short_new_password(test_sessionmaker):
    created = client.post("/api/users", json={"email": "one@example.com", "password": "correct horse", "role": "user"}).json()

    response = client.patch(f"/api/users/{created['id']}", json={"password": "short"})

    assert response.status_code == 400


def test_update_user_forbids_changing_your_own_role(test_sessionmaker):
    admin = User(id="acting-admin", email="acting-admin@example.com", role="admin", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: admin

    response = client.patch("/api/users/acting-admin", json={"role": "reviewer"})

    assert response.status_code == 400


def test_update_user_forbids_deactivating_yourself(test_sessionmaker):
    admin = User(id="acting-admin", email="acting-admin@example.com", role="admin", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: admin

    response = client.patch("/api/users/acting-admin", json={"is_active": False})

    assert response.status_code == 400
