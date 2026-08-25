import datetime
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.db import crud
from app.db.models import Base
from main import app

client = TestClient(app)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
async def test_sessionmaker(monkeypatch, tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    monkeypatch.setenv("REVIEW_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    yield sessionmaker
    await engine.dispose()


async def _create_project(sessionmaker, project_id="p1", name="Payments Service"):
    async with sessionmaker() as session:
        await crud.create_project(session, project_id=project_id, name=name)


def _build_completed_review_bytes(
    *, reviewer="Jane Doe", dated=datetime.date(2026, 7, 24), score_1_1=1, score_1_2=0,
) -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["<Project Name>", None, None, None, None, None, None])
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D4:D5)", "=D3*C3", "=E3/C3", None])
    ws.append([None, "Clear and consistent naming", None, score_1_1, None, None, None])
    ws.append([1.2, "Clean structure and formatting", None, score_1_2, None, None, "Needs cleanup." if score_1_2 == 0 else None])
    ws.append([None, None, None, None, None, None, None])
    ws.append([None, "General Remarks: placeholder text", None, None, None, None, None])
    ws.append([None, "Reviewers: ", reviewer, None, None, None, None])
    ws.append([None, "Dated", dated, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


async def test_upload_completed_review_persists_an_approved_review(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": ".NET"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["platform"] == ".NET"
    assert body["project_id"] == "p1"
    assert body["project_name"] == "Payments Service"
    assert body["total_score_pct"] == 50.0
    assert body["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 50.0}
    ]


async def test_upload_completed_review_uses_the_sheets_date_for_created_and_completed_at(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(dated=datetime.date(2025, 3, 4)), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "Android"},
    )

    body = response.json()
    assert body["created_at"].startswith("2025-03-04")
    assert body["completed_at"].startswith("2025-03-04")


async def test_upload_completed_review_stores_reviewer_as_created_by_and_approved_by(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(reviewer="Jane Doe"), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "iOS"},
    )

    review_id = response.json()["id"]
    async with test_sessionmaker() as session:
        review = await crud.get_review_by_id(session, review_id)
    assert review.created_by == "Jane Doe"
    assert review.approved_by == "Jane Doe"
    assert review.source == "manual_upload"
    assert review.llm_provider == "manual_upload"
    assert review.compile_check_mode == "none"


async def test_upload_completed_review_persists_the_file_as_a_downloadable_workbook(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "Android"},
    )

    review_id = response.json()["id"]
    download_response = client.get(f"/api/reviews/{review_id}/download")
    assert download_response.status_code == 200


async def test_upload_completed_review_rejects_non_xlsx_filename(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.txt", b"not a workbook", "text/plain")},
        data={"projectId": "p1", "platform": "Android"},
    )

    assert response.status_code == 400
    assert "xlsx" in response.json()["detail"].lower()


async def test_upload_completed_review_rejects_an_unopenable_file(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", b"not actually an xlsx file", XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "Android"},
    )

    assert response.status_code == 400
    assert "valid" in response.json()["detail"].lower()


async def test_upload_completed_review_rejects_a_missing_project(test_sessionmaker):
    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(), XLSX_MEDIA_TYPE)},
        data={"projectId": "does-not-exist", "platform": "Android"},
    )

    assert response.status_code == 404


async def test_upload_completed_review_rejects_a_sheet_with_a_blank_score(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(score_1_2=None), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "Android"},
    )

    assert response.status_code == 400
    assert "1.2" in response.json()["detail"]


async def test_upload_completed_review_rejects_a_sheet_missing_the_reviewer_name(test_sessionmaker):
    await _create_project(test_sessionmaker, "p1", "Payments Service")

    response = client.post(
        "/api/reviews/upload",
        files={"file": ("review.xlsx", _build_completed_review_bytes(reviewer=None), XLSX_MEDIA_TYPE)},
        data={"projectId": "p1", "platform": "Android"},
    )

    assert response.status_code == 400
    assert "reviewer" in response.json()["detail"].lower()
