# Report View, Project Name & Performance Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the uploaded project's name in the header, expose a per-clause report table in the browser (replacing download-only access to results), let the user toggle between that report and the existing prompt/token debug log, and move the timing breakdown into an on-demand "Performance breakdown" popup that also shows the previously-missing compile/lint duration.

**Architecture:** Backend: `project_name` (already computed at upload time) gets stored on review state and returned by `/progress`; each `category_scores` entry gains a `sub_criteria` list seeded from the static `CATEGORIES` map, backfilled with descriptions after the template is parsed and with score/remark during the existing per-category scoring loop — reusing data `aggregate_category_scores` already produces, no new computation. Frontend: a new `ReportTable` component renders that per-clause data; `App.jsx` swaps its always-on `PromptDebugLog` bottom band for a two-button Report/Debug toggle and shows `project_name` in the header once available; `StatsDisplay` replaces its inline timing card with a button opening a `.dialog` modal (new vendored CSS) containing the same table plus the missing "Compiling & Lint (Gradle)" row.

**Tech Stack:** FastAPI/Python backend (pytest, pytest-asyncio), React 19 frontend (Jest/React Testing Library), no new dependencies.

## Global Constraints

- `CATEGORIES` (in `backend/app/api/reviews.py`) is the single source of truth for category ids, names, and sub-criteria ids — never hardcode a parallel list.
- `aggregate_category_scores`'s `sub_scores` dict (`backend/app/analyzer/excel_handler.py`) is `{sub_id: {"score": int|None, "remark": str}}` — the backfill logic must read from this, not recompute scores.
- Binary rubric only: a sub-criterion `score` is `1`, `0`, or `null` — never `0.5` (established in the compile-lint round).
- Follow existing "Industry" design system conventions: `.card`/`.blueprint` + `<CornerMarks />`, `.btn`/`.btn-primary`/`.btn-ghost`, `.table`, `.tag`/`.tag-accent`/`.tag-outline`, CSS custom properties from `frontend/src/design-system.css` — no ad hoc inline colors.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit. Never write implementation before its test.
- After backend code changes, the running `backend` Docker container must be rebuilt (`docker compose up -d --build backend`) before manual verification — editing the source alone does not update a running container (this bit us in the compile-lint round).

---

## Task 1: Backend — persist and expose `project_name`

**Files:**
- Modify: `backend/app/api/reviews.py:40-61` (`_new_review_state`), `:81-110` (`create_review`), `:234-256` (`get_progress`)
- Test: `backend/tests/test_reviews_create.py`
- Test: `backend/tests/test_reviews_progress.py`

**Interfaces:**
- Consumes: nothing new — `project_name` is already computed in `create_review` (`backend/app/api/reviews.py:104`) and already passed into `_run_review`.
- Produces: `state["project_name"]` (str, set at creation, never mutated afterward); `/api/reviews/{id}/progress` response gains `"project_name": str | None`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_create.py`, extend `test_create_review_returns_id_and_creates_state`:

```python
def test_create_review_returns_id_and_creates_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "processing"
        assert body["review_id"] in _reviews
        assert _reviews[body["review_id"]]["project_name"] == "project"
