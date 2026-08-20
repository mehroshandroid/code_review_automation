# Upload Completed Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload an already-completed review sheet (one of the platform `.xlsx` templates, filled in by hand outside the app) and have it persisted as a normal `PlatformReview` record — reviewer name and review date read from the sheet, correct platform (Android/iOS/.NET/Web).

**Architecture:** Two new read-side functions in `excel_handler.py` (`read_scores`, `read_metadata`) mirror the existing write-side ones (`populate_scores`, `populate_metadata`) exactly, reusing the same structure-discovery and score-aggregation code the live-analysis pipeline already uses. A new synchronous endpoint `POST /api/reviews/upload` parses the uploaded workbook with these functions and persists it via `crud.persist_review_result` (extended with `created_by`/`approved_by`/`approved_at`). A new `UploadReviewDialog.jsx`, opened from a button next to "Start review", collects project + platform + file and calls it.

**Tech Stack:** FastAPI, SQLAlchemy (async), openpyxl, React, Testing Library, Jest.

## Global Constraints

- Uploaded file must be the same platform `.xlsx` template the app already reads/writes (see `samplefiles/AndroidSampleReview.xlsx`) — no new sheet format.
- Available for all four platforms (Android/iOS/.NET/Web), independent of `PLATFORMS[].available` (which only gates the automated "Start review" flow).
- Uploaded reviews land with `status = "approved"` immediately — no extra in-app confirmation step.
- `created_at`/`completed_at`/`approved_at` on the persisted record all use the review date parsed from the sheet's "Dated:" cell (interpreted as UTC midnight), not the upload time.
- `created_by`/`approved_by` on the persisted record both get the reviewer name parsed from the sheet's "Reviewers:" cell, verbatim (no name-splitting).
- `source = "manual_upload"`, `llm_provider = "manual_upload"`, `llm_model = None`, `compile_check_mode = "none"` — no analysis, no LLM call, no compile check runs for an uploaded review.
- Any parsing failure (blank/invalid score cell, blank reviewer, blank/unparseable date, unreadable/non-xlsx file) is rejected outright with a specific `HTTPException(status_code=400, detail="...")` — never a silent fallback.
- All existing call sites of `crud.persist_review_result` must keep working unchanged (new params are optional, default `None`).

---

### Task 1: Read-side Excel parsing (`read_scores`, `read_metadata`)

**Files:**
- Modify: `backend/app/analyzer/excel_handler.py`
- Test: `backend/tests/test_excel_handler.py`

**Interfaces:**
- Consumes: `discover_structure(ws) -> (categories, descriptions)` (existing), `aggregate_category_scores(sub_scores) -> dict` (existing), `_iter_positional_sub_rows`, `_find_header_row`, `_resolve_columns` (existing private helpers), module constants `REVIEWERS_LABEL = "reviewers"`, `DATED_LABEL = "dated"` (existing).
- Produces:
  - `read_scores(ws, categories: dict, descriptions: dict) -> dict` — returns `{category_id: aggregate_category_scores(...)}` (same shape `compute_total_score_pct` already consumes). Raises `ValueError` if a sub-criterion's score cell is blank, or not `0`/`1`.
  - `read_metadata(ws) -> tuple[str, datetime.date]` — returns `(reviewer_name, review_date)`. Raises `ValueError` if the "Reviewers:" cell is blank, or the "Dated:" cell is blank/unparseable.

- [ ] **Step 1: Write the failing tests**

Add to the end of `backend/tests/test_excel_handler.py` (the file already imports `Workbook`, `load_workbook`, `datetime`, and has the `_build_template` helper and `FIXTURES_DIR` constant at the top — add `read_scores` and `read_metadata` to the existing `from app.analyzer.excel_handler import (...)` block):

