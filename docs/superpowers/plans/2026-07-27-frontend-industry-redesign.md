# Frontend Industry Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing real React frontend (upload → progress → findings → download) to match the Industry design system handoff pixel-for-pixel, and add the one backend field (`total_score_pct`) the redesign needs.

**Architecture:** Vendor a trimmed Industry design-system stylesheet (`design-system.css`) and 6 inline-SVG icon components (`icons.jsx`) as shared frontend infrastructure; restyle each existing component in place using those classes/icons while preserving all existing state machines, polling logic, and the `services/api.js` contract; add a small pure aggregation helper on the backend and thread it through the existing progress response.

**Tech Stack:** React 19 (CRA, plain `.jsx`), Tailwind (unchanged, minor layout only), FastAPI/Python backend, pytest, React Testing Library / Jest.

## Global Constraints

- No new npm runtime dependencies (icons are inline SVG, not `lucide-react`; no `tailwind.config.js` token changes).
- No new backend dependencies; `total_score_pct` is a plain pure-function addition.
- Preserve the 2000ms polling interval and the existing "always HTTP 200, check `status`/`error` in body" error contract — do not change `services/api.js`.
- No responsive/mobile breakpoints, no dark mode (out of scope per the design handoff).
- Design tokens (colors, spacing, fonts) must match `/Users/mehroshmehboob/Downloads/designs/styles.css` values exactly where vendored.
- No demo-failure affordance anywhere in the shipped UI.

---

### Task 1: Backend — `compute_total_score_pct` helper

**Files:**
- Modify: `backend/app/analyzer/excel_handler.py:28-44` (add function after `aggregate_category_scores`)
- Test: `backend/tests/test_excel_handler.py`

**Interfaces:**
- Produces: `compute_total_score_pct(scores_by_category: dict) -> float | None` — `scores_by_category` is a dict of `category_id -> {"avg_points", "final_points", "percent_points", "sub_scores"}` (the same shape `aggregate_category_scores` returns, keyed by category id, as built in `backend/app/api/reviews.py`'s `_run_review`). Returns the mean of every category's `percent_points` that is not `None`, rounded to 1 decimal; returns `None` if no category has a score.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_excel_handler.py`, right after the existing `test_aggregate_category_scores_all_none_stays_none` test (and add `compute_total_score_pct` to the existing import block at the top of the file):

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    extract_sub_criteria_descriptions,
    generate_review_excel,
    populate_metadata,
    populate_scores,
)
```

```python
def test_compute_total_score_pct_averages_category_percentages():
    scores_by_category = {
        "1": {"avg_points": 0.9, "final_points": 0.9, "percent_points": 90.0, "sub_scores": {}},
        "2": {"avg_points": 0.6, "final_points": 0.6, "percent_points": 60.0, "sub_scores": {}},
    }
    assert compute_total_score_pct(scores_by_category) == 75.0


def test_compute_total_score_pct_skips_categories_with_no_score():
    scores_by_category = {
        "1": {"avg_points": 1.0, "final_points": 1.0, "percent_points": 100.0, "sub_scores": {}},
        "2": {"avg_points": None, "final_points": None, "percent_points": None, "sub_scores": {}},
    }
    assert compute_total_score_pct(scores_by_category) == 100.0


def test_compute_total_score_pct_returns_none_when_no_category_has_a_score():
    scores_by_category = {
        "1": {"avg_points": None, "final_points": None, "percent_points": None, "sub_scores": {}},
    }
    assert compute_total_score_pct(scores_by_category) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_excel_handler.py -v`
Expected: the three new tests FAIL with `ImportError: cannot import name 'compute_total_score_pct'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/analyzer/excel_handler.py`, insert immediately after the `aggregate_category_scores` function (after line 44, before the blank line that precedes `_normalize_id`):

```python
def compute_total_score_pct(scores_by_category: dict) -> float | None:
    values = [
        result["percent_points"]
        for result in scores_by_category.values()
        if result.get("percent_points") is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_excel_handler.py -v`
Expected: all tests PASS, including the 3 new ones.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/excel_handler.py backend/tests/test_excel_handler.py
git commit -m "feat: add compute_total_score_pct helper for aggregate review scoring"
```

---

### Task 2: Backend — wire `total_score_pct` into the reviews API

**Files:**
- Modify: `backend/app/api/reviews.py:16-20` (import), `:38-50` (`_new_review_state`), `:133-144` (scoring block), `:190-201` (`get_progress` response)
- Test: `backend/tests/test_reviews_progress.py`, `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `compute_total_score_pct(scores_by_category: dict) -> float | None` from Task 1.
- Produces: `GET /api/reviews/{review_id}/progress` response now includes `total_score_pct: number | null`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_progress.py`, update `test_progress_reflects_stored_state` to add the new field to both the stored state and the assertions:

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
```

And update `test_progress_defaults_detection_fields_when_absent` to also assert the new field defaults to `None` when the stored state (an older/"legacy" shape) doesn't have the key at all:

```python
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
```

In `backend/tests/test_reviews_integration.py`, add an assertion right after the existing `assert final_state["warnings"] == []` line (inside `test_full_review_pipeline_in_stub_mode`):

```python
        # Stub mode scores every sub-criterion 1 (perfect) across all 5
        # CATEGORIES, so every category's percent_points is 100.0 and the
        # mean across categories is exactly 100.0.
        assert final_state["total_score_pct"] == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_reviews_progress.py tests/test_reviews_integration.py -v`
Expected: `test_progress_reflects_stored_state`, `test_progress_defaults_detection_fields_when_absent`, and `test_full_review_pipeline_in_stub_mode` FAIL with `KeyError: 'total_score_pct'`.

- [ ] **Step 3: Implement the wiring**

In `backend/app/api/reviews.py`, update the import block (lines 16-20):

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    extract_sub_criteria_descriptions,
    generate_review_excel,
)
```

Add the new default field to `_new_review_state` (lines 38-50):

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
    }
```

