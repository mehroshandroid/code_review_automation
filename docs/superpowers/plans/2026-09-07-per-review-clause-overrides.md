# Per-Review Clause Checklist Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reviewer/admin see the org-wide clause checklist defaults for the specific template a review will use, and override some of them just for that one run -- never persisted, never affecting any other review.

**Architecture:** A new read-only endpoint (`POST /api/reviews/clause-preview`) mirrors the existing sample-template preview logic to return this review's actual clause list merged with current org-wide guidance text. `POST /api/reviews` gains one optional form field carrying only the clauses the reviewer actually changed; `_run_review` merges those on top of the org-wide dict at the exact point it already builds one, so `score_category` needs no changes at all.

**Tech Stack:** FastAPI, SQLAlchemy (async), openpyxl, React.

**Spec:** `docs/superpowers/specs/2026-09-07-per-review-clause-overrides-design.md`

## Global Constraints

- Editor lives on the platform review page (`AndroidReviewFlow.jsx` -- the single component used for Android/iOS/.NET, parameterized by a `platform` prop; there is no separate per-platform flow file), inside `UploadForm.jsx`, not in `StartReviewDialog`.
- Partial override: only clauses the reviewer actually edits are sent; everything else keeps org defaults, exactly like today. Clearing a field to blank counts as an edit.
- Reviewer + admin only -- both the new preview endpoint and the override field on `POST /api/reviews` (enforced server-side, not just hidden in the UI).
- Nothing is persisted. The override is form state that travels with one `POST /api/reviews` request and is then gone.
- `_run_review`'s merge must apply even when the org-wide load fails (DB outage) -- the override came in on the request itself, no DB round-trip needed for it.

---

### Task 1: `POST /api/reviews/clause-preview` endpoint

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: Create `backend/tests/test_reviews_clause_preview.py`

**Interfaces:**
- Consumes: `_resolve_excel_template(file, platform) -> tuple[bytes|None, str|None]`, `discover_structure(worksheet) -> (categories, descriptions)`, `_load_clause_checklists() -> dict[(platform, sub_id), str]`, `require_roles` (all existing, already imported in this file).
- Produces: `POST /api/reviews/clause-preview` -- multipart form (`platform`, optional `file`) -> `200` with `{"categories": [{"id", "name", "sub_criteria": [{"id", "description", "checklist_text"}]}]}`; `404` if no template available; `422` if the sheet can't be parsed; `403` for non-reviewer/admin roles.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reviews_clause_preview.py`:

