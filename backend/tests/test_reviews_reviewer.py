from datetime import datetime, timezone

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


async def _seed_review(sessionmaker, review_id="r1"):
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
            result_data={"category_scores": []},
        )


async def test_list_reviewers_returns_only_active_admins_and_reviewers(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="a1", email="alice@example.com", password_hash="h", role="admin")
        await crud.create_user(session, user_id="r1", email="rob@example.com", password_hash="h", role="reviewer")
        await crud.create_user(session, user_id="u1", email="uma@example.com", password_hash="h", role="user")

    response = client.get("/api/reviewers")

    assert response.status_code == 200
    assert response.json() == {
        "reviewers": [
            {"id": "a1", "email": "alice@example.com"},
            {"id": "r1", "email": "rob@example.com"},
        ]
    }


def test_list_reviewers_requires_login():
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/api/reviewers")

    assert response.status_code == 401


def test_list_reviewers_allows_the_user_role(test_sessionmaker):
    _as("user")

    response = client.get("/api/reviewers")

    assert response.status_code == 200


async def test_assign_reviewer_sets_the_reviewer_id(test_sessionmaker):
    await _seed_review(test_sessionmaker)
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="rev1", email="rob@example.com", password_hash="h", role="reviewer")

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "rev1"})

    assert response.status_code == 200
    assert response.json()["reviewer_id"] == "rev1"


async def test_assign_reviewer_allows_the_user_role(test_sessionmaker):
    await _seed_review(test_sessionmaker)
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="rev1", email="rob@example.com", password_hash="h", role="reviewer")
    _as("user")

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "rev1"})

    assert response.status_code == 200
    assert response.json()["reviewer_id"] == "rev1"


async def test_assign_reviewer_can_unassign_with_null(test_sessionmaker):
    await _seed_review(test_sessionmaker)
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="rev1", email="rob@example.com", password_hash="h", role="reviewer")
    client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "rev1"})

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": None})

    assert response.status_code == 200
    assert response.json()["reviewer_id"] is None


async def test_assign_reviewer_rejects_a_non_candidate_user(test_sessionmaker):
    await _seed_review(test_sessionmaker)
    async with test_sessionmaker() as session:
        await crud.create_user(session, user_id="plain1", email="plain@example.com", password_hash="h", role="user")

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "plain1"})

    assert response.status_code == 400


async def test_assign_reviewer_rejects_an_unknown_reviewer_id(test_sessionmaker):
    await _seed_review(test_sessionmaker)

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": "does-not-exist"})

    assert response.status_code == 400


def test_assign_reviewer_returns_404_for_unknown_review(test_sessionmaker):
    response = client.patch("/api/reviews/does-not-exist/reviewer", json={"reviewer_id": None})

    assert response.status_code == 404


def test_assign_reviewer_requires_login():
    app.dependency_overrides.pop(get_current_user, None)

    response = client.patch("/api/reviews/r1/reviewer", json={"reviewer_id": None})

    assert response.status_code == 401