```python
def test_read_scores_returns_percent_points_matching_the_filled_in_cells(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    categories, descriptions = discover_structure(ws)
    ws["D4"].value = 1
    ws["G4"].value = None
    ws["D5"].value = 0
    ws["G5"].value = "Formatting is inconsistent."

    scores_by_category = read_scores(ws, categories, descriptions)

    assert scores_by_category["1"]["sub_scores"]["1.1"] == {"score": 1, "remark": None}
    assert scores_by_category["1"]["sub_scores"]["1.2"] == {"score": 0, "remark": "Formatting is inconsistent."}
    assert scores_by_category["1"]["percent_points"] == 50.0


def test_read_scores_raises_when_a_score_cell_is_blank(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    categories, descriptions = discover_structure(ws)
    ws["D4"].value = 1
    # D5 (sub-criterion 1.2's score cell) intentionally left blank.

    try:
        read_scores(ws, categories, descriptions)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "1.2" in str(exc)
        assert "no score" in str(exc).lower()


def test_read_scores_raises_on_a_non_binary_score(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    categories, descriptions = discover_structure(ws)
    ws["D4"].value = 0.5
    ws["D5"].value = 1

    try:
        read_scores(ws, categories, descriptions)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "1.1" in str(exc)
        assert "0 or 1" in str(exc)


def test_read_metadata_returns_reviewer_and_date(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    ws["C8"].value = "Jane Doe"
    ws["C9"].value = datetime.date(2026, 7, 24)

    reviewer_name, review_date = read_metadata(ws)

    assert reviewer_name == "Jane Doe"
    assert review_date == datetime.date(2026, 7, 24)


def test_read_metadata_parses_a_plain_string_date():
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([None, "Reviewers: ", "Jane Doe", None, None, None, None])
    ws.append([None, "Dated", None, "2026-07-24", None, None, None])

    reviewer_name, review_date = read_metadata(ws)

    assert reviewer_name == "Jane Doe"
    assert review_date == datetime.date(2026, 7, 24)


def test_read_metadata_raises_when_reviewer_cell_is_blank(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    ws["C8"].value = None  # overrides _build_template's "<reviewer Name>" placeholder
    ws["C9"].value = datetime.date(2026, 7, 24)

    try:
        read_metadata(ws)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "reviewer" in str(exc).lower()


def test_read_metadata_raises_when_date_cell_is_blank_or_unparseable(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active
    ws["C8"].value = "Jane Doe"
    ws["C9"].value = "not a date"

    try:
        read_metadata(ws)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "date" in str(exc).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_excel_handler.py -k "read_scores or read_metadata" -v`
Expected: FAIL with `ImportError` (`read_scores`/`read_metadata` not defined) once you've added them to the import block — until then, `NameError`.

- [ ] **Step 3: Implement `read_scores` and `read_metadata`**

Insert into `backend/app/analyzer/excel_handler.py`, directly after the `populate_metadata` function (before `generate_review_excel`):

```python
def read_scores(ws, categories: dict, descriptions: dict) -> dict:
    """Mirrors populate_scores: reads each sub-criterion's score/remark cell
    (instead of writing them) for the rows discover_structure found, then
    runs the result through aggregate_category_scores exactly like the live
    scoring path does. Raises ValueError if a sub-criterion's score cell is
    blank or not 0/1 -- a hand-filled sheet must follow the same binary
    scoring convention the app itself writes.
    """
    header_row = _find_header_row(ws)
    columns = _resolve_columns(ws, header_row)
    id_col = columns["id"]
    score_col = columns["avg_points"]
    remarks_col = columns["remarks"]

    category_sub_ids = {cid: category["sub_criteria"] for cid, category in categories.items()}
    sub_scores_by_category = {cid: {} for cid in categories}
    for category_id, _category_row, sub_id, sub_row in _iter_positional_sub_rows(ws, header_row, id_col, category_sub_ids):
        score = ws.cell(row=sub_row, column=score_col).value
        if score is None:
            description = descriptions.get(sub_id, sub_id)
            raise ValueError(f"Clause {sub_id} ({description}) has no score filled in.")
        if score not in (0, 1):
            raise ValueError(f"Clause {sub_id} has an invalid score ({score}); expected 0 or 1.")
        remark = ws.cell(row=sub_row, column=remarks_col).value
        sub_scores_by_category[category_id][sub_id] = {"score": score, "remark": remark}

    return {cid: aggregate_category_scores(sub_scores) for cid, sub_scores in sub_scores_by_category.items()}


DATE_STRING_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]


def _parse_review_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in DATE_STRING_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def read_metadata(ws) -> tuple[str, datetime.date]:
    """Mirrors populate_metadata: label-searches for the 'Reviewers:' and
    'Dated:' cells and returns their values (instead of writing to them).
    Raises ValueError if either cell is blank, or the date cell isn't a
    recognizable date (a native Excel date, or a plain YYYY-MM-DD /
    MM/DD/YYYY / DD/MM/YYYY string).
    """
    reviewer_name = None
    review_date = None
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            text = cell.value.strip().lower()
            if text.startswith(REVIEWERS_LABEL):
                value = ws.cell(row=cell.row, column=cell.column + 1).value
                reviewer_name = str(value).strip() if value not in (None, "") else None
            elif text == DATED_LABEL:
                value = ws.cell(row=cell.row, column=cell.column + 1).value
                review_date = _parse_review_date(value)

    if not reviewer_name:
        raise ValueError('Sheet is missing a reviewer name (the "Reviewers:" cell is blank).')
    if review_date is None:
        raise ValueError('Sheet is missing a valid review date (the "Dated:" cell is blank or not a recognizable date).')
    return reviewer_name, review_date
```