Compute it right after the scoring loop finishes, in the scoring block (around line 144) — add the new line immediately after `stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)`:

```python
        stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)
        state["total_score_pct"] = compute_total_score_pct(scores_by_category)
```

Add it to the `get_progress` response dict (lines 190-201):

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
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/ -v`
Expected: all tests PASS (full backend suite, to catch any other consumer of these dicts).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_progress.py backend/tests/test_reviews_integration.py
git commit -m "feat: surface total_score_pct in the review progress response"
```

---

### Task 3: Frontend — vendor design-system tokens, icons, and corner marks

**Files:**
- Create: `frontend/src/design-system.css`
- Create: `frontend/src/icons.jsx`
- Create: `frontend/src/components/CornerMarks.jsx`
- Modify: `frontend/src/index.js:1-4` (import the new stylesheet)

**Interfaces:**
- Produces (consumed by Tasks 4-8):
  - CSS classes available globally: `.blueprint`, `.corner` (`.tl`/`.tr`/`.bl`/`.br`), `.elev-md`, `.card`, `.card-kicker`, `.card-title`, `.card-body`, `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-block`, `.field`, `.input`, `.tag`, `.tag-accent`, `.tag-outline`, `.nav`, `.nav-brand`, `.table`, `.text-muted`, plus CSS vars `--color-bg`, `--color-text`, `--color-accent`, `--color-accent-100/700/800/900`, `--color-divider`, `--color-surface`, `--font-heading`, `--font-body`, `--space-1` through `--space-10`, `--radius-md`, `--shadow-md`, and a `spin` keyframe.
  - `frontend/src/icons.jsx` exports: `FileIcon`, `CheckCircleIcon`, `SpinnerIcon`, `CircleIcon`, `DownloadIcon`, `ArrowRightIcon` — each `({ size }) => JSX`, sized in pixels, default sizes matching their usage (`FileIcon` 16, `CheckCircleIcon`/`SpinnerIcon`/`CircleIcon` 18, `DownloadIcon`/`ArrowRightIcon` 14).
  - `frontend/src/components/CornerMarks.jsx` default-exports a component rendering the 4 `<i className="corner tl/tr/bl/br">` marks — drop into any `.blueprint` element's children.

- [ ] **Step 1: Create `design-system.css`**

Create `frontend/src/design-system.css`:

```css
/* Industry design system — vendored subset (tokens + the component classes
   this app actually uses). Source: design handoff styles.css. */
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;700&family=Barlow+Condensed:wght@400;600&display=swap');

:root {
  --color-bg: #f2f2f3;
  --color-surface: #e9e9ea;
  --color-text: #1d1f20;
  --color-accent: #5980a6;
  --color-divider: color-mix(in srgb, #1d1f20 16%, transparent);

  --color-accent-100: #eef6ff;
  --color-accent-700: #416180;
  --color-accent-800: #2c455d;
  --color-accent-900: #1d2d3d;

  --font-heading: "Barlow Condensed", system-ui, sans-serif;
  --font-heading-weight: 600;
  --font-body: "Barlow", system-ui, sans-serif;

  --space-1: 3.4px;
  --space-2: 6.8px;
  --space-3: 10.2px;
  --space-4: 13.6px;
  --space-5: 17px;
  --space-6: 20.4px;
  --space-8: 27.2px;
  --space-10: 34px;

  --radius-md: 4px;

  --shadow-md: 0 3px 10px color-mix(in srgb, #2b2b2d 16%, transparent);
}

@keyframes spin { to { transform: rotate(360deg); } }

/* — blueprint frame: hairline border + "+" registration marks per corner — */
.blueprint {
  position: relative;
  border: 1px solid var(--color-divider);
  border-radius: 0;
}
.blueprint > .corner {
  position: absolute; width: 11px; height: 11px;
  color: color-mix(in srgb, var(--color-text) 55%, transparent);
}
.blueprint > .corner::before, .blueprint > .corner::after {
  content: ""; position: absolute; background: currentColor;
}
.blueprint > .corner::before { left: 5px; top: 0; width: 1px; height: 100%; }
.blueprint > .corner::after  { top: 5px; left: 0; width: 100%; height: 1px; }
.blueprint > .corner.tl { top: -6px; left: -6px; }
.blueprint > .corner.tr { top: -6px; right: -6px; }
.blueprint > .corner.bl { bottom: -6px; left: -6px; }
.blueprint > .corner.br { bottom: -6px; right: -6px; }

.elev-md { box-shadow: var(--shadow-md); }

/* — cards — */
.card {
  display: flex; flex-direction: column; gap: var(--space-2);
  border-radius: 0; background: transparent;
}
.card-kicker { font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--color-accent); }
.card-title {
  font-family: var(--font-heading); font-weight: var(--font-heading-weight);
  font-size: 17px; line-height: 1.2; color: var(--color-text);
}
.card-body { margin: 0; font-size: 13px; opacity: 0.8; color: var(--color-text); }

/* — buttons — */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  cursor: pointer; text-decoration: none;
  font-family: var(--font-heading); font-weight: var(--font-heading-weight);
  font-size: 14px; line-height: 1.2; color: var(--color-text);
  background: transparent; border: 1px solid var(--color-divider);
  padding: var(--space-2) calc(var(--space-3) * 1.2);
  border-radius: 0;
}
.btn svg { display: block; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary { background: var(--color-accent); color: var(--color-bg); border-color: var(--color-accent); }
.btn-primary:hover:not(:disabled) { background: var(--color-accent-700); }
.btn-ghost { color: var(--color-accent); border-color: transparent; padding-inline: var(--space-1); }
.btn-ghost:hover { background: color-mix(in srgb, var(--color-accent) 10%, transparent); }
.btn-block { width: 100%; }

/* — forms — */
.field > label {
  display: block; font-size: 12px; margin-bottom: 5px;
  color: color-mix(in srgb, var(--color-text) 70%, transparent);
}
.input {
  width: 100%; min-height: 36px; padding: 6px 10px; font: inherit;
  font-size: 14px; color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-divider); border-radius: 0;
}

/* — tags — */
.tag {
  display: inline-flex; align-items: center; font-size: 11px;
  letter-spacing: 0.02em; padding: 3px 10px; border-radius: 0;
}
.tag-accent { background: var(--color-accent-100); color: var(--color-accent-800); }
.tag-outline { border: 1px solid var(--color-accent); color: var(--color-accent); }

/* — navigation — */
.nav {
  display: flex; align-items: center; gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
}
.nav-brand {
  font-family: var(--font-heading); font-weight: var(--font-heading-weight);
  font-size: 18px;
}

/* — tables — */
.table { width: 100%; border-collapse: collapse; font-size: 14px; }
.table th {
  text-align: left; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
  color: color-mix(in srgb, var(--color-text) 60%, transparent);
  padding: var(--space-2); border-bottom: 1px solid var(--color-divider);
}
.table td {
  padding: var(--space-2);
  border-bottom: 1px solid color-mix(in srgb, var(--color-text) 8%, transparent);
}
.text-muted { color: color-mix(in srgb, var(--color-text) 55%, transparent); }
```