```

(Only the last assertion line is new — the zip is uploaded as `"project.zip"`, so the derived name is `"project"`, matching the existing convention checked in `test_reviews_integration.py:151`.)

In `backend/tests/test_reviews_progress.py`, extend `test_progress_reflects_stored_state` and `test_progress_defaults_detection_fields_when_absent`:

```python
def test_progress_reflects_stored_state():
    _reviews["fixed-id"] = {
        "status": "processing",
        "phase": "scoring",
        "progress": 60,
        "message": "Scoring category 2",
        "stats": {"ingest_time_ms": 120},
        "download_path": None,
        "error": None,
        "warnings": ["Missing AndroidManifest.xml"],
        "test_coverage": 82.5,
        "secrets_found": [{"file": "Constants.java", "line": 42, "pattern": "api_key"}],
        "total_score_pct": 78.0,
        "project_name": "MyProject",
        "category_scores": [
            {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
            {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
        ],
        "code_context": "class MainActivity {}",
        "prompt_log": [
            {
                "label": "Code naming conventions / Code Structure",
                "prompt_text": "Score the following...",
                "tokens": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None},
            },
        ],
        "lint_issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
        "compile_status": "ok",
    }
    response = client.get("/api/reviews/fixed-id/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["phase"] == "scoring"
    assert body["progress"] == 60
    assert body["download_url"] is None
    assert body["error"] is None
    assert body["warnings"] == ["Missing AndroidManifest.xml"]
    assert body["test_coverage"] == 82.5
    assert body["secrets_found"] == [{"file": "Constants.java", "line": 42, "pattern": "api_key"}]
    assert body["total_score_pct"] == 78.0
    assert body["project_name"] == "MyProject"
    assert body["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
    ]
    assert body["code_context"] == "class MainActivity {}"
    assert body["prompt_log"] == [
        {
            "label": "Code naming conventions / Code Structure",
            "prompt_text": "Score the following...",
            "tokens": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None},
        },
    ]
    assert body["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}]
    assert body["compile_status"] == "ok"


def test_progress_defaults_detection_fields_when_absent():
    _reviews["legacy-id"] = {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
    }
    response = client.get("/api/reviews/legacy-id/progress")
    body = response.json()
    assert body["warnings"] == []
    assert body["test_coverage"] is None
    assert body["secrets_found"] == []
    assert body["total_score_pct"] is None
    assert body["project_name"] is None
    assert body["category_scores"] == []
    assert body["code_context"] is None
    assert body["prompt_log"] == []
    assert body["lint_issues"] == []
    assert body["compile_status"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_create.py::test_create_review_returns_id_and_creates_state tests/test_reviews_progress.py -v`
Expected: FAIL — `KeyError: 'project_name'` (state dict has no such key) and the progress response has no `project_name` key (`body["project_name"]` raises `KeyError` on the test side via `assert body["project_name"] == ...` actually raising `AssertionError`/`KeyError` since the key is absent from the JSON dict).

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, add `"project_name": None` to `_new_review_state()`:

```python
def _new_review_state() -> dict:
    return {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
        "total_score_pct": None,
        "project_name": None,
        "category_scores": [
            {"id": category_id, "name": category["name"], "percent_points": None}
            for category_id, category in CATEGORIES.items()
        ],
        "code_context": None,
        "prompt_log": [],
        "lint_issues": [],
        "compile_status": None,
    }
```

In `create_review`, set it immediately after creating state (replacing the current single-line assignment):

```python
    state = _new_review_state()
    state["project_name"] = project_name
    _reviews[review_id] = state
    asyncio.create_task(
        _run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name)
    )
    return {"review_id": review_id, "status": "processing"}
```

In `get_progress`, add the field to the returned dict (placed alongside the other detection fields):

```python
    return {
        "status": state["status"],
        "phase": state["phase"],
        "progress": state["progress"],
        "message": state["message"],
        "stats": state["stats"],
        "download_url": f"/api/reviews/{review_id}/download" if state["status"] == "completed" else None,
        "error": state["error"],
        "warnings": state.get("warnings", []),
        "test_coverage": state.get("test_coverage"),
        "secrets_found": state.get("secrets_found", []),
        "total_score_pct": state.get("total_score_pct"),
        "project_name": state.get("project_name"),
        "category_scores": state.get("category_scores", []),
        "code_context": state.get("code_context"),
        "prompt_log": state.get("prompt_log", []),
        "lint_issues": state.get("lint_issues", []),
        "compile_status": state.get("compile_status"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reviews_create.py tests/test_reviews_progress.py tests/test_reviews_integration.py -v`
Expected: PASS (all backend tests touching review state/progress, including the untouched integration test, which doesn't check `project_name` yet — that comes in Task 2's integration assertions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_progress.py
git commit -m "feat: persist and expose project_name on review state"
```

---

## Task 2: Backend — extend `category_scores` with `sub_criteria` detail

**Files:**
- Modify: `backend/app/api/reviews.py:40-61` (`_new_review_state`), `:157-160` (description backfill), `:186-190` (score/remark backfill in the scoring loop)
- Test: `backend/tests/test_reviews_create.py`
- Test: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `CATEGORIES` (`backend/app/api/reviews.py:29-35`); `extract_sub_criteria_descriptions(ws, categories) -> {sub_id: str}` (`backend/app/analyzer/excel_handler.py:159`); `aggregate_category_scores(sub_scores) -> {"avg_points", "final_points", "percent_points", "sub_scores": {sub_id: {"score", "remark"}}}` (`backend/app/analyzer/excel_handler.py:30`).
- Produces: each `state["category_scores"][i]` gains `"sub_criteria": [{"id": str, "description": str|None, "score": int|None, "remark": str|None}, ...]`, in the same order as `CATEGORIES[category_id]["sub_criteria"]`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_reviews_create.py`, update the seed-shape assertion inside `test_run_review_updates_category_scores_progressively` (the first assertion block, right after `_reviews[review_id] = _new_review_state()`):

```python
async def test_run_review_updates_category_scores_progressively(monkeypatch):
    review_id = "category-scores-progress-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    expected_sub_criteria = {
        cid: [{"id": sub_id, "description": None, "score": None, "remark": None} for sub_id in cat["sub_criteria"]]
        for cid, cat in reviews_module.CATEGORIES.items()
    }
    assert _reviews[review_id]["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": None, "sub_criteria": expected_sub_criteria["1"]},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None, "sub_criteria": expected_sub_criteria["2"]},
        {"id": "3", "name": "Delivery Discipline & Architecture", "percent_points": None, "sub_criteria": expected_sub_criteria["3"]},
        {"id": "4", "name": "AI Usage & Code Ownership", "percent_points": None, "sub_criteria": expected_sub_criteria["4"]},
        {"id": "6", "name": "Safe & Integrated AI Code", "percent_points": None, "sub_criteria": expected_sub_criteria["6"]},
    ]

    snapshots = []

    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert snapshots[0] == [("1", None), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[1] == [("1", 100.0), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[4] == [("1", 100.0), ("2", 100.0), ("3", 100.0), ("4", 100.0), ("6", None)]

    final_scores = _reviews[review_id]["category_scores"]
    assert all(entry["percent_points"] == 100.0 for entry in final_scores)

    # Stub-style score_category above scores every LLM-scored sub-criterion 1
    # with an empty remark; every sub_criteria entry across every category
    # must reflect that (proves the per-category backfill runs for every
    # category, not just the first) -- except "1.4", which the compile-check
    # merge (_merge_compile_result_into_category_1) overwrites with its own
    # score/remark before scoring even runs, independent of score_category.
    for entry in final_scores:
        for sub in entry["sub_criteria"]:
            assert sub["score"] == 1
            if sub["id"] == "1.4":
                assert sub["remark"] == "No Lint warnings or errors found."
            else:
                assert sub["remark"] == ""
```

In `backend/tests/test_reviews_integration.py`, extend `test_full_review_pipeline_in_stub_mode` with assertions on the backfilled `sub_criteria` (add right after the existing `assert final_state["lint_issues"] == []` line):

```python
        assert final_state["project_name"] == "project"

        category_1 = next(c for c in final_state["category_scores"] if c["id"] == "1")
        sub_criteria_by_id = {s["id"]: s for s in category_1["sub_criteria"]}
        # Descriptions come from the xlsx fixture's own text (see _build_xlsx_bytes above).
        assert sub_criteria_by_id["1.1"]["description"] == "Clear and consistent naming conventions"
        assert sub_criteria_by_id["1.4"]["description"] == "No compile-time warnings"
        # Stub mode scores every LLM-scored sub-criterion 1 with the stub placeholder remark.
        assert sub_criteria_by_id["1.1"]["score"] == 1
        assert "placeholder score" in sub_criteria_by_id["1.1"]["remark"]
        # 1.4 comes from the (stubbed) compile-check merge, not the LLM, and keeps its own remark.
        assert sub_criteria_by_id["1.4"]["score"] == 1
        assert sub_criteria_by_id["1.4"]["remark"] == "No Lint warnings or errors found."

        category_2 = next(c for c in final_state["category_scores"] if c["id"] == "2")
        sub_2_1 = next(s for s in category_2["sub_criteria"] if s["id"] == "2.1")
        assert sub_2_1["description"] == "Proper exception handling"
        assert sub_2_1["score"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_create.py::test_run_review_updates_category_scores_progressively tests/test_reviews_integration.py -v`
Expected: FAIL — `AssertionError` on the `category_scores` equality check (no `sub_criteria` key present yet) and `KeyError`/`AssertionError` on the new integration assertions.

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, update `_new_review_state()`'s `category_scores` seed:

```python
        "category_scores": [
            {
                "id": category_id,
                "name": category["name"],
                "percent_points": None,
                "sub_criteria": [
                    {"id": sub_id, "description": None, "score": None, "remark": None}
                    for sub_id in category["sub_criteria"]
                ],
            }
            for category_id, category in CATEGORIES.items()
        ],
```

In `_run_review`, right after `sub_criteria_descriptions = extract_sub_criteria_descriptions(template_ws, CATEGORIES)` (around line 158), backfill descriptions into every category's `sub_criteria`:

```python
        sub_criteria_descriptions = extract_sub_criteria_descriptions(template_ws, CATEGORIES)
        for category_entry in state["category_scores"]:
            for sub_entry in category_entry["sub_criteria"]:
                sub_entry["description"] = sub_criteria_descriptions.get(sub_entry["id"])
```

In the scoring loop, right after `scores_by_category[category_id] = aggregate_category_scores(sub_results)` (around line 187), backfill score/remark for that category's `sub_criteria`:

```python
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
            sub_scores = scores_by_category[category_id]["sub_scores"]
            for sub_entry in state["category_scores"][index]["sub_criteria"]:
                sub_result = sub_scores.get(sub_entry["id"])
                if sub_result is not None:
                    sub_entry["score"] = sub_result["score"]
                    sub_entry["remark"] = sub_result["remark"]
            state["category_scores"][index]["percent_points"] = scores_by_category[category_id]["percent_points"]
```

(Note: this reorders the existing `state["category_scores"][index]["percent_points"] = ...` line to sit after the new backfill block — same statement, just moved a few lines down so both updates land together.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest backend/tests -v` (or `cd backend && python -m pytest tests -v` from within `backend/`)
Expected: PASS — full backend suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: backfill per-sub-criterion description/score/remark into category_scores"
```

---

## Task 3: Frontend — `ReportTable` component

**Files:**
- Create: `frontend/src/components/ReportTable.jsx`
- Test: `frontend/src/components/ReportTable.test.jsx`

**Interfaces:**
- Consumes: `CornerMarks` (`frontend/src/components/CornerMarks.jsx`, default export, no props).
- Produces: `ReportTable({ categoryScores })` default export, where `categoryScores` matches the API shape from Task 2: `{ id, name, percent_points, sub_criteria: [{ id, description, score, remark }] }[]`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ReportTable.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import ReportTable from "./ReportTable";

const categoryScores = [
  {
    id: "1",
    name: "Code naming conventions / Code Structure",
    percent_points: 83.3,
    sub_criteria: [
      { id: "1.1", description: "Clear and consistent naming conventions", score: 1, remark: "Looks good." },
      { id: "1.4", description: "No compile-time warnings", score: 0, remark: "2 Lint warning(s)/error(s) found." },
      { id: "1.5", description: "No unused dependencies", score: null, remark: null },
    ],
  },
  {
    id: "2",
    name: "Reliability, Security & Observability",
    percent_points: null,
    sub_criteria: [
      { id: "2.1", description: "Proper exception handling", score: null, remark: null },
    ],
  },
];

test("renders a section per category with its name and percent", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("83.3%")).toBeInTheDocument();
  expect(screen.getByText("Reliability, Security & Observability")).toBeInTheDocument();
});

test("omits the percent tag when percent_points is null", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.queryByText("null%")).not.toBeInTheDocument();
});

test("renders one row per sub-criterion with clause id, description and remark", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.getByText("Clear and consistent naming conventions")).toBeInTheDocument();
  expect(screen.getByText("Looks good.")).toBeInTheDocument();
});

test("maps score 1/0/null to Meets/Fails/Not evaluated labels", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("Meets")).toBeInTheDocument();
  expect(screen.getByText("Fails")).toBeInTheDocument();
  expect(screen.getAllByText("Not evaluated").length).toBe(2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx jest src/components/ReportTable.test.jsx`
Expected: FAIL — `Cannot find module './ReportTable'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/ReportTable.jsx`:

```jsx
import CornerMarks from "./CornerMarks";

function scoreLabel(score) {
  if (score === 1) return "Meets";
  if (score === 0) return "Fails";
  return "Not evaluated";
}

export default function ReportTable({ categoryScores }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-6)" }}>
      {categoryScores.map((category) => (
        <div key={category.id} className="card blueprint" style={{ padding: "var(--space-4)" }}>
          <CornerMarks />
          <div className="card-title" style={{ fontSize: 17, display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            {category.name}
            {category.percent_points !== null && category.percent_points !== undefined && (
              <span className="tag tag-accent">{category.percent_points}%</span>
            )}
          </div>
          <table className="table" style={{ marginTop: "var(--space-3)" }}>
            <thead>
              <tr>
                <th>Clause</th>
                <th>Description</th>
                <th>Score</th>
                <th>Remark</th>
              </tr>
            </thead>
            <tbody>
              {category.sub_criteria.map((sub) => (
                <tr key={sub.id}>
                  <td>{sub.id}</td>
                  <td>{sub.description}</td>
                  <td>{scoreLabel(sub.score)}</td>
                  <td className="text-muted">{sub.remark}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npx jest src/components/ReportTable.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ReportTable.jsx frontend/src/components/ReportTable.test.jsx
git commit -m "feat: add ReportTable component for per-clause scoring detail"
```

---

## Task 4: Frontend — project name in the header

**Files:**
- Modify: `frontend/src/App.jsx:63-71` (header)
- Test: `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: `progressData.project_name` (string | null, from Task 1's API contract).
- Produces: no new exports — header title text now conditional on `progressData?.project_name`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/App.test.jsx`, add `project_name: "project"` to both existing `getProgress.mockResolvedValue({...})` payloads (the completed one and the error one) so they match the real API contract:

```js
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    project_name: "project",
    category_scores: [
      {
        id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0,
        sub_criteria: [{ id: "1.1", description: "Clear naming", score: 1, remark: "" }],
      },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
    lint_issues: [],
    compile_status: "ok",
  });
```

(`category_scores[0].sub_criteria` is added here too since Task 5 wires `ReportTable` into this same screen — without it the report view would crash on `category.sub_criteria.map` once that task lands. Do this now so Task 5 doesn't need to touch this mock again.)

And for the error-state test's mock, add `project_name: null,` next to the other now-required fields:

```js
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    project_name: null,
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });
```

Then add a new test:

```js
test("shows the project name in the header once progress data has it, falling back beforehand", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: {}, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    project_name: "MyAndroidApp",
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: "ok",
  });

  render(<App />);
  expect(screen.getByRole("heading", { name: "Android Code Review Automation" })).toBeInTheDocument();

  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByRole("heading", { name: "MyAndroidApp" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Android Code Review Automation" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `cd frontend && CI=true npx jest src/App.test.jsx`
Expected: The new test FAILs — heading stays "Android Code Review Automation" after upload since `App.jsx` doesn't read `project_name` yet. (The two pre-existing tests should still pass since the mock additions are additive fields their assertions don't check.)

- [ ] **Step 3: Implement**

In `frontend/src/App.jsx`, change the header title:

```jsx
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            {progressData?.project_name || "Android Code Review Automation"}
          </h1>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx jest src/App.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: show project name in the header once available"
```

---

## Task 5: Frontend — Report/Debug toggle in the bottom band

**Files:**
- Modify: `frontend/src/App.jsx` (imports, state, bottom-band JSX)
- Test: `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: `ReportTable({ categoryScores })` (Task 3), `PromptDebugLog({ codeContext, promptLog })` (existing, unchanged).
- Produces: no new exports — purely internal `App` component state (`bottomView`, `"report" | "debug"`).

- [ ] **Step 1: Write the failing test**

In `frontend/src/App.test.jsx`, update the happy-path test (`"full happy path: upload, poll, complete, download link, LLM stats, reset"`) to check the toggle instead of assuming the debug log is always visible. Replace this line:

```js
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
```

with:

```js
  // Report view is the default: the report table's clause is visible, the
  // debug log's prompt-source toggle is not.
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Debug info" }));
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
  expect(screen.queryByText("1.1")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Report" }));
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();
```

(`"1.1"` comes from the `sub_criteria` entry already added to this test's mock in Task 4.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx jest src/App.test.jsx`
Expected: FAIL — `screen.getByText("1.1")` throws (not rendered yet; the bottom band still always renders `PromptDebugLog` with no `ReportTable` or toggle buttons).

- [ ] **Step 3: Implement**

In `frontend/src/App.jsx`, add the import and toggle state:

```jsx
import ReportTable from "./components/ReportTable";
```

```jsx
  const [bottomView, setBottomView] = useState("report"); // report | debug
```

Replace the bottom-band block:

```jsx
            {showLlmDetails && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <PromptDebugLog codeContext={progressData.code_context} promptLog={progressData.prompt_log} />
              </div>
            )}
```

with:

```jsx
            {showLlmDetails && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
                  <button
                    type="button"
                    className={`btn ${bottomView === "report" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("report")}
                  >
                    Report
                  </button>
                  <button
                    type="button"
                    className={`btn ${bottomView === "debug" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("debug")}
                  >
                    Debug info
                  </button>
                </div>
                {bottomView === "report" ? (
                  <ReportTable categoryScores={progressData.category_scores} />
                ) : (
                  <PromptDebugLog codeContext={progressData.code_context} promptLog={progressData.prompt_log} />
                )}
              </div>
            )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx jest src/App.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: add Report/Debug toggle to the bottom band"
```

---

## Task 6: Frontend — vendor `.dialog`/`.dialog-backdrop` classes

**Files:**
- Modify: `frontend/src/design-system.css`

**Interfaces:**
- Consumes: nothing (pure CSS addition).
- Produces: `--color-neutral-900`, `--radius-lg`, `--shadow-lg` tokens; `.dialog-backdrop`, `.dialog`, `.dialog-title`, `.dialog-body`, `.dialog-actions` classes, for Task 7 to consume.

No test — this is CSS-only scaffolding with no behavior to unit test on its own; Task 7's component tests exercise it via `render`/`screen` queries against the DOM structure it enables.

- [ ] **Step 1: Add the tokens**

In `frontend/src/design-system.css`, extend the `:root` block (after `--shadow-md`):

```css
  --shadow-md: 0 3px 10px color-mix(in srgb, #2b2b2d 16%, transparent);

  --color-neutral-900: #17181a;
  --radius-lg: 8px;
  --shadow-lg: 0 12px 32px color-mix(in srgb, #2b2b2d 28%, transparent);
```

- [ ] **Step 2: Add the dialog classes**

Append to the end of `frontend/src/design-system.css`:

```css
/* — dialog (modal) — */
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-neutral-900) 55%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  z-index: 100;
}
.dialog {
  position: relative;
  width: 100%;
  max-width: 480px;
  background: var(--color-bg);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: var(--space-6);
}
.dialog-title {
  font-family: var(--font-heading);
  font-weight: var(--font-heading-weight);
  font-size: 20px;
  margin: 0 0 var(--space-4);
}
.dialog-body { margin: 0; }
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-5);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/design-system.css
git commit -m "feat: vendor dialog/modal classes into the design system"
```

---

## Task 7: Frontend — Performance breakdown popup on `StatsDisplay`

**Files:**
- Modify: `frontend/src/components/StatsDisplay.jsx`
- Test: `frontend/src/components/StatsDisplay.test.jsx`

**Interfaces:**
- Consumes: `.dialog`/`.dialog-backdrop`/`.dialog-title`/`.dialog-body`/`.dialog-actions` classes (Task 6); `stats.compile_time_ms` (already present in backend `stats` since the compile-check feature, per `backend/app/api/reviews.py:169`).
- Produces: no new exports — same `StatsDisplay` props as before.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/StatsDisplay.test.jsx`, replace the existing timing test (it currently assumes the table is always inline) with one that opens the modal first, and add two new tests:

```jsx
test("shows timing breakdown for each provided stat, formatted as seconds, inside the performance breakdown modal", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      stats={{ ingest_time_ms: 800, analysis_time_ms: 2100, compile_time_ms: 5200, scoring_time_ms: 11400, generation_time_ms: 600, total_time_ms: 14900 }}
    />
  );

  expect(screen.queryByText("0.8s")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /performance breakdown/i }));

  expect(screen.getByText("0.8s")).toBeInTheDocument();
  expect(screen.getByText("14.9s")).toBeInTheDocument();
  expect(screen.getByText("Compiling & Lint (Gradle)")).toBeInTheDocument();
  expect(screen.getByText("5.2s")).toBeInTheDocument();
});

test("closes the performance breakdown modal when Close is clicked", async () => {
  const user = userEvent.setup();
  render(<StatsDisplay {...baseProps} stats={{ total_time_ms: 500 }} />);

  await user.click(screen.getByRole("button", { name: /performance breakdown/i }));
  expect(screen.getByText("Total")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /^close$/i }));
  expect(screen.queryByText("Total")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx jest src/components/StatsDisplay.test.jsx`
Expected: FAIL — the timing table is currently always rendered inline (so `queryByText("0.8s")` is already present before the click, failing the first assertion), there's no "Performance breakdown" button, and `compile_time_ms` isn't in `TIMING_ROWS` yet.

- [ ] **Step 3: Implement**

In `frontend/src/components/StatsDisplay.jsx`:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

const TIMING_ROWS = [
  { key: "ingest_time_ms", label: "Ingest (unzip + validate)" },
  { key: "analysis_time_ms", label: "Analysis (parsing + secrets + versions)" },
  { key: "compile_time_ms", label: "Compiling & Lint (Gradle)" },
  { key: "scoring_time_ms", label: "Scoring (Azure OpenAI)" },
  { key: "generation_time_ms", label: "Generation (Excel write)" },
  { key: "total_time_ms", label: "Total" },
];

export default function StatsDisplay({ totalScorePct, warnings, secretsFound, stats, downloadUrl, onReset }) {
  const [showPerf, setShowPerf] = useState(false);
  const rows = TIMING_ROWS.filter((row) => stats[row.key] !== undefined);

  return (
    <div>
      <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
        <CornerMarks />
        <div className="card-kicker">Complete</div>
        <div className="card-title" style={{ fontSize: 20 }}>Review ready</div>
        <p className="card-body">Scores were written into your template with the original formatting preserved.</p>
        <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
          {totalScorePct !== null && totalScorePct !== undefined && (
            <span className="tag tag-accent">Total {totalScorePct}%</span>
          )}
          <span className="tag tag-outline">{warnings.length} warnings</span>
          <span className="tag tag-outline">{secretsFound.length} secrets</span>
        </div>
        <a
          href={getDownloadUrl(downloadUrl)}
          download
          className="btn btn-primary btn-block blueprint"
          style={{ marginTop: "var(--space-5)" }}
        >
          <CornerMarks />
          Download populated workbook
          <DownloadIcon />
        </a>
        <button
          type="button"
          className="btn"
          style={{ marginTop: "var(--space-3)" }}
          onClick={() => setShowPerf(true)}
        >
          Performance breakdown
        </button>
      </div>

      {showPerf && (
        <div className="dialog-backdrop" onClick={() => setShowPerf(false)}>
          <div className="dialog" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Performance breakdown</div>
            <table className="table dialog-body">
              <thead><tr><th>Phase</th><th>Duration</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td className="text-muted">{formatSeconds(stats[row.key])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setShowPerf(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      <button type="button" className="btn btn-ghost" style={{ marginTop: "var(--space-5)" }} onClick={onReset}>
        Start new review
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx jest src/components/StatsDisplay.test.jsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx jest`
Expected: PASS — full frontend suite green, including `App.test.jsx` (Tasks 4-5) and `ReportTable.test.jsx` (Task 3).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/StatsDisplay.jsx frontend/src/components/StatsDisplay.test.jsx
git commit -m "feat: replace inline timing card with a performance breakdown popup"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend && python -m pytest -v` — all green.
- [ ] Run the full frontend suite: `cd frontend && CI=true npx jest` — all green.
- [ ] Rebuild and restart affected containers: `docker compose up -d --build backend frontend` (per the Global Constraints note — a source-only edit does not update a running container).
- [ ] Manually verify in the browser: upload a project, confirm the header shows the project's name once polling starts, confirm the Report view renders per-category tables with Meets/Fails/Not evaluated labels, toggle to Debug info and back, open the Performance breakdown popup and confirm the Compiling & Lint (Gradle) row appears with a real duration, close it via both the Close button and a backdrop click.