```python
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_clause_preview.py -v`
Expected: FAIL with 404s (route doesn't exist yet).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/reviews.py`, add directly after the existing `upload_completed_review` endpoint (keeps the three "start/preview/upload" POST routes grouped together):

```python
@router.post("/api/reviews/clause-preview")
async def clause_preview(
    platform: str = Form(...),
    file: UploadFile | None = File(None),
    user=Depends(require_roles("admin", "reviewer")),
):
    template_bytes, _ = await _resolve_excel_template(file, platform)
    if template_bytes is None:
        raise HTTPException(status_code=404, detail="No sample template configured for this platform and no file uploaded.")

    try:
        worksheet = load_workbook(BytesIO(template_bytes)).active
        categories, descriptions = discover_structure(worksheet)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read this sheet's clause structure")

    clause_checklists = await _load_clause_checklists()

    return {
        "categories": [
            {
                "id": category_id,
                "name": category["name"],
                "sub_criteria": [
                    {
                        "id": sub_id,
                        "description": descriptions.get(sub_id, ""),
                        "checklist_text": clause_checklists.get((platform, sub_id)),
                    }
                    for sub_id in category["sub_criteria"]
                ],
            }
            for category_id, category in categories.items()
        ]
    }
```

Add `require_roles` to the existing auth import line:

```python
from app.auth.dependencies import get_current_user, require_roles
```

(This import already exists in the file with just `get_current_user` -- extend it, don't duplicate the line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_clause_preview.py -v`
Expected: all PASS.

Then the full backend suite:

Run: `cd backend && source venv/bin/activate && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_clause_preview.py
git commit -m "feat: add clause-preview endpoint for per-review checklist overrides

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `POST /api/reviews` accepts per-review overrides; `_run_review` merges them

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: `backend/tests/test_reviews_create.py`
- Test: `backend/tests/test_reviews_clause_checklists.py`

**Interfaces:**
- Consumes: `_load_clause_checklists` (existing).
- Produces: `POST /api/reviews` gains `clauseChecklistOverrides: str | None` (Form, JSON object string `{sub_id: text}`) -- malformed JSON or a non-reviewer/admin role submitting it both become the existing `input_error` 200-with-error-state response (matching this endpoint's established error convention, not an HTTP error status). `_run_review(...)` gains `clause_overrides: dict[str, str] | None = None` -- merged onto the org-wide dict before scoring.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reviews_clause_checklists.py` (it already has `_build_dotnet_zip_bytes`, `_build_xlsx_bytes`, and the `test_run_review_passes_loaded_checklists_through_to_score_category` test to pattern-match):

```python
async def test_run_review_merges_per_review_overrides_onto_org_checklists(monkeypatch):
    review_id = "override-merge-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "project.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_load_clause_checklists():
        return {(".NET", "1.1"): "Org default for 1.1"}

    captured_checklists = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_checklists.append(checklists)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_dotnet_build_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_dotnet_build_warnings", fake_check_dotnet_build_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform=".NET", clause_overrides={"1.1": "Reviewer's override for this run only"},
    )

    # The override wins for 1.1; nothing else in the org dict is touched.
    assert captured_checklists == [{(".NET", "1.1"): "Reviewer's override for this run only"}]


async def test_run_review_override_still_applies_when_org_checklist_load_fails(monkeypatch):
    review_id = "override-survives-db-outage"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "project.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_load_clause_checklists():
        return {}  # matches the real function's DB-outage-safe empty-dict behavior

    captured_checklists = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_checklists.append(checklists)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_dotnet_build_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_dotnet_build_warnings", fake_check_dotnet_build_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform=".NET", clause_overrides={"1.1": "Reviewer's override"},
    )

    assert captured_checklists == [{(".NET", "1.1"): "Reviewer's override"}]
```

Add to `backend/tests/test_reviews_create.py` (it already has `_build_zip_bytes` and `_build_xlsx_bytes` helpers):

```python
def test_create_review_rejects_malformed_clause_overrides_json(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
            data={"clauseChecklistOverrides": "not valid json"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        state = reviews_module._reviews[body["review_id"]]
        assert "clauseChecklistOverrides must be valid JSON" in state["error"]


def test_create_review_rejects_clause_overrides_from_a_non_privileged_role(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    non_privileged = User(id="u1", email="u@example.com", role="user", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: non_privileged
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/reviews",
                files={
                    "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                    "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                },
                data={"clauseChecklistOverrides": '{"1.1": "text"}'},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "error"
            state = reviews_module._reviews[body["review_id"]]
            assert "Only admin/reviewer accounts" in state["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

This second test needs two new imports at the top of `backend/tests/test_reviews_create.py`:

```python
from app.auth.dependencies import get_current_user
from app.db.models import User
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_clause_checklists.py tests/test_reviews_create.py -v -k "override"`
Expected: FAIL -- `_run_review()` raises `TypeError: unexpected keyword argument 'clause_overrides'`; the two new `create_review` tests get a 200 with `status: "processing"` instead of the expected error (the field is silently ignored today).

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, add `import json` to the top-level imports (alongside the existing `import asyncio` etc.).

Update `_run_review`'s signature -- add one parameter at the end of the existing list:

```python
async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
    project_name: str,
    llm_provider: str = "azure",
    ollama_model: str | None = None,
    compile_check_mode: str = "compiler",
    platform: str = "Android",
    devops_repo_url: str | None = None,
    devops_pat: str | None = None,
    devops_branch: str | None = None,
    project_id: str | None = None,
    clause_overrides: dict | None = None,
) -> None:
```

Find the existing line `clause_checklists = await _load_clause_checklists()` (inside `_run_review`, right before the per-category scoring loop) and add the merge directly after it:

```python
        clause_checklists = await _load_clause_checklists()
        for sub_id, text in (clause_overrides or {}).items():
            clause_checklists[(platform, sub_id)] = text
```

In `create_review`, add the new parameter to the signature (right before the existing `user=Depends(get_current_user)` line):

```python
    clauseChecklistOverrides: str | None = Form(None),
    user=Depends(get_current_user),
```

Find the existing block:

```python
    if has_zip and has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."
    elif not has_zip and not has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."
    else:
        input_error = None
```

and replace it with:

```python
    if has_zip and has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."
    elif not has_zip and not has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."
    else:
        input_error = None

    clause_overrides: dict = {}
    if input_error is None and clauseChecklistOverrides:
        if user.role not in ("admin", "reviewer"):
            input_error = "Only admin/reviewer accounts can adjust clause guidance for a review."
        else:
            try:
                clause_overrides = json.loads(clauseChecklistOverrides)
            except json.JSONDecodeError:
                input_error = "clauseChecklistOverrides must be valid JSON."
```

Find the `asyncio.create_task(...)` call at the end of `create_review`:

```python
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode, platform,
            devopsRepoUrl, devopsPat, devopsBranch, project_id=projectId,
        )
    )
