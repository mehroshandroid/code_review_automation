# Upload Completed Review — Design

## Problem

Some code reviews are performed outside the app (by hand, filling in one of
the platform `.xlsx` templates directly) and never enter the database. The
dashboard should let a user upload such an already-completed review sheet
and have it persisted as a normal `PlatformReview` record — reviewer name
and review date read from the sheet itself, platform-appropriate storage
for Android/iOS/.NET/Web.

## Scope

The uploaded file is the *same* platform template the app already reads
(via `discover_structure`) and writes (via `generate_review_excel`) —
filled in by hand: binary 0/1 scores per clause, remarks on failing
clauses, and free-text "Reviewers:"/"Dated:" cells near the bottom (see
`samplefiles/AndroidSampleReview.xlsx` for the concrete shape). No new
sheet format, no code/zip upload, no LLM call, no compile check — this is
pure spreadsheet parsing and DB persistence.

Available for all four platforms (Android/iOS/.NET/Web), including Web —
upload doesn't depend on an automated analyzer existing for that platform,
unlike "Start review".

## Architecture

### Backend: read-side parser, symmetric to the existing write-side

`backend/app/analyzer/excel_handler.py` already has:
- `discover_structure(ws) -> (categories, descriptions)` — finds
  categories/clauses generically from any template, no per-platform
  hardcoding (a category row is any row whose "Avg Points" cell holds a
  pre-existing `=AVERAGE(range)` formula; the range tells it exactly which
  following rows are that category's sub-criteria).
- `populate_scores(ws, category_results)` — **writes** scores/remarks into
  a sheet.
- `populate_metadata(ws, ...)` — **writes** project name, general remarks,
  reviewer name, and date, located by label text search.
- `aggregate_category_scores(sub_scores)` / `compute_total_score_pct(...)`
  — pure scoring math, already used by the live-analysis path.

Two new read-side functions, mirroring the write-side ones exactly:

```python
def read_scores(ws, categories: dict) -> dict:
    """Mirrors populate_scores: reads each sub-criterion's score/remark
    cell (instead of writing them) for the rows discover_structure found,
    then runs them through aggregate_category_scores exactly like the live
    scoring path does. Raises ValueError if a sub-criterion's score cell is
    blank or not 0/1."""

def read_metadata(ws) -> tuple[str, datetime.date]:
    """Mirrors populate_metadata: label-searches for the 'Reviewers:' and
    'Dated:' cells and returns their values (instead of writing to them).
    Raises ValueError if either cell is blank, or the date cell isn't a
    recognizable date (a native Excel date, or a plain string in
    YYYY-MM-DD / MM/DD/YYYY / DD/MM/YYYY)."""
```

`read_scores` reuses `_iter_positional_sub_rows` and `aggregate_category_scores`
directly — no duplicated scoring math.

### Backend: new endpoint

`POST /api/reviews/upload` (multipart form: `file`, `projectId`, `platform`)
in `backend/app/api/reviews.py`, next to the existing review endpoints.
Fully synchronous (unlike `POST /api/reviews`, which kicks off a background
`asyncio.create_task` for the async analysis pipeline) — there's no
long-running work here, so no polling/status endpoint is needed.

Flow:
1. Validate `file.filename` ends in `.xlsx`; reject otherwise (400).
2. `load_workbook(BytesIO(await file.read()))` — reject with a clear 400
   message if openpyxl can't open it ("That file doesn't look like a valid
   .xlsx workbook.").
3. `categories, descriptions = discover_structure(ws)` — propagates
   `discover_structure`'s own `ValueError` message (e.g. "Could not find a
   header row...") as a 400 on failure.
4. `scores_by_category = read_scores(ws, categories)` — 400 on any
   `ValueError` (blank/invalid score cell).
5. `reviewer_name, review_date = read_metadata(ws)` — 400 on any
   `ValueError` (blank reviewer, blank/unparseable date).
6. Build the same `category_scores` list shape the automated flow produces
   (`[{"id", "name", "percent_points", "sub_criteria": [{"id",
   "description", "score", "remark"}, ...]}, ...]`), and
   `total_score_pct = compute_total_score_pct(scores_by_category)`.
7. Look up the project by `projectId` (404 if not found) for its
   `project_name`.
8. Persist the uploaded file itself as the review's workbook (copy into
   `_review_artifacts_dir() / f"{review_id}.xlsx"`, same convention as the
   automated flow) — so the existing `GET /api/reviews/{id}/download`
   endpoint works unchanged for uploaded reviews too.
