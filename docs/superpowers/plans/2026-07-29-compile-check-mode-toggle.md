# Compile-Check Mode Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the reviewer choose, per Android review, between "Compile-time lint" (today's only behavior — real compiler service, clause 1.4 excluded from the LLM prompt) and "Static file analysis" (the pre-compile-lint behavior — clause 1.4 scored by the LLM like every other sub-criterion, compiler service never called).

**Architecture:** Backend: a new `compileCheckMode` form field threads through `_run_review`, branching the compiling phase (skip vs. call `check_compile_warnings`) and the scoring loop (exclude vs. include `"1.4"` in the LLM sub-criteria list). Frontend: a new `compileCheckModeStorage.js` persists the choice; `UploadForm` gains an opt-in toggle (behind a new `showCompileCheckToggle` prop, so the shared placeholder pages for iOS/.NET/Web never show it); `AndroidReviewFlow` reads the persisted mode at submit time and sends it with the review, the same pattern already used for the LLM provider/model.

**Tech Stack:** FastAPI/Python backend (pytest, pytest-asyncio), React 19 frontend (Jest/React Testing Library). No new dependencies.

## Global Constraints

- `compileCheckMode` values: only `"static"` skips the compiler and includes `"1.4"` in the LLM prompt; every other value (including omitted/default) behaves exactly as today (`"compiler"`).
- Static mode reuses the exact same category-scoring prompt clause `"1.4"` would get if it weren't excluded — no separate static-analysis prompt, no special-casing of its rubric text.
- `UploadForm` is shared with the iOS/.NET/Web placeholder pages (`PlaceholderReviewFlow`) — the new toggle must be opt-in (a prop, default off) so those pages are unaffected.
- Follow existing patterns: `Form(...)` fields on `POST /api/reviews` (matching `llmProvider`/`ollamaModel`), the `localStorage`-backed getter/setter module shape (matching `llmProviderStorage.js`), the `.btn`/`.btn-primary` toggle pattern already used three times in this app.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit.

---

## Task 1: Backend — thread `compileCheckMode` through the review

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/tests/test_reviews_create.py`
- Modify: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `check_compile_warnings` (`backend/app/analyzer/compile_checker.py`, unchanged); `score_category`/`generate_general_remarks` (`backend/app/analyzer/llm_client.py`, unchanged signatures).
- Produces: `POST /api/reviews` accepts `compileCheckMode` (form field, default `"compiler"`); `_run_review` gains a `compile_check_mode: str = "compiler"` parameter.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reviews_create.py` (placed after `test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm`):

```python
async def test_run_review_static_mode_skips_compiler_and_scores_1_4_via_llm(monkeypatch):
    review_id = "static-mode-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    compile_check_called = []
    captured_sub_criteria = {}

    async def fake_check_compile_warnings(zip_path_arg):
        compile_check_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": "stub"} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        compile_check_mode="static",
    )

    assert compile_check_called == []
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "skipped"
    assert state["lint_issues"] == []
    sub_1_4 = next(s for s in state["category_scores"][0]["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1
    assert sub_1_4["remark"] == "stub"
```

Add to `backend/tests/test_reviews_integration.py` (placed after `test_full_review_pipeline_in_stub_mode`):

```python
async def test_full_review_pipeline_static_mode_scores_1_4_via_stub_llm(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    async def _fail_if_called(zip_path_arg):
        raise AssertionError("check_compile_warnings must not be called in static mode")

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fail_if_called)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx",
                    _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={"compileCheckMode": "static"},
        )
        assert create_response.status_code == 200
        review_id = create_response.json()["review_id"]

        final_state = None
        for _ in range(50):
            progress_response = client.get(f"/api/reviews/{review_id}/progress")
            body = progress_response.json()
            if body["status"] in ("completed", "error"):
                final_state = body
                break
            time.sleep(0.05)

        assert final_state is not None, "review did not finish in time"
        assert final_state["status"] == "completed"
        assert final_state["compile_status"] == "skipped"
        assert final_state["lint_issues"] == []

        category_1 = next(c for c in final_state["category_scores"] if c["id"] == "1")
        sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
        assert sub_1_4["description"] == "No compile-time warnings"
        assert sub_1_4["score"] == 1
        assert "placeholder score" in sub_1_4["remark"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py::test_run_review_static_mode_skips_compiler_and_scores_1_4_via_llm tests/test_reviews_integration.py::test_full_review_pipeline_static_mode_scores_1_4_via_stub_llm -v`
