import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


def _build_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D3:D4)", None, None, None])
    ws.append([1.1, "Clear and consistent naming", None, None, None, None, None])
    ws.append([1.2, "Clean structure and formatting", None, None, None, None, None])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
async def test_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    yield sessionmaker
    await engine.dispose()


def test_clause_preview_uses_the_uploaded_file_and_merges_org_defaults(test_sessionmaker, monkeypatch):
    async def fake_load_clause_checklists():
        return {(".NET", "1.2"): "Check for retry logic"}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)

    response = client.post(
        "/api/reviews/clause-preview",
        files={"file": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"platform": ".NET"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["categories"] == [
        {
            "id": "1", "name": "Code naming conventions / Code Structure",
            "sub_criteria": [
                {"id": "1.1", "description": "Clear and consistent naming", "checklist_text": None},
                {"id": "1.2", "description": "Clean structure and formatting", "checklist_text": "Check for retry logic"},
            ],
        }
    ]


def test_clause_preview_falls_back_to_the_stored_default_template(test_sessionmaker, monkeypatch):
    async def fake_resolve_excel_template(file, platform):
        assert file is None
        assert platform == "Android"
        return _build_xlsx_bytes(), "android-default.xlsx"

    async def fake_load_clause_checklists():
        return {}

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_resolve_excel_template)
    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)

    response = client.post("/api/reviews/clause-preview", data={"platform": "Android"})

    assert response.status_code == 200
    assert len(response.json()["categories"]) == 1


async def _persist(sessionmaker, review_id, platform, created_at, result_data):
    async with sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id=review_id,
            project_id=None,
            platform=platform,
            status="pending_approval",
            project_name="Test",
            created_at=created_at,
            completed_at=created_at,
            total_score_pct=None,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=None,
            result_data=result_data,
        )


async def test_clause_preview_uses_the_most_recent_reviews_guidance_over_org_defaults(test_sessionmaker, monkeypatch):

    await _persist(
        test_sessionmaker, "r1", ".NET", datetime(2026, 1, 1, tzinfo=timezone.utc),
        {"clause_checklists": {"1.1": "Guidance from last review"}},
    )

    async def fake_load_clause_checklists():
        # Org-wide guidance IS configured, but must lose to the last review's
        # guidance -- confirms "last review wins once one exists" rather than
        # only being a fallback for clauses org-wide leaves empty.
        return {(".NET", "1.1"): "Org default that should be overridden"}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)

    response = client.post(
        "/api/reviews/clause-preview",
        files={"file": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"platform": ".NET"},
    )

    assert response.status_code == 200
    sub_criteria = response.json()["categories"][0]["sub_criteria"]
    by_id = {s["id"]: s["checklist_text"] for s in sub_criteria}
    assert by_id["1.1"] == "Guidance from last review"
    assert by_id["1.2"] is None


async def test_clause_preview_falls_back_to_org_defaults_when_latest_review_has_no_clause_checklists(test_sessionmaker, monkeypatch):

    # An older review persisted before this feature existed (or one that
    # errored before reaching scoring) has no "clause_checklists" key at all.
    await _persist(
        test_sessionmaker, "r1", ".NET", datetime(2026, 1, 1, tzinfo=timezone.utc),
        {"category_scores": []},
    )

    async def fake_load_clause_checklists():
        return {(".NET", "1.1"): "Org default"}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)

    response = client.post(
        "/api/reviews/clause-preview",
        files={"file": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"platform": ".NET"},
    )

    assert response.status_code == 200
    sub_criteria = response.json()["categories"][0]["sub_criteria"]
    by_id = {s["id"]: s["checklist_text"] for s in sub_criteria}
    assert by_id["1.1"] == "Org default"


def test_clause_preview_returns_404_when_no_template_available(test_sessionmaker, monkeypatch):
    async def fake_resolve_excel_template(file, platform):
        return None, None

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_resolve_excel_template)

    response = client.post("/api/reviews/clause-preview", data={"platform": "Android"})

    assert response.status_code == 404


def test_clause_preview_returns_422_when_the_sheet_cannot_be_parsed(test_sessionmaker):
    response = client.post(
        "/api/reviews/clause-preview",
        files={"file": ("bad.xlsx", b"not a real workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"platform": "Android"},
    )

    assert response.status_code == 422


def test_clause_preview_forbidden_for_the_user_role(test_sessionmaker):
    non_privileged = User(id="u1", email="u@example.com", role="user", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: non_privileged

    response = client.post(
        "/api/reviews/clause-preview",
        files={"file": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"platform": "Android"},
    )

    assert response.status_code == 403