```

and add the new argument:

```python
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode, platform,
            devopsRepoUrl, devopsPat, devopsBranch, project_id=projectId, clause_overrides=clause_overrides,
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_clause_checklists.py tests/test_reviews_create.py -v`
Expected: all PASS.

Then the full backend suite:

Run: `cd backend && source venv/bin/activate && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_clause_checklists.py
git commit -m "feat: accept and apply per-review clause checklist overrides

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend API client

**Files:**
- Modify: `frontend/src/services/api.js`

**Interfaces:**
- Produces: `getClausePreview({ platform, file }) -> Promise<Array<{id, name, sub_criteria: [{id, description, checklist_text}]}>>`; `createReview(...)` gains an 11th positional parameter `clauseChecklistOverrides` (a plain object, or falsy).

- [ ] **Step 1: Implement**

In `frontend/src/services/api.js`, replace the existing `createReview` function:

```javascript
export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch, projectId
) {
  const formData = new FormData();
  if (androidZip) formData.append("androidZip", androidZip);
  if (excelTemplate) formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  if (devopsRepoUrl) formData.append("devopsRepoUrl", devopsRepoUrl);
  if (devopsPat) formData.append("devopsPat", devopsPat);
  if (devopsBranch) formData.append("devopsBranch", devopsBranch);
  if (projectId) formData.append("projectId", projectId);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

with:

```javascript
export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch, projectId, clauseChecklistOverrides
) {
  const formData = new FormData();
  if (androidZip) formData.append("androidZip", androidZip);
  if (excelTemplate) formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  if (devopsRepoUrl) formData.append("devopsRepoUrl", devopsRepoUrl);
  if (devopsPat) formData.append("devopsPat", devopsPat);
  if (devopsBranch) formData.append("devopsBranch", devopsBranch);
  if (projectId) formData.append("projectId", projectId);
  if (clauseChecklistOverrides && Object.keys(clauseChecklistOverrides).length > 0) {
    formData.append("clauseChecklistOverrides", JSON.stringify(clauseChecklistOverrides));
  }
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}

export async function getClausePreview({ platform, file }) {
  const formData = new FormData();
  formData.append("platform", platform);
  if (file) formData.append("file", file);
  const response = await axios.post(`${API_BASE_URL}/reviews/clause-preview`, formData);
  return response.data.categories;
}
```

- [ ] **Step 2: Run the full frontend suite to confirm nothing broke**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all PASS (purely additive -- `createReview`'s existing 10 positional args are unchanged, the 11th is new and optional).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.js
git commit -m "feat: add getClausePreview and thread overrides through createReview

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `ClauseGuidanceEditor` component

**Files:**
- Create: `frontend/src/components/ClauseGuidanceEditor.jsx`
- Test: `frontend/src/components/ClauseGuidanceEditor.test.jsx`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure presentational component over the shape `getClausePreview` returns).
- Produces: `ClauseGuidanceEditor({ categories, onChange })` -- `categories: Array<{id, name, sub_criteria: [{id, description, checklist_text}]}>`; calls `onChange(overrides)` with `overrides: {sub_id: text}` containing only the fields that currently differ from their original `checklist_text` (blank counts as `""`, differing from a non-blank original).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ClauseGuidanceEditor.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ClauseGuidanceEditor from "./ClauseGuidanceEditor";

const categories = [
  {
    id: "1", name: "Code naming conventions / Code Structure",
    sub_criteria: [
      { id: "1.1", description: "Clear and consistent naming", checklist_text: "Check for camelCase" },
      { id: "1.2", description: "Clean structure and formatting", checklist_text: null },
    ],
  },
];

test("renders each clause's description and pre-fills the org default text", () => {
  render(<ClauseGuidanceEditor categories={categories} onChange={jest.fn()} />);

  expect(screen.getByText(/Clear and consistent naming/)).toBeInTheDocument();
  expect(screen.getByLabelText(/1\.1/)).toHaveValue("Check for camelCase");
  expect(screen.getByLabelText(/1\.2/)).toHaveValue("");
});

test("editing one clause's text reports only that clause as an override", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  await user.type(screen.getByLabelText(/1\.2/), "Check for retry logic");

  expect(onChange).toHaveBeenLastCalledWith({ "1.2": "Check for retry logic" });
});

test("clearing a field that had a default counts as an override", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  await user.clear(screen.getByLabelText(/1\.1/));

  expect(onChange).toHaveBeenLastCalledWith({ "1.1": "" });
});

test("retyping a field back to its original value removes it from the overrides", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  const field = screen.getByLabelText(/1\.1/);
  await user.type(field, "x");
  await user.type(field, "{backspace}");

  expect(onChange).toHaveBeenLastCalledWith({});
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/ClauseGuidanceEditor --watchAll=false`
Expected: FAIL -- `Cannot find module './ClauseGuidanceEditor'`.