Then update the import block at the top of `backend/tests/test_excel_handler.py`:

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    discover_structure,
    generate_review_excel,
    populate_metadata,
    populate_scores,
    read_metadata,
    read_scores,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_excel_handler.py -v`
Expected: all PASS (existing tests plus the 6 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/excel_handler.py backend/tests/test_excel_handler.py
git commit -m "feat: add read_scores/read_metadata for parsing completed review sheets

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `crud.persist_review_result` gains reviewer/approval fields

**Files:**
- Modify: `backend/app/db/crud.py`
- Test: `backend/tests/test_db_crud.py`

**Interfaces:**
- Consumes: `PlatformReview` model (existing, already has `created_by`/`approved_by`/`approved_at` columns), `Project` model (existing).
- Produces:
  - `crud.persist_review_result(..., created_by: Optional[str] = None, approved_by: Optional[str] = None, approved_at: Optional[datetime] = None) -> PlatformReview` — three new optional trailing params on the existing function; all prior call sites unaffected.
  - `crud.get_project(session: AsyncSession, project_id: str) -> Optional[Project]`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_db_crud.py`, after the existing `test_persist_review_result_records_an_error_status` test:

```python
async def test_persist_review_result_stores_reviewer_and_approval_fields(session):
    approved_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
    review = await crud.persist_review_result(
        session,
        review_id="r1",
        project_id=None,
        platform="Android",
        status="approved",
        project_name="MyApp",
        created_at=approved_at,
        completed_at=approved_at,
        total_score_pct=90.0,
        llm_provider="manual_upload",
        llm_model=None,
        compile_check_mode="none",
        source="manual_upload",
        workbook_path=None,
        result_data={"category_scores": []},
        created_by="Jane Doe",
        approved_by="Jane Doe",
        approved_at=approved_at,
    )

    assert review.created_by == "Jane Doe"
    assert review.approved_by == "Jane Doe"
    assert review.approved_at == approved_at


async def test_persist_review_result_defaults_reviewer_and_approval_fields_to_none(session):
    review = await crud.persist_review_result(
        session,
        review_id="r1",
        project_id=None,
        platform="Android",
        status="pending_approval",
        project_name="MyApp",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        total_score_pct=None,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path=None,
        result_data={},
    )

    assert review.created_by is None
    assert review.approved_by is None
    assert review.approved_at is None


async def test_get_project_returns_it_by_id(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")

    project = await crud.get_project(session, "p1")

    assert project.id == "p1"
    assert project.name == "Payments Service"


async def test_get_project_returns_none_when_not_found(session):
    assert await crud.get_project(session, "missing") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_db_crud.py -k "reviewer_and_approval or get_project" -v`
Expected: FAIL — `persist_review_result` raises `TypeError: unexpected keyword argument 'created_by'`; `crud.get_project` doesn't exist (`AttributeError`).

- [ ] **Step 3: Implement**

In `backend/app/db/crud.py`, replace the `persist_review_result` function (currently lines 34-70) with:

```python
async def persist_review_result(
    session: AsyncSession,
    review_id: str,
    project_id: Optional[str],
    platform: str,
    status: str,
    project_name: str,
    created_at: datetime,
    completed_at: Optional[datetime],
    total_score_pct: Optional[float],
    llm_provider: str,
    llm_model: Optional[str],
    compile_check_mode: str,
    source: str,
    workbook_path: Optional[str],
    result_data: dict,
    created_by: Optional[str] = None,
    approved_by: Optional[str] = None,
    approved_at: Optional[datetime] = None,
) -> PlatformReview:
    review = PlatformReview(
        id=review_id,
        project_id=project_id,
        platform=platform,
        status=status,
        project_name=project_name,
        created_at=created_at,
        completed_at=completed_at,
        total_score_pct=total_score_pct,
        llm_provider=llm_provider,
        llm_model=llm_model,
        compile_check_mode=compile_check_mode,
        source=source,
        workbook_path=workbook_path,
        result_data=result_data,
        created_by=created_by,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def get_project(session: AsyncSession, project_id: str) -> Optional[Project]:
    return await session.get(Project, project_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_db_crud.py -v`
Expected: all PASS.

Then run the full backend suite to confirm no other call site broke:

Run: `cd backend && python -m pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/crud.py backend/tests/test_db_crud.py
git commit -m "feat: add reviewer/approval fields to persist_review_result, add get_project

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `POST /api/reviews/upload` endpoint

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: Create `backend/tests/test_reviews_upload.py`

**Interfaces:**
- Consumes: `discover_structure`, `read_scores`, `read_metadata`, `compute_total_score_pct` (from `app.analyzer.excel_handler`), `crud.get_project`, `crud.persist_review_result` (from Tasks 1-2), `_review_artifacts_dir()`, `_review_summary_to_dict(review) -> dict` (all existing in `reviews.py`).
- Produces: `POST /api/reviews/upload` — multipart form (`file`, `projectId`, `platform`) → `200` with the review summary dict (same shape as `GET /api/reviews` list entries) on success; `400`/`404` with `{"detail": "..."}` on any validation failure.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reviews_upload.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_upload.py -v`
Expected: FAIL with `404 Not Found` (route doesn't exist yet) on every test.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/reviews.py`, add `BytesIO` to the imports at the top (after the existing `from pathlib import Path` line):

```python
from io import BytesIO
```

Extend the `excel_handler` import block to include the two new functions:

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    discover_structure,
    generate_review_excel,
    read_metadata,
    read_scores,
)
```

Add the new endpoint directly after `list_review_years` (after the existing `GET /api/reviews/years` route, so both stay grouped with the other list-style review routes and — critically — still stay before any `/api/reviews/{review_id}` route per this file's established route-ordering rule):

```python
@router.post("/api/reviews/upload")
async def upload_completed_review(
    file: UploadFile = File(...),
    projectId: str = Form(...),
    platform: str = Form(...),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx workbook.")

    async with new_session() as session:
        project = await crud.get_project(session, projectId)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    file_bytes = await file.read()
    try:
        wb = load_workbook(BytesIO(file_bytes))
    except Exception:
        raise HTTPException(status_code=400, detail="That file doesn't look like a valid .xlsx workbook.")
    ws = wb.active

    try:
        categories, descriptions = discover_structure(ws)
        scores_by_category = read_scores(ws, categories, descriptions)
        reviewer_name, review_date = read_metadata(ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    category_scores = [
        {
            "id": category_id,
            "name": category["name"],
            "percent_points": scores_by_category[category_id]["percent_points"],
            "sub_criteria": [
                {
                    "id": sub_id,
                    "description": descriptions.get(sub_id),
                    "score": scores_by_category[category_id]["sub_scores"][sub_id]["score"],
                    "remark": scores_by_category[category_id]["sub_scores"][sub_id]["remark"],
                }
                for sub_id in category["sub_criteria"]
            ],
        }
        for category_id, category in categories.items()
    ]
    total_score_pct = compute_total_score_pct(scores_by_category)

    review_id = str(uuid.uuid4())
    artifacts_dir = _review_artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = artifacts_dir / f"{review_id}.xlsx"
    workbook_path.write_bytes(file_bytes)

    review_datetime = datetime.combine(review_date, datetime.min.time(), tzinfo=timezone.utc)

    async with new_session() as session:
        review = await crud.persist_review_result(
            session,
            review_id=review_id,
            project_id=projectId,
            platform=platform,
            status="approved",
            project_name=project.name,
            created_at=review_datetime,
            completed_at=review_datetime,
            total_score_pct=total_score_pct,
            llm_provider="manual_upload",
            llm_model=None,
            compile_check_mode="none",
            source="manual_upload",
            workbook_path=str(workbook_path),
            result_data={"category_scores": category_scores},
            created_by=reviewer_name,
            approved_by=reviewer_name,
            approved_at=review_datetime,
        )

    return _review_summary_to_dict(review)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reviews_upload.py -v`
Expected: all PASS.

Then run the full backend suite:

Run: `cd backend && python -m pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_upload.py
git commit -m "feat: add POST /api/reviews/upload for already-completed review sheets

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `UploadReviewDialog.jsx` and `uploadCompletedReview` API call

**Files:**
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/components/UploadReviewDialog.jsx`
- Test: Create `frontend/src/components/UploadReviewDialog.test.jsx`

**Interfaces:**
- Consumes: `SearchableSelect` (`frontend/src/components/SearchableSelect.jsx`, existing — props `ariaLabel`, `options`, `value`, `onChange`, `placeholder`, `onAddNew`, `addNewLabel`), `ProjectDialog` (`frontend/src/components/ProjectDialog.jsx`, existing — props `title`, `initialName`, `submitLabel`, `onSubmit`, `onClose`), `PLATFORMS` (`frontend/src/platforms.js`, existing — `{id, label, available}[]`), `createProject(name)` (existing, in `api.js`).
- Produces:
  - `uploadCompletedReview({ projectId, platform, file }) -> Promise<object>` in `api.js` — `POST`s to `/api/reviews/upload`, throws the axios error on failure (caller reads `err.response?.data?.detail`).
  - `UploadReviewDialog({ projects, onProjectCreated, onUploaded, onClose })` component — `projects: {id, name}[]`, `onProjectCreated(project)` called after creating a new project inline, `onUploaded()` called (no args) after a successful upload (before `onClose()`), `onClose()` called on Cancel or after a successful upload.

- [ ] **Step 1: Add `uploadCompletedReview` to `api.js`**

Add to `frontend/src/services/api.js`, after the existing `getReviewYears` function (at the end of the file):

```javascript
export async function uploadCompletedReview({ projectId, platform, file }) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("projectId", projectId);
  formData.append("platform", platform);
  const response = await axios.post(`${API_BASE_URL}/reviews/upload`, formData);
  return response.data;
}
```

- [ ] **Step 2: Write the failing component tests**

Create `frontend/src/components/UploadReviewDialog.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadReviewDialog from "./UploadReviewDialog";
import { uploadCompletedReview, createProject } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  uploadCompletedReview: jest.fn(),
  createProject: jest.fn(),
}));

