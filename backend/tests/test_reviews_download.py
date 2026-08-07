from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.api.reviews import _reviews
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


async def test_download_returns_404_when_no_result(test_sessionmaker):
    # Not in the live in-memory dict AND not found in the (empty) DB either
    # -- exercises the fallback path's own not-found branch, not just an
    # early return before it.
    response = client.get("/api/reviews/no-such-review/download")
    assert response.status_code == 404


def test_download_returns_file_and_deletes_it_after(tmp_path: Path):
    output_file = tmp_path / "output.xlsx"
    output_file.write_bytes(b"fake xlsx bytes")
    _reviews["download-ready"] = {
        "status": "completed",
        "phase": "completed",
        "progress": 100,
        "message": "Review complete",
        "stats": {},
        "download_path": str(output_file),
        "error": None,
    }

    response = client.get("/api/reviews/download-ready/download")
    assert response.status_code == 200
    assert response.content == b"fake xlsx bytes"
    assert not output_file.exists()
    assert not output_file.parent.exists()


async def test_download_falls_back_to_the_persisted_workbook_when_not_live(test_sessionmaker, tmp_path: Path):
    # Not in the in-memory _reviews dict at all -- simulates a review from
    # a prior backend process lifetime, reachable only via the historical
    # detail page.
    persisted_file = tmp_path / "persisted.xlsx"
    persisted_file.write_bytes(b"persisted xlsx bytes")

    async with test_sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id="persisted-review",
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
            workbook_path=str(persisted_file),
            result_data={},
        )

    response = client.get("/api/reviews/persisted-review/download")

    assert response.status_code == 200
    assert response.content == b"persisted xlsx bytes"
    # Unlike the live/temp-dir path, a persisted workbook is NOT deleted
    # after download -- an approver may need to download it again later.
    assert persisted_file.exists()


async def test_download_returns_404_when_persisted_review_has_no_workbook(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id="no-workbook-review",
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

    response = client.get("/api/reviews/no-workbook-review/download")

    assert response.status_code == 404
