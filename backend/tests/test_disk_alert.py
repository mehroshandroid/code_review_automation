import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.ops.disk_alert as disk_alert
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(disk_alert, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "a1", "a1@example.com", "h", "admin")
        await crud.create_user(s, "a2", "a2@example.com", "h", "admin")
        await crud.create_user(s, "off", "off@example.com", "h", "admin")
        await crud.update_user(s, "off", is_active=False)
        await crud.create_user(s, "co", "co@example.com", "h", "coordinator")
    yield maker
    await engine.dispose()


async def test_alert_emails_every_active_admin(db):
    sent = await disk_alert.alert_admins(percent=83, free="21G", mount="/")
    assert sent == 2
    async with db() as s:
        rows = await crud.list_notifications(s, "disk_space_low")
    assert sorted(r.recipient_user_id for r in rows) == ["a1", "a2"]
    assert rows[0].payload == {"percent": 83, "free": "21G", "mount": "/", "link": "/"}


def test_command_line_parses_its_arguments(monkeypatch):
    calls = []

    async def fake(percent, free, mount):
        calls.append((percent, free, mount))
        return 1

    monkeypatch.setattr(disk_alert, "alert_admins", fake)
    disk_alert.main(["83", "21G", "/"])
    assert calls == [(83, "21G", "/")]
