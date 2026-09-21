import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
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


def test_list_reviews_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/reviews", params={"year": 2026})
    assert response.status_code == 401


def test_list_reviews_allows_the_user_role(test_sessionmaker):
    _as("user")
    response = client.get("/api/reviews", params={"year": 2026})
    assert response.status_code == 200


def test_download_review_allows_the_user_role_reaches_the_real_404(test_sessionmaker):
    _as("user")
    response = client.get("/api/reviews/does-not-exist/download")
    # Passes the permission check and reaches the real not-found handling.
    assert response.status_code == 404


def test_edit_review_scores_forbidden_for_user():
    _as("user")
    response = client.patch("/api/reviews/does-not-matter", json={"status": "approved"})
    assert response.status_code == 403


def test_edit_review_scores_allowed_for_reviewer_reaches_the_real_404(test_sessionmaker):
    _as("reviewer")
    response = client.patch("/api/reviews/does-not-exist", json={"status": "approved"})
    assert response.status_code == 404


def test_edit_review_scores_allowed_for_admin_reaches_the_real_404(test_sessionmaker):
    _as("admin")
    response = client.patch("/api/reviews/does-not-exist", json={"status": "approved"})
    assert response.status_code == 404