Expected: FAIL — `TypeError: _run_review() got an unexpected keyword argument 'compile_check_mode'` (unit test) and an `AssertionError` from `_fail_if_called` being invoked (integration test, since `compileCheckMode` isn't read by `create_review` yet, so it falls through to today's compiler path regardless of the form field).

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, add the new form field to `create_review`:

```python
@router.post("/api/reviews")
async def create_review(
    androidZip: UploadFile = File(...),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
    compileCheckMode: str = Form("compiler"),
):
```

Pass it through to `_run_review`:

```python
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode,
        )
    )
```

Add the new parameter to `_run_review`'s signature:

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
) -> None:
```

Branch the compiling phase:

```python
        t1b = time.monotonic()
        state["phase"] = "compiling"
        if compile_check_mode == "static":
            state["message"] = "Skipping compiler check (static analysis mode)..."
            state["lint_issues"] = []
            state["compile_status"] = "skipped"
            compile_sub_result = None
        else:
            state["message"] = "Compiling and running Lint checks..."
            compile_result = await check_compile_warnings(zip_path)
            state["lint_issues"] = compile_result["issues"]
            state["compile_status"] = compile_result["status"]
            compile_sub_result = _compile_result_to_sub_score(compile_result)
        stats["compile_time_ms"] = int((time.monotonic() - t1b) * 1000)
        state["progress"] = 55
```

Branch the scoring loop's sub-criteria selection and merge:

```python
            llm_sub_criteria = (
                [sub_id for sub_id in category["sub_criteria"] if sub_id != "1.4"]
                if category_id == "1" and compile_check_mode == "compiler" else category["sub_criteria"]
            )
            sub_results, prompt_info = await score_category(
                llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context,
                model=ollama_model,
            )
            if category_id == "1" and compile_check_mode == "compiler":
                sub_results = _merge_compile_result_into_category_1(sub_results, compile_sub_result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: PASS — all tests in both files green, including the two new ones.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: add compileCheckMode to skip the compiler and score 1.4 via the LLM"
```

---

## Task 2: Frontend — `compileCheckModeStorage.js`

**Files:**
- Create: `frontend/src/services/compileCheckModeStorage.js`
- Test: `frontend/src/services/compileCheckModeStorage.test.jsx`

**Interfaces:**
- Produces: `getCompileCheckMode(): string` (defaults to `"compiler"`), `setCompileCheckMode(mode: string): void`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/services/compileCheckModeStorage.test.jsx`:

```jsx
import { getCompileCheckMode, setCompileCheckMode } from "./compileCheckModeStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to compiler when nothing is stored", () => {
  expect(getCompileCheckMode()).toBe("compiler");
});

test("returns a previously-stored value", () => {
  localStorage.setItem("compileCheckMode", "static");
  expect(getCompileCheckMode()).toBe("static");
});

test("setCompileCheckMode writes to localStorage under the expected key", () => {
  setCompileCheckMode("static");
  expect(localStorage.getItem("compileCheckMode")).toBe("static");
  expect(getCompileCheckMode()).toBe("static");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/services/compileCheckModeStorage.test.jsx`
Expected: FAIL — `Cannot find module './compileCheckModeStorage'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/services/compileCheckModeStorage.js`:

```js
const STORAGE_KEY = "compileCheckMode";
const DEFAULT_MODE = "compiler";

export function getCompileCheckMode() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_MODE;
}

export function setCompileCheckMode(mode) {
  localStorage.setItem(STORAGE_KEY, mode);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npx react-scripts test src/services/compileCheckModeStorage.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/compileCheckModeStorage.js frontend/src/services/compileCheckModeStorage.test.jsx
git commit -m "feat: add compileCheckMode persistence"
```

---

## Task 3: Frontend — `UploadForm` gains an opt-in toggle

**Files:**
- Modify: `frontend/src/components/UploadForm.jsx`
- Modify: `frontend/src/components/UploadForm.test.jsx`

**Interfaces:**
- Consumes: `getCompileCheckMode`/`setCompileCheckMode` (Task 2).
- Produces: `UploadForm({ onSubmit, disabled, disabledLabel, showCompileCheckToggle })` — `showCompileCheckToggle` is new, defaults to `false` (existing callers, including `PlaceholderReviewFlow`, are unaffected).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/components/UploadForm.test.jsx` (add a `beforeEach` if none exists, and import the storage getter):

```jsx
import { getCompileCheckMode } from "../services/compileCheckModeStorage";
```

```jsx
beforeEach(() => {
  localStorage.clear();
});
```

```jsx
test("does not render the compile-check toggle by default", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  expect(screen.queryByText("Compile-time lint")).not.toBeInTheDocument();
});