- [ ] **Step 3: Implement**

Create `frontend/src/components/ClauseGuidanceEditor.jsx`:

```jsx
import { useState } from "react";

export default function ClauseGuidanceEditor({ categories, onChange }) {
  const [values, setValues] = useState({});

  function handleChange(subId, newText) {
    const next = { ...values, [subId]: newText };
    setValues(next);

    const overrides = {};
    for (const category of categories) {
      for (const sub of category.sub_criteria) {
        if (sub.id in next) {
          const original = sub.checklist_text || "";
          if (next[sub.id] !== original) overrides[sub.id] = next[sub.id];
        }
      }
    }
    onChange(overrides);
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      {categories.map((category) => (
        <div key={category.id}>
          <div className="card-kicker-muted" style={{ marginBottom: "var(--space-2)" }}>{category.name}</div>
          <div style={{ display: "grid", gap: "var(--space-3)" }}>
            {category.sub_criteria.map((sub) => {
              const original = sub.checklist_text || "";
              const currentValue = sub.id in values ? values[sub.id] : original;
              return (
                <div className="field" key={sub.id}>
                  <label htmlFor={`clauseGuidance-${sub.id}`}>{sub.id} — {sub.description}</label>
                  <textarea
                    id={`clauseGuidance-${sub.id}`}
                    className="input"
                    rows={2}
                    value={currentValue}
                    onChange={(event) => handleChange(sub.id, event.target.value)}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/ClauseGuidanceEditor --watchAll=false`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ClauseGuidanceEditor.jsx frontend/src/components/ClauseGuidanceEditor.test.jsx
git commit -m "feat: add ClauseGuidanceEditor component

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire the editor into `UploadForm.jsx` and `AndroidReviewFlow.jsx`

**Files:**
- Modify: `frontend/src/components/UploadForm.jsx`
- Modify: `frontend/src/pages/AndroidReviewFlow.jsx`
- Test: `frontend/src/components/UploadForm.test.jsx`
- Test: `frontend/src/pages/AndroidReviewFlow.test.jsx`

**Interfaces:**
- Consumes: `getClausePreview` (Task 3), `ClauseGuidanceEditor` (Task 4), `useAuth` (existing, `frontend/src/context/AuthContext.jsx`).
- Produces: `UploadForm`'s `onSubmit` payload gains a `clauseChecklistOverrides` field (an object, possibly empty); `AndroidReviewFlow`'s `handleUpload` forwards it into `createReview(...)`.

This task touches two existing, well-established test files. Both currently pass `<UploadForm>`/`<AndroidReviewFlow>` no `AuthContext.Provider` at all, which means every existing test in them already gets `AuthContext`'s default context value -- `{role: "admin", ...}` (see Task 12 of the auth-rbac plan) -- so the new "Adjust clause guidance" button will render in every existing test in both files once this task lands. That's harmless by itself, but three tests in `UploadForm.test.jsx` assert `onSubmit` was called with an *exact* object literal, and six tests in `AndroidReviewFlow.test.jsx` assert `createReview` was called with an *exact* positional argument list -- both need the new field/argument added or they'll fail once `UploadForm` always includes `clauseChecklistOverrides` in its payload. This step updates those alongside adding the new tests.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/UploadForm.test.jsx`, change the import block:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";
import { getSampleTemplates } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getSampleTemplates: jest.fn(),
}));
```

to:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";
import { AuthContext } from "../context/AuthContext";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";
import { getSampleTemplates, getClausePreview } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getSampleTemplates: jest.fn(),
  getClausePreview: jest.fn(),
}));
```

