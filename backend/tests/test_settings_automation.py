import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.settings as settings_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from app.secrets import decrypt
from main import app

client = TestClient(app)


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings_module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None)])
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="system")
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "iOS"), run_status="failed", failure_kind="url")
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_defaults_when_nothing_configured(db):
    _as("admin")
    body = client.get("/api/settings/automation").json()
    assert body == {
        "pat": {"configured": False, "last4": None, "updated_at": None, "updated_by_name": None},
        "compile_modes": {"Android": "compiler", ".NET": "compiler", "iOS": "static"},
    }


async def test_save_pat_encrypts_and_requeues_system_failures(db):
    _as("admin")
    response = client.put("/api/settings/devops-pat", json={"pat": "  secretpat1234  "})
    assert response.status_code == 200
    assert response.json()["configured"] is True and response.json()["last4"] == "1234"
    assert response.json()["updated_by_name"] == "Ada"
    async with db() as s:
        settings = await crud.get_org_settings(s)
        assert decrypt(settings.devops_pat_encrypted) == "secretpat1234"
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"
        assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"


def test_pat_is_never_returned(db):
    _as("admin")
    client.put("/api/settings/devops-pat", json={"pat": "secretpat1234"})
    assert "secretpat1234" not in client.get("/api/settings/automation").text


def test_pat_validation_and_permissions(db):
    _as("admin")
    assert client.put("/api/settings/devops-pat", json={"pat": "   "}).status_code == 400
    _as("management", "m")
    assert client.put("/api/settings/devops-pat", json={"pat": "x"}).status_code == 403
    assert client.get("/api/settings/automation").status_code == 200
    _as("coordinator", "c")
    assert client.get("/api/settings/automation").status_code == 403


def test_compile_modes(db):
    _as("management", "m")
    response = client.put("/api/settings/auto-compile-modes", json={"modes": {"iOS": "compiler", "Android": "local"}})
    assert response.json() == {"compile_modes": {"Android": "local", ".NET": "compiler", "iOS": "compiler"}}
    assert client.get("/api/settings/automation").json()["compile_modes"]["iOS"] == "compiler"
    assert client.put("/api/settings/auto-compile-modes", json={"modes": {".NET": "local"}}).status_code == 400
    assert client.put("/api/settings/auto-compile-modes", json={"modes": {"Web": "static"}}).status_code == 400