- [ ] **Step 2: Create `icons.jsx`**

Create `frontend/src/icons.jsx`:

```jsx
export function FileIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

export function CheckCircleIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-700)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function SpinnerIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" style={{ animation: "spin 1s linear infinite" }}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

export function CircleIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.35 }}>
      <circle cx="12" cy="12" r="10" />
    </svg>
  );
}

export function DownloadIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 15V3" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

export function ArrowRightIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}
```

- [ ] **Step 3: Create `CornerMarks.jsx`**

Create `frontend/src/components/CornerMarks.jsx`:

```jsx
export default function CornerMarks() {
  return (
    <>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
    </>
  );
}
```

- [ ] **Step 4: Import the stylesheet**

In `frontend/src/index.js`, add the import right after `import './index.css';` (line 3):

```js
import './index.css';
import './design-system.css';
```

- [ ] **Step 5: Verify nothing broke**

Run: `cd frontend && CI=true npm test -- --watchAll=false`
Expected: the full existing suite still PASSES unchanged (these are pure additions — no existing component imports the new files yet).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/design-system.css frontend/src/icons.jsx frontend/src/components/CornerMarks.jsx frontend/src/index.js
git commit -m "feat: vendor Industry design-system tokens, icons, and corner marks"
```

---

### Task 4: Frontend — restyle `UploadForm`

**Files:**
- Modify: `frontend/src/components/UploadForm.jsx` (full rewrite)
- Test: `frontend/src/components/UploadForm.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `CornerMarks` (default export, Task 3), `FileIcon`/`ArrowRightIcon` from `../icons` (Task 3).
- Produces (unchanged from before): `UploadForm({ onSubmit, disabled })` — `onSubmit(androidZipFile, excelTemplateFile)` called only after both files pass extension validation. New behavior: the submit button is disabled until both files are chosen (in addition to the existing `disabled` prop), and reads "Starting review…" while `disabled` is true.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/UploadForm.test.jsx` entirely:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

test("calls onSubmit with both files when extensions are valid", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith(zip, xlsx);
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const notAZip = buildFile("project.txt", "text/plain");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), notAZip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByText(/must be a \.zip file/i)).toBeInTheDocument();
});

test("disables the start button until both files are chosen", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  expect(screen.getByRole("button", { name: /start review/i })).toBeEnabled();
});

test("disables inputs and shows the starting label when disabled prop is true", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} />);
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: /starting review/i })).toBeDisabled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- UploadForm --watchAll=false`
Expected: FAIL — old implementation has no "scoring template" label, no disabled-until-both-chosen behavior, and no "Starting review…" text.

- [ ] **Step 3: Implement the restyled component**

Replace `frontend/src/components/UploadForm.jsx` entirely:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";
import { FileIcon, ArrowRightIcon } from "../icons";

