from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
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
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def _as(role):
    user = User(id="u1", email=f"{role}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


async def _persist(sessionmaker, review_id="r1", workbook_path=None):
    async with sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id=review_id,
            project_id=None,
            platform="Android",
            status="pending_approval",
            project_name="MyApp",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            total_score_pct=90,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=workbook_path,
            result_data={},
        )


async def test_delete_review_removes_it_for_admin(test_sessionmaker):
    await _persist(test_sessionmaker, "r1")

    response = client.delete("/api/reviews/r1")

    assert response.status_code == 204
    async with test_sessionmaker() as session:
        assert await crud.get_review_by_id(session, "r1") is None


async def test_delete_review_also_removes_its_workbook_file(test_sessionmaker, tmp_path: Path):
    workbook = tmp_path / "r1.xlsx"
    workbook.write_bytes(b"fake xlsx bytes")
    await _persist(test_sessionmaker, "r1", workbook_path=str(workbook))

    response = client.delete("/api/reviews/r1")

    assert response.status_code == 204
    assert not workbook.exists()


async def test_delete_review_returns_404_for_unknown_review(test_sessionmaker):
    response = client.delete("/api/reviews/does-not-exist")

    assert response.status_code == 404


async def test_delete_review_forbidden_for_management(test_sessionmaker):
    await _persist(test_sessionmaker, "r1")
    _as("management")

    response = client.delete("/api/reviews/r1")

    assert response.status_code == 403
    async with test_sessionmaker() as session:
        assert await crud.get_review_by_id(session, "r1") is not None


async def test_delete_review_forbidden_for_project_manager(test_sessionmaker):
    await _persist(test_sessionmaker, "r1")
    _as("project_manager")

    response = client.delete("/api/reviews/r1")

    assert response.status_code == 403
