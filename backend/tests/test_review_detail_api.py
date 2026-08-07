from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.db import crud
from app.db.models import Base
from main import app


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


async def test_get_review_returns_the_full_persisted_review(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id="r1",
            project_id=None,
            platform=".NET",
            status="pending_approval",
            project_name="Moove",
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc),
            total_score_pct=82.5,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path="/data/reviews/r1.xlsx",
            result_data={
                "category_scores": [{"id": "1", "name": "Structure", "percent_points": 100, "sub_criteria": []}],
                "warnings": ["Outdated SDK"],
                "secrets_found": [],
                "lint_issues": [],
                "compile_status": "ok",
                "stats": {"total_time_ms": 1000},
            },
        )

    with TestClient(app) as client:
        response = client.get("/api/reviews/r1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "r1"
    assert body["platform"] == ".NET"
    assert body["status"] == "pending_approval"
    assert body["project_name"] == "Moove"
    assert body["total_score_pct"] == 82.5
    assert body["llm_provider"] == "azure"
    # SQLite (used here for test speed) doesn't round-trip timezone offsets
    # on DateTime(timezone=True) columns the way real Postgres does -- just
    # check the naive date/time portion, not the exact offset suffix.
    assert body["created_at"].startswith("2026-08-01T00:00:00")
    assert body["completed_at"].startswith("2026-08-01T00:05:00")
    assert body["has_workbook"] is True
    assert body["category_scores"] == [{"id": "1", "name": "Structure", "percent_points": 100, "sub_criteria": []}]
    assert body["warnings"] == ["Outdated SDK"]
    assert body["compile_status"] == "ok"
    assert body["stats"] == {"total_time_ms": 1000}


async def test_get_review_returns_404_when_not_found(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/reviews/does-not-exist")

    assert response.status_code == 404


async def test_get_review_has_workbook_false_when_no_workbook_path(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id="r2",
            project_id=None,
            platform="Android",
            status="error",
            project_name="MyApp",
            created_at=datetime.now(timezone.utc),
            completed_at=None,
            total_score_pct=None,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=None,
            result_data={"error": "boom"},
        )

    with TestClient(app) as client:
        response = client.get("/api/reviews/r2")

    assert response.status_code == 200
    assert response.json()["has_workbook"] is False