9. `crud.persist_review_result(..., created_by=reviewer_name,
   approved_by=reviewer_name, approved_at=review_date_as_datetime)` — a new
   call this function doesn't make today; see below.

### Backend: persistence

`crud.persist_review_result` (in `backend/app/db/crud.py`) gains three new
**optional** parameters — `created_by`, `approved_by`, `approved_at`, all
defaulting to `None` — so every existing call site is unaffected. The new
endpoint is the only caller that passes them.

Field values for an uploaded review:
- `status = "approved"` — already scored and signed off externally, no
  extra in-app confirmation step (per your answer).
- `source = "manual_upload"` — a new value; `source` and `llm_provider`
  are plain `String` columns with no DB-level allow-list, so this doesn't
  require a migration or touch existing "upload"/"devops" semantics (those
  describe how *code* was ingested for an automated review — unrelated
  concept).
- `llm_provider = "manual_upload"`, `llm_model = None`,
  `compile_check_mode = "none"` — no analysis ran.
- `created_at = completed_at = approved_at = <review_date from the sheet,
  interpreted as UTC midnight>` — the record is dated when the review
  actually happened (drives the dashboard's Year filter and date column),
  not when it was uploaded, per your answer.
- `created_by = approved_by = <reviewer_name from the sheet>` — free text,
  verbatim from the cell (may be one name or several comma-separated
  names; no parsing/splitting).
- `result_data = {"category_scores": [...]}` — other keys the automated
  flow writes (`warnings`, `secrets_found`, `lint_issues`,
  `compile_status`, `stats`) are omitted; every read site already does
  `result_data.get(key, default)`, confirmed in `reviews.py`, so this is
  safe and doesn't need placeholder empty values.

### Frontend

New `frontend/src/components/UploadReviewDialog.jsx`, sibling to
`StartReviewDialog.jsx`, reusing `SearchableSelect`, `ProjectDialog`, and
the `PLATFORMS` constant (all four platforms enabled here, unlike Start
Review's `platform.available` gate). Flow: pick project → pick platform →
a file input appears/triggers for the `.xlsx` → on file selection,
immediately `POST` to `/api/reviews/upload` with a loading state. On
success: close the dialog (the page's existing filtered-reviews fetch
picks the new review up naturally next time its filters match — no
special-case refresh logic needed). On failure: show the backend's error
`detail` string inline in the dialog and keep it open so the user can pick
a different file without restarting project/platform selection.

`frontend/src/services/api.js` gains `uploadCompletedReview({ projectId,
platform, file })`, mirroring the existing `sendChatMessage`/`getReviews`
style.

`ProjectDashboardPage.jsx`: an "Upload review" button next to the existing
"Start review" button in the header, opening `UploadReviewDialog`.

## Error handling summary

All rejections are `HTTPException(status_code=400, detail="<message>")`,
matching this file's existing convention (e.g. `reviews.py:601`):

| Condition | Message |
|---|---|
| Filename doesn't end `.xlsx` | "File must be an .xlsx workbook." |
| openpyxl can't open it | "That file doesn't look like a valid .xlsx workbook." |
| No header row / no categories found | (propagated verbatim from `discover_structure`) |
| A sub-criterion's score cell is blank | "Clause {sub_id} ({description}) has no score filled in." |
| A sub-criterion's score isn't 0 or 1 | "Clause {sub_id} has an invalid score ({value}); expected 0 or 1." |
| "Reviewers:" cell blank | "Sheet is missing a reviewer name (the \"Reviewers:\" cell is blank)." |
| "Dated:" cell blank or unparseable | "Sheet is missing a valid review date (the \"Dated:\" cell is blank or not a recognizable date)." |
| `projectId` doesn't match a project | 404 "Project not found." |

## Testing

Backend: unit tests for `read_scores`/`read_metadata` against real
in-memory workbooks built with openpyxl (mirroring the existing
`discover_structure`/`populate_scores` test style), plus endpoint tests
using the existing sample fixture
(`backend/tests/fixtures/SampleCodeReview.xlsx`) for the happy path and
deliberately-broken variants (blank score cell, blank reviewer cell,
unparseable date) for each error case.

Frontend: `UploadReviewDialog.test.jsx` covering project/platform
selection gating the file input, successful upload closing the dialog,
and a failed upload showing the inline error and staying open — following
the same patterns as `StartReviewDialog.test.jsx`.