Add to the `beforeEach`, so `getClausePreview` starts clean for every test the same way `getSampleTemplates` already does:

```javascript
beforeEach(() => {
  localStorage.clear();
  getSampleTemplates.mockReset();
  getSampleTemplates.mockResolvedValue([]);
  getClausePreview.mockReset();
});
```

Fix the three existing exact-object `onSubmit` assertions -- each currently expects a 5-key object; add the new field. The first is in `test("calls onSubmit with both files when extensions are valid", ...)`. Change:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: xlsx, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
  });
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
```

to:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: xlsx, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
    clauseChecklistOverrides: {},
  });
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
```

The second is in `test("calls onSubmit with the DevOps fields (and a null androidZip) in DevOps mode", ...)`. Change:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: null,
    excelTemplate: xlsx,
    devopsRepoUrl: "https://dev.azure.com/myorg/MyProject/_git/my-repo",
    devopsPat: "fake-pat",
    devopsBranch: "release/1.0",
  });
});
```

to:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: null,
    excelTemplate: xlsx,
    devopsRepoUrl: "https://dev.azure.com/myorg/MyProject/_git/my-repo",
    devopsPat: "fake-pat",
    devopsBranch: "release/1.0",
    clauseChecklistOverrides: {},
  });
});
```

The third is in `test("submits with excelTemplate: null when the default template is used", ...)`. Change:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: null, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
  });
});
```

to:

```jsx
  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: null, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
    clauseChecklistOverrides: {},
  });
});
```

Now add the new tests, at the end of the file (after the last existing test, `"'Use default instead' reverts back to the default after choosing a different file"`):

```jsx
function renderAsRole(role, props = {}) {
  const value = { user: { id: "u1", email: "a@example.com", role }, loading: false, login: jest.fn(), logout: jest.fn() };
  return render(
    <AuthContext.Provider value={value}>
      <UploadForm onSubmit={jest.fn()} platformLabel="Android" {...props} />
    </AuthContext.Provider>
  );
}

test("hides the clause guidance section for the user role", () => {
  renderAsRole("user");
  expect(screen.queryByRole("button", { name: /adjust clause guidance/i })).not.toBeInTheDocument();
});

test("reviewer can expand the clause guidance section, pre-filled from the preview endpoint", async () => {
  const user = userEvent.setup();
  getClausePreview.mockResolvedValue([
    { id: "1", name: "Code Structure", sub_criteria: [{ id: "1.1", description: "Clear naming", checklist_text: "Org default text" }] },
  ]);
  renderAsRole("reviewer");

  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.click(screen.getByRole("button", { name: /adjust clause guidance/i }));

  expect(await screen.findByLabelText(/1\.1/)).toHaveValue("Org default text");
  expect(getClausePreview).toHaveBeenCalledWith({ platform: "Android", file: null });
});

test("submitting with an edited clause includes it in clauseChecklistOverrides, and leaves other clauses out", async () => {
  const user = userEvent.setup();
  getClausePreview.mockResolvedValue([
    {
      id: "1", name: "Code Structure",
      sub_criteria: [
        { id: "1.1", description: "Clear naming", checklist_text: "Org default" },
        { id: "1.2", description: "Clean structure", checklist_text: "Untouched default" },
      ],
    },
  ]);
  const onSubmit = jest.fn();
  renderAsRole("admin", { onSubmit });

  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.click(screen.getByRole("button", { name: /adjust clause guidance/i }));
  const field = await screen.findByLabelText(/1\.1/);
  await user.clear(field);
  await user.type(field, "Custom guidance for this run");
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    clauseChecklistOverrides: { "1.1": "Custom guidance for this run" },
  }));
});
```

These three tests rely on `getSampleTemplates.mockResolvedValue([])` (already the `beforeEach` default), so `usingDefaultTemplate` is `false` and the zip/template pickers behave exactly like the file's very first test (`"calls onSubmit with both files when extensions are valid"`) -- no separate stubbing convention introduced.

In `frontend/src/pages/AndroidReviewFlow.test.jsx`, add `getClausePreview` to the existing mock. Change:

```jsx
import { createReview, getProgress, getOllamaModels, getSampleTemplates } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
  getOllamaModels: jest.fn(),
  getSampleTemplates: jest.fn(),
}));
```

to:

```jsx
import { createReview, getProgress, getOllamaModels, getSampleTemplates, getClausePreview } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
  getOllamaModels: jest.fn(),
  getSampleTemplates: jest.fn(),
  getClausePreview: jest.fn(),
}));
```

Six existing tests assert `createReview` was called with an exact 10-argument list; each needs `, {}` appended as the 11th argument (this file's `beforeEach` never touches the clause editor, so `clauseOverrides` stays at its `{}` initial state for all of them). Change each of these six lines:

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android", null, null, null, "proj-1");
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler", "Android", null, null, null, null);
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android", null, null, null, null);
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static", "Android", null, null, null, null);
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "AndroidCustom", null, null, null, null);
```
```jsx
  expect(createReview).toHaveBeenCalledWith(
    null, xlsx, "azure", null, "compiler", "Android",
    "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", null, null
  );
```

