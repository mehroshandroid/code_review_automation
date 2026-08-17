from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.api.reviews import _recompute_category_scores
from app.db import crud
from app.db.models import Base
from main import app


def test_recompute_category_scores_averages_sub_criteria_and_categories():
    category_scores = [
        {"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 1}, {"id": "1.2", "score": 0}]},
        {"id": "2", "name": "Security", "sub_criteria": [{"id": "2.1", "score": 1}]},
    ]

    updated, total = _recompute_category_scores(category_scores)

    assert updated[0]["percent_points"] == 50.0
    assert updated[1]["percent_points"] == 100.0
    assert total == 75.0


def test_recompute_category_scores_ignores_null_scores():
    category_scores = [
        {"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 1}, {"id": "1.2", "score": None}]},
    ]

    updated, total = _recompute_category_scores(category_scores)

    assert updated[0]["percent_points"] == 100.0
    assert total == 100.0


def test_recompute_category_scores_returns_none_when_all_scores_are_null():
    category_scores = [
        {"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": None}]},
    ]

    updated, total = _recompute_category_scores(category_scores)

    assert updated[0]["percent_points"] is None
    assert total is None


def test_recompute_category_scores_preserves_other_fields_on_each_category():
    category_scores = [
        {"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 1, "remark": "Looks good"}]},
    ]

    updated, _ = _recompute_category_scores(category_scores)

    assert updated[0]["id"] == "1"
    assert updated[0]["name"] == "Structure"
    assert updated[0]["sub_criteria"] == [{"id": "1.1", "score": 1, "remark": "Looks good"}]


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


async def _seed_review(sessionmaker, review_id="r1", category_scores=None):
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
            total_score_pct=50,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=None,
            result_data={"category_scores": category_scores or []},
        )


async def test_patch_review_recomputes_scores_and_persists(test_sessionmaker):
    await _seed_review(
        test_sessionmaker,
        category_scores=[{"id": "1", "name": "Structure", "percent_points": 0, "sub_criteria": [{"id": "1.1", "score": 0, "remark": "bad"}]}],
    )

    with TestClient(app) as client:
        response = client.patch(
            "/api/reviews/r1",
            json={"category_scores": [{"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 1, "remark": "actually fine"}]}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_score_pct"] == 100.0
    assert body["category_scores"][0]["percent_points"] == 100.0
    assert body["category_scores"][0]["sub_criteria"][0]["remark"] == "actually fine"


async def test_patch_review_updates_status_to_approved(test_sessionmaker):
    await _seed_review(test_sessionmaker)

    with TestClient(app) as client:
        response = client.patch("/api/reviews/r1", json={"status": "approved"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_at"] is not None


async def test_patch_review_updates_status_to_completed(test_sessionmaker):
    await _seed_review(test_sessionmaker)

    with TestClient(app) as client:
        response = client.patch("/api/reviews/r1", json={"status": "completed"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_patch_review_rejects_invalid_status(test_sessionmaker):
    with TestClient(app) as client:
        response = client.patch("/api/reviews/r1", json={"status": "bogus"})

    assert response.status_code == 400


def test_patch_review_returns_404_for_unknown_review(test_sessionmaker):
    with TestClient(app) as client:
        response = client.patch("/api/reviews/does-not-exist", json={"status": "approved"})

    assert response.status_code == 404


async def test_patch_review_leaves_status_untouched_when_only_scores_given(test_sessionmaker):
    await _seed_review(
        test_sessionmaker,
        category_scores=[{"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 1}]}],
    )

    with TestClient(app) as client:
        response = client.patch(
            "/api/reviews/r1",
            json={"category_scores": [{"id": "1", "name": "Structure", "sub_criteria": [{"id": "1.1", "score": 0}]}]},
        )

    assert response.json()["status"] == "pending_approval"