export default function UploadForm({ onSubmit, disabled }) {
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [validationError, setValidationError] = useState("");

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

      {validationError && <p className="card-body" style={{ color: "#b3261e" }}>{validationError}</p>}

      <button
        type="submit"
        className="btn btn-primary btn-block blueprint"
        style={{ marginTop: "var(--space-5)" }}
        disabled={disabled || !canStart}
      >
        <CornerMarks />
        {disabled ? "Starting review…" : "Start review"}
        <ArrowRightIcon />
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- UploadForm --watchAll=false`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx
git commit -m "feat: restyle UploadForm as the Industry blueprint idle card"
```

---

### Task 5: Frontend — restyle `ProgressTracker`

**Files:**
- Modify: `frontend/src/components/ProgressTracker.jsx` (full rewrite)
- Test: `frontend/src/components/ProgressTracker.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `CornerMarks` (Task 3), `CheckCircleIcon`/`SpinnerIcon`/`CircleIcon` from `../icons` (Task 3), `getProgress(reviewId)` from `../services/api` (unchanged).
- Produces (unchanged prop contract): `ProgressTracker({ reviewId, onUpdate })` — same 2000ms polling loop, calls `onUpdate(data)` on every poll, stops polling once `status !== "processing"`. New visual: a 4-row step list (Extracting archive / Analyzing code / Scoring with AI / Generating report) instead of a numeric bar; backend `phase` maps to a step index (`pending` → -1, `extracting`→0, `analyzing`→1, `scoring`→2, `generating`→3, `completed`/`error`→4); the active row shows the backend's live `message` as subtext.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/ProgressTracker.test.jsx` entirely:

```jsx
import { act, render, screen } from "@testing-library/react";
import ProgressTracker from "./ProgressTracker";
import { getProgress } from "../services/api";

jest.mock("../services/api");

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

test("shows all four steps before the first poll resolves", () => {
  getProgress.mockReturnValue(new Promise(() => {}));

  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);

  expect(screen.getByText("Extracting archive")).toBeInTheDocument();
  expect(screen.getByText("Analyzing code")).toBeInTheDocument();
  expect(screen.getByText("Scoring with AI")).toBeInTheDocument();
  expect(screen.getByText("Generating report")).toBeInTheDocument();
});

test("polls immediately on mount and shows the active phase's live message", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting project files...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  const onUpdate = jest.fn();

  render(<ProgressTracker reviewId="abc-123" onUpdate={onUpdate} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledWith("abc-123");
  expect(screen.getByText("Extracting project files...")).toBeInTheDocument();
  expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ phase: "extracting" }));
});

test("shows the scoring phase's per-category message as subtext", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60,
    message: "Evaluating Reliability, Security & Observability...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(screen.getByText("Evaluating Reliability, Security & Observability...")).toBeInTheDocument();
});

test("polls again after 2000ms while status is processing", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60, message: "Scoring...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(2);
});

test("stops polling once status is completed", async () => {
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: 78,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- ProgressTracker --watchAll=false`
Expected: FAIL — old implementation renders a "phase" label and a percentage bar, not the 4 named steps.

- [ ] **Step 3: Implement the restyled component**

Replace `frontend/src/components/ProgressTracker.jsx` entirely:

```jsx
import { useEffect, useState } from "react";
import { getProgress } from "../services/api";
import CornerMarks from "./CornerMarks";
import { CheckCircleIcon, SpinnerIcon, CircleIcon } from "../icons";

const POLL_INTERVAL_MS = 2000;

const STEPS = [
  { phase: "extracting", label: "Extracting archive" },
  { phase: "analyzing", label: "Analyzing code" },
  { phase: "scoring", label: "Scoring with AI" },
  { phase: "generating", label: "Generating report" },
];

function stepIndexForPhase(phase) {
  if (phase === "completed" || phase === "error") return STEPS.length;
  return STEPS.findIndex((step) => step.phase === phase);
}

export default function ProgressTracker({ reviewId, onUpdate }) {
  const [progressData, setProgressData] = useState(null);

  useEffect(() => {
    let intervalId;
    let cancelled = false;

    async function poll() {
      const data = await getProgress(reviewId);
      if (cancelled) return;
      setProgressData(data);
      onUpdate(data);
      if (data.status !== "processing") {
        clearInterval(intervalId);
      }
    }

    poll();
    intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [reviewId, onUpdate]);

  const phase = progressData?.phase ?? "pending";
  const message = progressData?.message ?? "";
  const currentIndex = stepIndexForPhase(phase);

  return (
    <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
      <CornerMarks />
      <div className="card-kicker">Step 2 of 2</div>
      <div className="card-title" style={{ fontSize: 20 }}>Reviewing your project</div>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-5)" }}>
        {STEPS.map((step, index) => {
          const done = currentIndex > index || currentIndex === STEPS.length;
          const active = index === currentIndex;
          return (
            <div key={step.phase} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", padding: "var(--space-2) 0" }}>
              {done && <CheckCircleIcon />}
              {active && <SpinnerIcon />}
              {!done && !active && <CircleIcon />}
              <div>
                <span style={{ opacity: done || active ? 1 : 0.5 }}>{step.label}</span>
                {active && message && (
                  <p className="text-muted" style={{ margin: 0, fontSize: 12 }}>{message}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- ProgressTracker --watchAll=false`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressTracker.jsx frontend/src/components/ProgressTracker.test.jsx
git commit -m "feat: restyle ProgressTracker as the Industry 4-step list"
```

---

### Task 6: Frontend — restyle `FindingsPanel` with expandable cards

**Files:**
- Modify: `frontend/src/components/FindingsPanel.jsx` (full rewrite)
- Test: `frontend/src/components/FindingsPanel.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `CornerMarks` (Task 3).
- Produces: `FindingsPanel({ warnings, testCoverage, secretsFound })` — same prop names/shapes as before (`warnings: string[]`, `testCoverage: number | null`, `secretsFound: {file, line, pattern}[]`). Renders `null` only when all three are empty/null. Otherwise renders all 3 cards (Warnings / Test coverage / Secrets found); Warnings and Secrets cards toggle an expanded list on click when they have entries. Consumed directly by `App.jsx` (Task 8, running state) and internally by `StatsDisplay` (Task 7, completed state).

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/FindingsPanel.test.jsx` entirely:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings at all", () => {
  const { container } = render(<FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} />);
  expect(container.firstChild).toBeNull();
});

test("shows all three cards once any finding is present, with placeholders for absent ones", () => {
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml"]} testCoverage={null} secretsFound={[]} />);

  expect(screen.getByText("Warnings")).toBeInTheDocument();
  expect(screen.getByText("Test coverage")).toBeInTheDocument();
  expect(screen.getByText("No coverage report found.")).toBeInTheDocument();
  expect(screen.getByText("Secrets found")).toBeInTheDocument();
  expect(screen.getByText("No secrets found.")).toBeInTheDocument();
});

test("shows the coverage percentage and secret summary when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText("82.5%")).toBeInTheDocument();
  expect(screen.getByText("1 possible secret found")).toBeInTheDocument();
});

test("expands the warnings card to list every warning on click", async () => {
  const user = userEvent.setup();
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml", "Outdated Gradle plugin"]} testCoverage={null} secretsFound={[]} />);

  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
  await user.click(screen.getByText("2 issues found"));
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByText("Outdated Gradle plugin")).toBeInTheDocument();
});

test("expands the secrets card to list file:line (pattern) for every secret on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={null}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );

  await user.click(screen.getByText("1 possible secret found"));
  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- FindingsPanel --watchAll=false`
Expected: FAIL — old implementation hides the coverage card when null and never renders an expandable list.

- [ ] **Step 3: Implement the restyled component**

Replace `frontend/src/components/FindingsPanel.jsx` entirely:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";

function FindingCard({ kicker, value, caption, expandable, expanded, onToggle, children }) {
  return (
    <div className="card blueprint" style={{ padding: "var(--space-4)" }}>
      <CornerMarks />
      <div className="card-kicker">{kicker}</div>
      <div className="card-title" style={{ fontSize: 32 }}>{value}</div>
      {expandable ? (
        <button
          type="button"
          className="card-body"
          style={{ textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit" }}
          onClick={onToggle}
        >
          {caption}
        </button>
      ) : (
        <p className="card-body">{caption}</p>
      )}
      {expanded && children}
    </div>
  );
}

export default function FindingsPanel({ warnings, testCoverage, secretsFound }) {
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [secretsOpen, setSecretsOpen] = useState(false);

  const hasWarnings = warnings && warnings.length > 0;
  const hasSecrets = secretsFound && secretsFound.length > 0;
  const hasCoverage = testCoverage !== null && testCoverage !== undefined;

  if (!hasWarnings && !hasSecrets && !hasCoverage) {
    return null;
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-4)" }}>
      <FindingCard
        kicker="Warnings"
        value={warnings.length}
        caption={hasWarnings ? `${warnings.length} issue${warnings.length === 1 ? "" : "s"} found` : "No warnings found."}
        expandable={hasWarnings}
        expanded={warningsOpen}
        onToggle={() => setWarningsOpen((open) => !open)}
      >
        <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.1em", fontSize: 13 }}>
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      </FindingCard>

      <FindingCard
        kicker="Test coverage"
        value={hasCoverage ? `${testCoverage}%` : "—"}
        caption={hasCoverage ? "Coverage report found." : "No coverage report found."}
        expandable={false}
      />

      <FindingCard
        kicker="Secrets found"
        value={secretsFound.length}
        caption={hasSecrets ? `${secretsFound.length} possible secret${secretsFound.length === 1 ? "" : "s"} found` : "No secrets found."}
        expandable={hasSecrets}
        expanded={secretsOpen}
        onToggle={() => setSecretsOpen((open) => !open)}
      >
        <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.1em", fontSize: 13 }}>
          {secretsFound.map((secret, index) => (
            <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
          ))}
        </ul>
      </FindingCard>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- FindingsPanel --watchAll=false`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FindingsPanel.jsx frontend/src/components/FindingsPanel.test.jsx
git commit -m "feat: restyle FindingsPanel as expandable Industry cards"
```

---

### Task 7: Frontend — restyle `StatsDisplay` as the completed screen

**Files:**
- Modify: `frontend/src/components/StatsDisplay.jsx` (full rewrite)
- Test: `frontend/src/components/StatsDisplay.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `CornerMarks` (Task 3), `DownloadIcon` from `../icons` (Task 3), `FindingsPanel` (Task 6, rendered internally for the design's "findings grid repeated below" section), `getDownloadUrl(downloadPath)` from `../services/api` (unchanged).
- Produces: `StatsDisplay({ totalScorePct, warnings, testCoverage, secretsFound, stats, downloadUrl, onReset })` — `totalScorePct: number | null`, `warnings`/`testCoverage`/`secretsFound` forwarded to the nested `FindingsPanel`, `stats: {ingest_time_ms?, analysis_time_ms?, scoring_time_ms?, generation_time_ms?, total_time_ms?}`, `downloadUrl: string`, `onReset: () => void` called when "Start new review" is clicked. This is a breaking prop-shape change from the previous `StatsDisplay({ stats, downloadUrl })` — Task 8 updates the only caller (`App.jsx`).

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/StatsDisplay.test.jsx` entirely:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatsDisplay from "./StatsDisplay";

const baseProps = {
  totalScorePct: 78,
  warnings: [],
  testCoverage: null,
  secretsFound: [],
  stats: {},
  downloadUrl: "/api/reviews/abc-123/download",
  onReset: () => {},
};

test("shows timing breakdown for each provided stat, formatted as seconds", () => {
  render(
    <StatsDisplay
      {...baseProps}
      stats={{ ingest_time_ms: 800, analysis_time_ms: 2100, scoring_time_ms: 11400, generation_time_ms: 600, total_time_ms: 14900 }}
    />
  );

  expect(screen.getByText("0.8s")).toBeInTheDocument();
  expect(screen.getByText("14.9s")).toBeInTheDocument();
});

test("shows the total score tag when totalScorePct is present", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={78} />);
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
});

test("omits the total score tag when totalScorePct is null", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={null} />);
  expect(screen.queryByText(/^Total/)).not.toBeInTheDocument();
});