to (respectively):

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android", null, null, null, "proj-1", {});
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler", "Android", null, null, null, null, {});
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android", null, null, null, null, {});
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static", "Android", null, null, null, null, {});
```
```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "AndroidCustom", null, null, null, null, {});
```
```jsx
  expect(createReview).toHaveBeenCalledWith(
    null, xlsx, "azure", null, "compiler", "Android",
    "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", null, null, {}
  );
```

Add this new test at the end of the file, after `"sends devops fields through to createReview when starting a review in DevOps mode"`:

```jsx
test("forwards an edited clause guidance override through to createReview", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  getClausePreview.mockResolvedValue([
    { id: "1", name: "Code Structure", sub_criteria: [{ id: "1.1", description: "Clear naming", checklist_text: "Org default" }] },
  ]);
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);

  await user.click(screen.getByRole("button", { name: /adjust clause guidance/i }));
  const field = await screen.findByLabelText(/1\.1/);
  await user.clear(field);
  await user.type(field, "Custom guidance for this run");

  await act(async () => {
    await user.click(screen.getByRole("button", { name: /start review/i }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(
    zip, xlsx, "azure", null, "compiler", "Android", null, null, null, null,
    { "1.1": "Custom guidance for this run" },
  );
});
```

(`getSampleTemplates.mockResolvedValue([])` is already this file's `beforeEach` default, so `usingDefaultTemplate` is `false` and the effective file passed to `getClausePreview` is the uploaded `xlsx`, matching how every other test in this file already uploads its own template rather than relying on a stored default.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm src/pages/AndroidReviewFlow --watchAll=false`
Expected: FAIL -- the three fixed-up `UploadForm` assertions and six fixed-up `AndroidReviewFlow` assertions now expect a `clauseChecklistOverrides`/11th-argument value the code doesn't send yet; the new "Adjust clause guidance" tests fail because that button doesn't exist yet.

- [ ] **Step 3: Implement `UploadForm.jsx`**

Add imports:

```javascript
import { useAuth } from "../context/AuthContext";
import ClauseGuidanceEditor from "./ClauseGuidanceEditor";
import { getCompileCheckMode, setCompileCheckMode } from "../services/compileCheckModeStorage";
import { getSampleTemplates, getClausePreview } from "../services/api";
```

(This replaces the existing `import { getSampleTemplates } from "../services/api";` line -- add `getClausePreview` to it.)

Inside the component, add new state and the fetch effect right after the existing `defaultTemplate`/`useOwnTemplate` effect:

```javascript
  const { user } = useAuth();
  const canAdjustClauses = user?.role === "admin" || user?.role === "reviewer";
  const [showClauseEditor, setShowClauseEditor] = useState(false);
  const [clauseCategories, setClauseCategories] = useState(null);
  const [clauseOverrides, setClauseOverrides] = useState({});

  useEffect(() => {
    if (!canAdjustClauses || !showClauseEditor) return;
    const effectiveFile = usingDefaultTemplate ? null : excelTemplate;
    if (!usingDefaultTemplate && !excelTemplate) {
      setClauseCategories(null);
      return;
    }
    let cancelled = false;
    setClauseOverrides({});
    getClausePreview({ platform: platformLabel, file: effectiveFile })
      .then((categories) => { if (!cancelled) setClauseCategories(categories); })
      .catch(() => { if (!cancelled) setClauseCategories(null); });
    return () => { cancelled = true; };
  }, [canAdjustClauses, showClauseEditor, usingDefaultTemplate, excelTemplate, platformLabel]);
```

Update `handleSubmit`'s `onSubmit({...})` call:

```javascript
    onSubmit({
      androidZip: sourceMode === "upload" ? androidZip : null,
      excelTemplate: usingDefaultTemplate ? null : excelTemplate,
      devopsRepoUrl: sourceMode === "devops" ? devopsRepoUrl : null,
      devopsPat: sourceMode === "devops" ? devopsPat : null,
      devopsBranch: sourceMode === "devops" ? (devopsBranch || null) : null,
      clauseChecklistOverrides: clauseOverrides,
    });
```

Add the section's markup right before the closing `{validationError && ...}` block (i.e. after the existing template-selection `<div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", ... }}>...</div>` block, before the `showCompileCheckToggle` block):

```jsx
      {canAdjustClauses && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setShowClauseEditor((current) => !current)}
          >
            {showClauseEditor ? "Hide" : "Adjust"} clause guidance for this review
          </button>
          {showClauseEditor && clauseCategories && (
            <div style={{ marginTop: "var(--space-3)" }}>
              <ClauseGuidanceEditor categories={clauseCategories} onChange={setClauseOverrides} />
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 4: Implement `AndroidReviewFlow.jsx`**

Update `handleUpload`'s destructured parameter and the `createReview` call:

```javascript
  const handleUpload = useCallback(async ({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch, clauseChecklistOverrides }) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const models = await getOllamaModels().catch(() => []);
      const storedProvider = getLlmProvider();
      const effectiveProvider = storedProvider === "ollama" && models.length === 0 ? "azure" : storedProvider;
      const effectiveModel = effectiveProvider === "ollama" ? getOllamaModel() : null;
      const compileCheckMode = getCompileCheckMode();
      setReviewMeta({
        llmProvider: effectiveProvider,
        llmModel: effectiveModel,
        source: devopsRepoUrl ? "devops" : "upload",
        compileCheckMode,
      });

      const result = await createReview(
        androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode, platform.label,
        devopsRepoUrl, devopsPat, devopsBranch, projectId, clauseChecklistOverrides
      );
```

(Only the function's parameter list and the `createReview(...)` call change -- everything else in `handleUpload` stays exactly as-is.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm src/pages/AndroidReviewFlow --watchAll=false`
Expected: all PASS.

Then the full frontend suite:

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all PASS -- every other existing test that renders `UploadForm`/`AndroidReviewFlow` gets the default admin user from `AuthContext`'s default context value, so the new section renders for them too, but no existing assertion asserts the form has *only* specific content, so nothing should break.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx frontend/src/pages/AndroidReviewFlow.jsx frontend/src/pages/AndroidReviewFlow.test.jsx
git commit -m "feat: wire per-review clause guidance editor into the review flow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all PASS.

- [ ] **Step 3: Rebuild and verify the Docker stack**

```bash
docker compose up -d --build backend frontend
```

- [ ] **Step 4: Live smoke test**

Log in as the seeded admin, then:

```bash
curl -s -c /tmp/admin_cookies.txt -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "change-me-please"}' -o /dev/null

curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8000/api/reviews/clause-preview \
  -F "platform=Android"
```

Expected: `200` with a `categories` array if a default Android template is configured, or `404` "No sample template configured for this platform and no file uploaded." if none is -- both are correct outcomes; confirm whichever matches this stack's actual configured templates.

Then confirm the `user` role is rejected:

```bash
curl -s -c /tmp/user_cookies.txt -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email": "reader@example.com", "password": "correct horse battery"}' -o /dev/null
curl -s -b /tmp/user_cookies.txt -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/reviews/clause-preview \
  -F "platform=Android"
```

Expected: `403`. (If the `reader@example.com` account from earlier sessions no longer exists, create one via the admin session and `POST /api/users` first.)

- [ ] **Step 5: Manual UI check**

Report to the user that browser click-through isn't available in this environment -- recommend they open a review flow page as a reviewer/admin account, expand "Adjust clause guidance for this review," confirm it's pre-filled with real clause descriptions and org defaults, edit one, and start a review to confirm the request succeeds.

- [ ] **Step 6: Report results**

Report pass/fail counts for both suites and the smoke test's observed behavior.