test("renders the compile-check toggle when showCompileCheckToggle is true, defaulting to Compile-time lint", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);
  expect(screen.getByRole("button", { name: "Compile-time lint" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Static file analysis" })).not.toHaveClass("btn-primary");
});

test("selecting Static file analysis persists the choice and highlights it", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);

  await user.click(screen.getByRole("button", { name: "Static file analysis" }));

  expect(screen.getByRole("button", { name: "Static file analysis" })).toHaveClass("btn-primary");
  expect(getCompileCheckMode()).toBe("static");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm.test.jsx`
Expected: FAIL — no element with text "Compile-time lint" exists yet (the second and third new tests fail; the first passes trivially since nothing is rendered either way, but keep it — it's the regression guard once the toggle exists).

- [ ] **Step 3: Implement**

Overwrite `frontend/src/components/UploadForm.jsx`:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";
import { FileIcon, ArrowRightIcon } from "../icons";
import { getCompileCheckMode, setCompileCheckMode } from "../services/compileCheckModeStorage";

export default function UploadForm({ onSubmit, disabled, disabledLabel = "Starting review…", showCompileCheckToggle = false }) {
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [validationError, setValidationError] = useState("");
  const [compileCheckMode, setCompileCheckModeState] = useState(() => getCompileCheckMode());

  function handleSubmit(event) {
    event.preventDefault();
    if (!androidZip || !androidZip.name.endsWith(".zip")) {
      setValidationError("Android project must be a .zip file");
      return;
    }
    if (!excelTemplate || !excelTemplate.name.endsWith(".xlsx")) {
      setValidationError("Review template must be a .xlsx file");
      return;
    }
    setValidationError("");
    onSubmit(androidZip, excelTemplate);
  }

  function handleSelectMode(mode) {
    setCompileCheckMode(mode);
    setCompileCheckModeState(mode);
  }

  const canStart = !!androidZip && !!excelTemplate;

  return (
    <form onSubmit={handleSubmit} className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
      <CornerMarks />
      <div className="card-kicker">Step 1 of 2</div>
      <div className="card-title" style={{ fontSize: 20 }}>Upload project files</div>
      <p className="card-body">Both files are required to start a review.</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginTop: "var(--space-5)" }}>
        <div className="field">
          <label htmlFor="androidZip">Android project (.zip)</label>
          <label className="input" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
            <FileIcon />
            {androidZip ? <span>{androidZip.name}</span> : <span style={{ opacity: 0.55 }}>Choose ZIP file…</span>}
            <input
              id="androidZip"
              type="file"
              accept=".zip"
              disabled={disabled}
              onChange={(event) => setAndroidZip(event.target.files[0] ?? null)}
              style={{ display: "none" }}
            />
          </label>
        </div>
        <div className="field">
          <label htmlFor="excelTemplate">Scoring template (.xlsx)</label>
          <label className="input" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
            <FileIcon />
            {excelTemplate ? <span>{excelTemplate.name}</span> : <span style={{ opacity: 0.55 }}>Choose Excel file…</span>}
            <input
              id="excelTemplate"
              type="file"
              accept=".xlsx"
              disabled={disabled}
              onChange={(event) => setExcelTemplate(event.target.files[0] ?? null)}
              style={{ display: "none" }}
            />
          </label>
        </div>
      </div>

      {showCompileCheckToggle && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <p className="card-body" style={{ marginBottom: "var(--space-2)" }}>Clause 1.4 evaluation</p>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              className={`btn ${compileCheckMode === "compiler" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("compiler")}
            >
              Compile-time lint
            </button>
            <button
              type="button"
              className={`btn ${compileCheckMode === "static" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("static")}
            >
              Static file analysis
            </button>
          </div>
        </div>
      )}

      {validationError && <p className="card-body" style={{ color: "#b3261e" }}>{validationError}</p>}

      <button
        type="submit"
        className="btn btn-primary btn-block blueprint"
        style={{ marginTop: "var(--space-5)" }}
        disabled={disabled || !canStart}
      >
        <CornerMarks />
        {disabled ? disabledLabel : "Start review"}
        <ArrowRightIcon />
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm.test.jsx`
Expected: PASS — all tests green (4 existing + 1 from the earlier `disabledLabel` round + 3 new).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx
git commit -m "feat: add opt-in compile-check mode toggle to UploadForm"
```

---

## Task 4: Frontend — `createReview` gains the field + `FindingsPanel` handles `"skipped"`

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/services/api.test.js`
- Modify: `frontend/src/components/FindingsPanel.jsx`
- Modify: `frontend/src/components/FindingsPanel.test.jsx`

**Interfaces:**
- Produces: `createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode)` — the 5th parameter is new and optional. `FindingsPanel` renders a new caption for `compileStatus === "skipped"`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/services/api.test.js`, inside the `describe("createReview", ...)` block:

```js
  it("includes compileCheckMode field when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "azure", null, "static");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("compileCheckMode")).toBe("static");
  });
```

Add to `frontend/src/components/FindingsPanel.test.jsx` (after `test("shows an unavailable caption when the compile check couldn't run", ...)`):

```jsx
test("shows a static-analysis caption when the compiler check was skipped", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="skipped" />
  );
  expect(screen.getByText("Static analysis mode selected — clause 1.4 scored by AI.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js src/components/FindingsPanel.test.jsx`
Expected: FAIL — `formData.get("compileCheckMode")` is `null` (not sent yet); the "skipped" caption text doesn't exist yet (falls through to "Not yet checked.").

- [ ] **Step 3: Implement**

In `frontend/src/services/api.js`, update `createReview`:

```js
export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

In `frontend/src/components/FindingsPanel.jsx`, update `lintCardProps`:

```js
function lintCardProps(compileStatus, lintIssues) {
  if (compileStatus === "ok") {
    return lintIssues.length > 0
      ? { value: lintIssues.length, caption: `${lintIssues.length} issue${lintIssues.length === 1 ? "" : "s"} found`, expandable: true }
      : { value: 0, caption: "No Lint warnings or errors found.", expandable: false };
  }
  if (compileStatus === "build_failed") {
    return { value: "—", caption: "Project failed to compile.", expandable: false };
  }
  if (compileStatus === "unavailable") {
    return { value: "—", caption: "Compile check unavailable.", expandable: false };
  }
  if (compileStatus === "skipped") {
    return { value: "—", caption: "Static analysis mode selected — clause 1.4 scored by AI.", expandable: false };
  }
  return { value: "—", caption: "Not yet checked.", expandable: false };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js src/components/FindingsPanel.test.jsx`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js frontend/src/components/FindingsPanel.jsx frontend/src/components/FindingsPanel.test.jsx
git commit -m "feat: send compileCheckMode with the review and show a skipped-check caption"
```

---

## Task 5: Frontend — `AndroidReviewFlow` sends the persisted mode and shows the toggle

**Files:**
- Modify: `frontend/src/pages/AndroidReviewFlow.jsx`
- Modify: `frontend/src/pages/AndroidReviewFlow.test.jsx`

**Interfaces:**
- Consumes: `getCompileCheckMode` (Task 2); `createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode)` (Task 4); `UploadForm`'s `showCompileCheckToggle` prop (Task 3).
- Produces: no new exports — same `AndroidReviewFlow` default export, no props, as before.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/AndroidReviewFlow.test.jsx`, update the two existing `toHaveBeenCalledWith` assertions from the ollama round (they now need a 5th argument, since `createReview` is always called with `compileCheckMode` too — the stored default, `"compiler"`, since neither test sets it). No new import is needed in this file — the new tests below set the mode via `localStorage.setItem` directly, the same way the existing tests already set `llmProvider`/`ollamaModel`.

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler");
```

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler");
```

Then add two new tests at the end of the file:

```jsx
test("shows the compile-check mode toggle", () => {
  renderFlow();
  expect(screen.getByRole("button", { name: "Compile-time lint" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Static file analysis" })).toBeInTheDocument();
});

test("sends the persisted compile-check mode when starting a review", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("compileCheckMode", "static");
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx`
Expected: FAIL — the toggle isn't rendered yet (`showCompileCheckToggle` isn't passed), and `createReview` is still called with only 4 arguments.

- [ ] **Step 3: Implement**

In `frontend/src/pages/AndroidReviewFlow.jsx`, add the import:

```jsx
import { getLlmProvider, getOllamaModel } from "../services/llmProviderStorage";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";
```

Update `handleUpload`:

```jsx
  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const models = await getOllamaModels().catch(() => []);
      const storedProvider = getLlmProvider();
      const effectiveProvider = storedProvider === "ollama" && models.length === 0 ? "azure" : storedProvider;
      const effectiveModel = effectiveProvider === "ollama" ? getOllamaModel() : null;
      const compileCheckMode = getCompileCheckMode();

      const result = await createReview(androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode);
      if (result.status === "error") {
        setErrorMessage(result.error || "Upload failed");
        setState("error");
        return;
      }
      setReviewId(result.review_id);
      setState("polling");
    } catch (err) {
      setErrorMessage("Failed to start review. Is the server running?");
      setState("error");
    }
  }, []);
```

Update the `UploadForm` render to opt into the toggle:

```jsx
        {(state === "idle" || state === "uploading") && (
          <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} showCompileCheckToggle />
        )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx`
Expected: PASS — all tests green.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test`
Expected: PASS — full frontend suite green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AndroidReviewFlow.jsx frontend/src/pages/AndroidReviewFlow.test.jsx
git commit -m "feat: send the persisted compile-check mode and show its toggle on the Android flow"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend && source venv/bin/activate && python -m pytest -v` — all green.
- [ ] Run the full frontend suite: `cd frontend && CI=true npx react-scripts test` — all green.
- [ ] Rebuild and restart both containers: `docker compose up -d --build backend frontend`.
- [ ] Manually verify in the browser: the Android upload screen shows the Compile-time lint / Static file analysis toggle (defaulting to Compile-time lint); the iOS/.NET/Web placeholder pages do not show it; running a review in Static file analysis mode completes without ever hitting the compiler container (check `docker compose logs compiler` shows no new request), and the report table shows a real AI-scored remark for clause 1.4 instead of a lint-derived one; running a review in Compile-time lint mode behaves exactly as before.
