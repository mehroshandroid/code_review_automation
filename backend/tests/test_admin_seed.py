import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import main
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


async def test_seeds_an_admin_when_env_vars_set_and_table_empty(test_sessionmaker, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery staple")

    await main._seed_admin_if_needed()

    async with test_sessionmaker() as session:
        user = await crud.get_user_by_email(session, "admin@example.com")
    assert user is not None
    assert user.role == "admin"


async def test_skips_seeding_when_env_vars_are_not_set(test_sessionmaker, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    await main._seed_admin_if_needed()  # must not raise

    async with test_sessionmaker() as session:
        assert await crud.count_users(session) == 0


async def test_skips_seeding_when_a_user_already_exists(test_sessionmaker, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery staple")
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="existing", email="already@example.com", password_hash="h", role="user")

    await main._seed_admin_if_needed()

    async with test_sessionmaker() as session:
        assert await crud.count_users(session) == 1