test("shows warning and secret counts as outline tags", () => {
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml"]}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText("1 warnings")).toBeInTheDocument();
  expect(screen.getByText("1 secrets")).toBeInTheDocument();
});

test("renders a download link pointing at the constructed download URL", () => {
  render(<StatsDisplay {...baseProps} />);
  const link = screen.getByRole("link", { name: /download populated workbook/i });
  expect(link).toHaveAttribute("href", "http://localhost:8000/api/reviews/abc-123/download");
  expect(link).toHaveAttribute("download");
});

test("calls onReset when Start new review is clicked", async () => {
  const user = userEvent.setup();
  const onReset = jest.fn();
  render(<StatsDisplay {...baseProps} onReset={onReset} />);
  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(onReset).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- StatsDisplay --watchAll=false`
Expected: FAIL — old implementation has no `totalScorePct`/`warnings`/`secretsFound`/`onReset` props and the old "Download Result" link text/ms-formatted timings.

- [ ] **Step 3: Implement the restyled component**

Replace `frontend/src/components/StatsDisplay.jsx` entirely:

```jsx
import CornerMarks from "./CornerMarks";
import FindingsPanel from "./FindingsPanel";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

const TIMING_ROWS = [
  { key: "ingest_time_ms", label: "Ingest (unzip + validate)" },
  { key: "analysis_time_ms", label: "Analysis (parsing + secrets + versions)" },
  { key: "scoring_time_ms", label: "Scoring (Azure OpenAI)" },
  { key: "generation_time_ms", label: "Generation (Excel write)" },
  { key: "total_time_ms", label: "Total" },
];

export default function StatsDisplay({
  totalScorePct, warnings, testCoverage, secretsFound, stats, downloadUrl, onReset,
}) {
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
      </div>

      <div style={{ marginTop: "var(--space-5)" }}>
        <FindingsPanel warnings={warnings} testCoverage={testCoverage} secretsFound={secretsFound} />
      </div>

      <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-5)" }}>
        <CornerMarks />
        <div className="card-kicker">Timing</div>
        <div className="card-title" style={{ fontSize: 20 }}>Performance breakdown</div>
        <table className="table" style={{ marginTop: "var(--space-4)" }}>
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
      </div>

      <button type="button" className="btn btn-ghost" style={{ marginTop: "var(--space-5)" }} onClick={onReset}>
        Start new review
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- StatsDisplay --watchAll=false`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatsDisplay.jsx frontend/src/components/StatsDisplay.test.jsx
git commit -m "feat: restyle StatsDisplay as the Industry completed screen"
```

---

### Task 8: Frontend — restyle `App.jsx` page shell and wire the redesigned components together

**Files:**
- Modify: `frontend/src/App.jsx` (full rewrite)
- Test: `frontend/src/App.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `CornerMarks` (Task 3), restyled `UploadForm`/`ProgressTracker`/`FindingsPanel`/`StatsDisplay` (Tasks 4-7), `createReview` from `../services/api` (unchanged).
- Produces: the complete page — nav bar + title/description shell (constant across phases) wrapping whichever phase card is active. No new external interface; this is the app's root component.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/App.test.jsx` entirely:

```jsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { createReview, getProgress } from "./services/api";

jest.mock("./services/api", () => ({
  ...jest.requireActual("./services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

async function uploadValidFiles(user) {
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));
}

test("full happy path: upload, poll, complete, download link, reset", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/review ready/i)).toBeInTheDocument();
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download populated workbook/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/failed to start review/i)).toBeInTheDocument();
});

test("shows an error message when the review itself fails during processing, and Try again resets to idle", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /try again/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- App.test --watchAll=false`
Expected: FAIL — old implementation shows "Review Complete"/"Download Result" text and has no "Try again" button.

- [ ] **Step 3: Implement the restyled shell**

Replace `frontend/src/App.jsx` entirely:

```jsx
import { useCallback, useState } from "react";
import UploadForm from "./components/UploadForm";
import ProgressTracker from "./components/ProgressTracker";
import FindingsPanel from "./components/FindingsPanel";
import StatsDisplay from "./components/StatsDisplay";
import CornerMarks from "./components/CornerMarks";
import { createReview } from "./services/api";

export default function App() {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const result = await createReview(androidZip, excelTemplate);
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

  const handleProgressUpdate = useCallback((data) => {
    setProgressData(data);
    if (data.status === "completed") {
      setState("completed");
    } else if (data.status === "error") {
      setErrorMessage(data.error || "Review failed");
      setState("error");
    }
  }, []);

  function handleReset() {
    setState("idle");
    setReviewId(null);
    setProgressData(null);
    setErrorMessage("");
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Android Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Upload an Android project and a scoring template. The reviewer analyzes structure, security, tests and
            dependency versions, scores each category with AI, and hands back a populated workbook.
          </p>
        </header>

        {(state === "idle" || state === "uploading") && (
          <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
        )}

        {state === "polling" && reviewId && (
          <>
            <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
            {progressData && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <FindingsPanel
                  warnings={progressData.warnings}
                  testCoverage={progressData.test_coverage}
                  secretsFound={progressData.secrets_found}
                />
              </div>
            )}
          </>
        )}

        {state === "completed" && progressData && (
          <StatsDisplay
            totalScorePct={progressData.total_score_pct}
            warnings={progressData.warnings}
            testCoverage={progressData.test_coverage}
            secretsFound={progressData.secrets_found}
            stats={progressData.stats}
            downloadUrl={progressData.download_url}
            onReset={handleReset}
          />
        )}

        {state === "error" && (
          <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
            <CornerMarks />
            <div className="card-kicker">Error</div>
            <div className="card-title" style={{ fontSize: 20 }}>Review failed</div>
            <p className="card-body">{errorMessage}</p>
            <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              <button type="button" className="btn btn-primary blueprint" onClick={handleReset}>
                <CornerMarks />
                Try again
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- --watchAll=false`
Expected: the ENTIRE frontend suite (App, UploadForm, ProgressTracker, FindingsPanel, StatsDisplay, api) PASSES.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: restyle App page shell with Industry nav/header and wire redesigned components"
```

---

## Final Verification

After Task 8, run both full suites once more to confirm the whole feature works end to end:

```bash
cd backend && source venv/bin/activate && pytest -v
cd frontend && CI=true npm test -- --watchAll=false
```

Both must PASS with zero failures before considering this plan complete.
