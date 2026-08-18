from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
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
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


async def _persist(sessionmaker, review_id, project_id=None, platform="Android", created_at=None, status="pending_approval", total_score_pct=80.0):
    async with sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id=review_id,
            project_id=project_id,
            platform=platform,
            status=status,
            project_name="MyApp",
            created_at=created_at or datetime.now(timezone.utc),
            completed_at=created_at or datetime.now(timezone.utc),
            total_score_pct=total_score_pct,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=None,
            result_data={"category_scores": [{"id": "1", "name": "Structure", "percent_points": 80.0}]},
        )


async def test_list_reviews_filters_by_year_platform_and_project(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", project_id="p1", platform=".NET", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", project_id="p1", platform="Android", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r3", project_id="p2", platform=".NET", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025, "platform": ".NET", "project_id": "p1"})

    assert response.status_code == 200
    reviews = response.json()["reviews"]
    assert [r["id"] for r in reviews] == ["r1"]
    assert reviews[0]["category_scores"] == [{"id": "1", "name": "Structure", "percent_points": 80.0}]
    assert reviews[0]["project_id"] == "p1"


async def test_list_reviews_with_only_year_returns_everything_that_year(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", project_id="p1", platform=".NET", created_at=datetime(2025, 3, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", project_id="p2", platform="Android", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025})

    assert sorted(r["id"] for r in response.json()["reviews"]) == ["r1", "r2"]


async def test_list_reviews_includes_errored_reviews(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", status="pending_approval", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", status="error", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025})

    assert sorted(r["id"] for r in response.json()["reviews"]) == ["r1", "r2"]


def test_list_reviews_requires_year(test_sessionmaker):
    response = client.get("/api/reviews")

    assert response.status_code == 422


async def test_list_review_years_returns_distinct_years_sorted(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews/years")

    assert response.status_code == 200
    assert response.json() == {"years": [2024, 2025]}


def test_list_review_years_returns_empty_when_no_reviews(test_sessionmaker):
    response = client.get("/api/reviews/years")

    assert response.json() == {"years": []}