const projects = [{ id: "p1", name: "Payments Service" }];

function renderDialog(overrides = {}) {
  return render(
    <UploadReviewDialog projects={projects} onProjectCreated={jest.fn()} onUploaded={jest.fn()} onClose={jest.fn()} {...overrides} />
  );
}

function selectProject(user) {
  return async () => {
    await user.click(screen.getByRole("button", { name: "Project" }));
    await user.click(screen.getByRole("button", { name: "Payments Service" }));
  };
}

test("platform cards are disabled until a project is chosen", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(uploadCompletedReview).not.toHaveBeenCalled();
});

test("selecting a project, a platform, then a file uploads it and calls onUploaded then onClose", async () => {
  const user = userEvent.setup();
  const onUploaded = jest.fn();
  const onClose = jest.fn();
  uploadCompletedReview.mockResolvedValue({ id: "r1" });
  renderDialog({ onUploaded, onClose });

  await selectProject(user)();
  await user.click(screen.getByRole("button", { name: "Android" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  await waitFor(() => expect(uploadCompletedReview).toHaveBeenCalledWith({ projectId: "p1", platform: "Android", file }));
  await waitFor(() => expect(onUploaded).toHaveBeenCalled());
  expect(onClose).toHaveBeenCalled();
});

test("shows the backend's error message and keeps the dialog open on failure", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  uploadCompletedReview.mockRejectedValue({ response: { data: { detail: "Sheet is missing a reviewer name." } } });
  renderDialog({ onClose });

  await selectProject(user)();
  await user.click(screen.getByRole("button", { name: "iOS" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  expect(await screen.findByText("Sheet is missing a reviewer name.")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

test("creating a project via the dialog selects it for the upload", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p2", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  uploadCompletedReview.mockResolvedValue({ id: "r1" });
  renderDialog({ onProjectCreated });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  await user.click(screen.getByRole("button", { name: ".NET" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  await waitFor(() => expect(uploadCompletedReview).toHaveBeenCalledWith({ projectId: "p2", platform: ".NET", file }));
});

test("clicking Cancel calls onClose", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  renderDialog({ onClose });

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadReviewDialog --watchAll=false`
Expected: FAIL — `Cannot find module './UploadReviewDialog'`.

- [ ] **Step 4: Implement `UploadReviewDialog.jsx`**

Create `frontend/src/components/UploadReviewDialog.jsx`:

```jsx
import { useRef, useState } from "react";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, uploadCompletedReview } from "../services/api";

export default function UploadReviewDialog({ projects, onProjectCreated, onUploaded, onClose }) {
  const [projectId, setProjectId] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [pendingPlatform, setPendingPlatform] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const projectOptions = projects.map((p) => ({ value: p.id, label: p.name }));

  async function handleCreateProject(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    setProjectId(project.id);
  }

  function handleSelectPlatform(platform) {
    if (!projectId || uploading) return;
    setError("");
    setPendingPlatform(platform);
    fileInputRef.current.click();
  }

  async function handleFileChange(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file || !pendingPlatform) return;
    setUploading(true);
    setError("");
    try {
      await uploadCompletedReview({ projectId, platform: pendingPlatform.label, file });
      onUploaded();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload review.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="dialog-title">Upload a completed review</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-4)" }}>
          <div className="field">
            <label htmlFor="uploadReviewProject">Project</label>
            <SearchableSelect
              ariaLabel="Project" options={projectOptions} value={projectId} onChange={setProjectId}
              placeholder="Choose a project…" onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
            />
          </div>

          <div className="field">
            <label>Platform</label>
            <p className="card-body" style={{ marginTop: 0 }}>
              Choose a platform, then pick the filled-in .xlsx review sheet to upload.
            </p>
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              {PLATFORMS.map((platform) => (
                <div
                  key={platform.id}
                  role="button"
                  aria-label={platform.label}
                  tabIndex={0}
                  className="card elev-sm"
                  style={{
                    padding: 16,
                    cursor: projectId && !uploading ? "pointer" : "not-allowed",
                    opacity: projectId ? 1 : 0.5,
                  }}
                  onClick={() => handleSelectPlatform(platform)}
                >
                  <div className="card-title" style={{ fontSize: 16 }}>
                    {platform.label}
                    {uploading && pendingPlatform?.id === platform.id ? " — uploading…" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

          <input
            ref={fileInputRef} type="file" accept=".xlsx" onChange={handleFileChange}
            style={{ display: "none" }} aria-label="Choose review sheet"
          />
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>

      {showCreateDialog && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create"
          onSubmit={handleCreateProject} onClose={() => setShowCreateDialog(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadReviewDialog --watchAll=false`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.js frontend/src/components/UploadReviewDialog.jsx frontend/src/components/UploadReviewDialog.test.jsx
git commit -m "feat: add UploadReviewDialog for uploading completed review sheets

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire "Upload review" into the dashboard

**Files:**
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx`
- Modify: `frontend/src/pages/ProjectDashboardPage.test.jsx`

**Interfaces:**
- Consumes: `UploadReviewDialog` (Task 4).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/pages/ProjectDashboardPage.test.jsx`, after the existing `test("clicking Start review opens the dialog", ...)` test. The file's `jest.mock("../services/api", ...)` block already covers `getReviews` for refetch assertions — no new mock needed since `UploadReviewDialog` itself is exercised in its own test file:

```jsx
test("clicking Upload review opens the upload dialog", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.click(screen.getByRole("button", { name: /upload review/i }));

  expect(screen.getByText("Upload a completed review")).toBeInTheDocument();
});

test("a successful upload refetches reviews for the current filters", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });
  getReviews.mockClear();

  await user.click(screen.getByRole("button", { name: /upload review/i }));
  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(screen.getByRole("button", { name: "Android" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  // getReviews was cleared right before this flow started, so exactly one
  // new call (from the refreshKey bump) is expected here, not a running total.
  await waitFor(() => expect(getReviews).toHaveBeenCalledTimes(1));
  expect(screen.queryByText("Upload a completed review")).not.toBeInTheDocument();
});
```

This second test needs `uploadCompletedReview` mocked to resolve successfully — add it to the file's existing `jest.mock("../services/api", ...)` block and set its resolved value in `beforeEach`:

```javascript
jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getProjects: jest.fn(),
  getReviews: jest.fn(),
  getReviewYears: jest.fn(),
  updateProject: jest.fn(),
  uploadCompletedReview: jest.fn(),
}));
```

```javascript
beforeEach(() => {
  jest.resetAllMocks();
  getProjects.mockResolvedValue(projects);
  getReviewYears.mockResolvedValue([currentYear - 1, currentYear]);
  getReviews.mockResolvedValue([]);
  uploadCompletedReview.mockResolvedValue({ id: "r1" });
});
```

And add `uploadCompletedReview` to the top-of-file import list:

```javascript
import { getProjects, getReviews, getReviewYears, updateProject, uploadCompletedReview } from "../services/api";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/ProjectDashboardPage --watchAll=false`
Expected: FAIL — no "Upload review" button exists yet.

- [ ] **Step 3: Implement**

In `frontend/src/pages/ProjectDashboardPage.jsx`:

Add the import, next to the existing `StartReviewDialog` import:

```javascript
import UploadReviewDialog from "../components/UploadReviewDialog";
```

Add two new pieces of state, next to the existing `startReviewOpen` state:

```javascript
const [uploadReviewOpen, setUploadReviewOpen] = useState(false);
const [refreshKey, setRefreshKey] = useState(0);
```

Update the reviews-fetching effect's dependency array so a successful upload can force a refetch even when the filter values themselves haven't changed — replace:

```javascript
  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    getReviews({ year, platform, projectId })
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setReviews([]); });
    return () => { cancelled = true; };
  }, [year, platform, projectId]);
```

with:

```javascript
  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    getReviews({ year, platform, projectId })
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setReviews([]); });
    return () => { cancelled = true; };
  }, [year, platform, projectId, refreshKey]);
```

Update the header to add the "Upload review" button next to "Start review" — replace:

```jsx
          <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
```

with:

```jsx
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button type="button" className="btn" onClick={() => setUploadReviewOpen(true)}>Upload review</button>
            <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
          </div>
```

Add the dialog's render, next to the existing `StartReviewDialog` render — replace:

```jsx
      {startReviewOpen && (
        <StartReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onClose={() => setStartReviewOpen(false)}
        />
      )}
```

with:

```jsx
      {startReviewOpen && (
        <StartReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onClose={() => setStartReviewOpen(false)}
        />
      )}

      {uploadReviewOpen && (
        <UploadReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onUploaded={() => setRefreshKey((key) => key + 1)}
          onClose={() => setUploadReviewOpen(false)}
        />
      )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/ProjectDashboardPage --watchAll=false`
Expected: all PASS.

Then run the full frontend suite:

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProjectDashboardPage.jsx frontend/src/pages/ProjectDashboardPage.test.jsx
git commit -m "feat: add Upload review button and dialog to the dashboard

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: all PASS.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all PASS.

- [ ] **Step 3: Rebuild and verify the Docker stack**

```bash
docker compose up -d --build backend frontend
```

Then smoke-test against the real running stack:
1. `curl -s -X POST http://localhost:8000/api/projects -H "Content-Type: application/json" -d '{"name": "Upload Smoke Test"}'` — note the returned `id`.
2. Build a completed review `.xlsx` by hand (or reuse `samplefiles/AndroidSampleReview.xlsx`, filled in) and upload it:
   `curl -s -X POST http://localhost:8000/api/reviews/upload -F "file=@samplefiles/AndroidSampleReview.xlsx" -F "projectId=<id from step 1>" -F "platform=Android"`
3. Confirm the response has `"status": "approved"` and a sensible `total_score_pct`.
4. `curl -s "http://localhost:8000/api/reviews?year=<year from the sheet's Dated cell>&project_id=<id from step 1>"` — confirm the uploaded review appears.
5. In the browser, open the dashboard, click "Upload review", and confirm the button and dialog render correctly end-to-end (manual click-through — no browser automation available in this environment).

- [ ] **Step 4: Report results**

Report pass/fail counts for both suites and confirm the smoke test's observed behavior.
