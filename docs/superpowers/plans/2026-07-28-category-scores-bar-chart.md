# Category Scores Bar Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a live-filling, per-category bar chart (the 5 scoring "heads") on both the running and completed screens, backed by a new `category_scores` field on the existing `/progress` endpoint.

**Architecture:** Expose data that already exists internally (`scores_by_category`'s `percent_points` per category) through the progress response, seeded with all 5 categories at `null` and updated in place as each finishes scoring. Render it with a new Recharts-based horizontal bar chart component, reused on both the running screen (App.jsx) and the completed screen (StatsDisplay.jsx).

**Tech Stack:** FastAPI/Python backend (unchanged stack), React 19 frontend, new dependency: `recharts`.

## Global Constraints

- No status/threshold bar coloring — single accent hue (`var(--color-accent)`) for every scored bar, consistent with the existing mono-accent Industry design system.
- No dark mode theming for the chart — the app has no dark mode today.
- No new backend computation — `category_scores` only exposes values already computed by the existing `aggregate_category_scores` call in the scoring loop.
- The chart only appears once the "Scoring with AI" step has started (`phase === "scoring"` or later) on the running screen; it's always shown on the completed screen (all categories are resolved by then).
- Bar mark spec: ~20px thick, 4px rounded end at the value tip, square at the baseline, direct percentage label at the tip (or "Pending…" for unscored categories).

---

### Task 1: Backend — expose `category_scores` progressively

**Files:**
- Modify: `backend/app/api/reviews.py:39-52` (`_new_review_state`), `:139-146` (scoring loop), `:193-205` (`get_progress` response)
- Test: `backend/tests/test_reviews_create.py`, `backend/tests/test_reviews_progress.py`

**Interfaces:**
- Produces: `GET /api/reviews/{review_id}/progress` response gains `category_scores: {id: string, name: string, percent_points: number | null}[]`, one entry per `CATEGORIES` key in `CATEGORIES` iteration order, seeded at `null` and updated in place as each category's scoring resolves.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_create.py`, add this test after `test_run_review_updates_message_per_category_during_scoring`:

```python
async def test_run_review_updates_category_scores_progressively(monkeypatch):
    review_id = "category-scores-progress-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    assert _reviews[review_id]["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": None},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
        {"id": "3", "name": "Delivery Discipline & Architecture", "percent_points": None},
        {"id": "4", "name": "AI Usage & Code Ownership", "percent_points": None},
        {"id": "6", "name": "Safe & Integrated AI Code", "percent_points": None},
    ]

    snapshots = []

    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        return {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    # Snapshot taken right before each category is scored: earlier categories
    # already show their resolved percent_points (stub mode always scores 1,
    # i.e. 100.0%), later ones are still None -- proves updates land in place
    # without disturbing sibling entries.
    assert snapshots[0] == [("1", None), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[1] == [("1", 100.0), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[4] == [("1", 100.0), ("2", 100.0), ("3", 100.0), ("4", 100.0), ("6", None)]

    final_scores = _reviews[review_id]["category_scores"]
    assert all(entry["percent_points"] == 100.0 for entry in final_scores)
```

In `backend/tests/test_reviews_progress.py`, update `test_progress_reflects_stored_state` to add the new field:

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
        "category_scores": [
            {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
            {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
        ],
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
    assert body["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
    ]
```

And update `test_progress_defaults_detection_fields_when_absent` to assert the default:

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
    assert body["category_scores"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_reviews_create.py tests/test_reviews_progress.py -v`
Expected: the new test and the two updated tests FAIL — `test_run_review_updates_category_scores_progressively` with `KeyError: 'category_scores'`, the two progress tests on the `category_scores` assertion.

- [ ] **Step 3: Implement the wiring**

In `backend/app/api/reviews.py`, add `category_scores` to `_new_review_state` (lines 39-52), seeded from `CATEGORIES`:

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
        "category_scores": [
            {"id": category_id, "name": category["name"], "percent_points": None}
            for category_id, category in CATEGORIES.items()
        ],
    }
```

Update the scoring loop (around line 144) to update the matching entry in place right after aggregating that category's result — `state["category_scores"]` was seeded in the same `CATEGORIES` iteration order as this loop's `enumerate`, so `index` addresses the right entry directly:

```python
        for index, (category_id, category) in enumerate(CATEGORIES.items()):
            state["message"] = f"Evaluating {category['name']}..."
            sub_results = await score_category(
                category["name"], category["sub_criteria"], sub_criteria_descriptions, code_context
            )
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
            state["category_scores"][index]["percent_points"] = scores_by_category[category_id]["percent_points"]
            state["progress"] = 50 + int(30 * (index + 1) / category_count)
```

Add it to the `get_progress` response (lines 193-205):

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
        "category_scores": state.get("category_scores", []),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest -v`
Expected: all tests PASS (full backend suite).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_progress.py
git commit -m "feat: expose per-category scores progressively in the progress response"
```

---

### Task 2: Frontend — add `recharts` and build `CategoryScoresChart`

**Files:**
- Modify: `frontend/package.json` (via `npm install`)
- Create: `frontend/src/components/CategoryScoresChart.jsx`
- Test: `frontend/src/components/CategoryScoresChart.test.jsx`

**Interfaces:**
- Consumes: `CornerMarks` (default export, from `./CornerMarks`), `recharts`'s `Bar`/`BarChart`/`Cell`/`LabelList`/`Tooltip`/`XAxis`/`YAxis`.
- Produces: `CategoryScoresChart({ categoryScores })` — `categoryScores: {id, name, percent_points: number | null}[]`. Consumed by `App.jsx` (Task 3, running screen) and `StatsDisplay.jsx` (Task 3, completed screen).

- [ ] **Step 1: Install the dependency**

```bash
cd frontend && npm install recharts
```

If npm reports a peer-dependency conflict against React 19 (recharts' peer range may lag the latest React major), retry with `npm install recharts --legacy-peer-deps`. Confirm afterward that `frontend/package.json`'s `dependencies` now lists `recharts` and that `CI=true npm test -- --watchAll=false` (the existing suite) still passes before continuing.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/components/CategoryScoresChart.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import CategoryScoresChart from "./CategoryScoresChart";

const categoryScores = [
  { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
  { id: "2", name: "Reliability, Security & Observability", percent_points: 75.5 },
  { id: "3", name: "Delivery Discipline & Architecture", percent_points: null },
];

test("renders a labeled bar for each scored category", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
  expect(screen.getByText("Reliability, Security & Observability")).toBeInTheDocument();
  expect(screen.getByText("75.5%")).toBeInTheDocument();
});

test("renders a Pending label instead of a percentage for unscored categories", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getByText("Delivery Discipline & Architecture")).toBeInTheDocument();
  expect(screen.getByText("Pending…")).toBeInTheDocument();
});

test("renders one row per category in a mixed scored/pending list", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getAllByText(/^(Pending…|[\d.]+%)$/)).toHaveLength(3);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- CategoryScoresChart --watchAll=false`
Expected: FAIL — `Cannot find module './CategoryScoresChart'` (the component doesn't exist yet).

- [ ] **Step 4: Implement the component**

Create `frontend/src/components/CategoryScoresChart.jsx`:

```jsx
import { Bar, BarChart, Cell, LabelList, Tooltip, XAxis, YAxis } from "recharts";
import CornerMarks from "./CornerMarks";

const ROW_HEIGHT = 40;
const CHART_WIDTH = 820;
const CHART_MARGIN = { top: 8, right: 56, bottom: 8, left: 8 };

function isPending(entry) {
  return entry.percent_points === null || entry.percent_points === undefined;
}

function ValueLabel({ x, y, width, height, index, data }) {
  const entry = data[index];
  const pending = isPending(entry);
  const label = pending ? "Pending…" : `${entry.percent_points}%`;
  const labelX = pending ? x + 8 : x + width + 8;
  return (
    <text x={labelX} y={y + height / 2} dy={4} fontSize={12} fill="var(--color-text)" opacity={pending ? 0.5 : 1}>
      {label}
    </text>
  );
}

function CategoryTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const entry = payload[0].payload;
  return (
    <div className="card blueprint" style={{ padding: "var(--space-2) var(--space-3)", background: "var(--color-bg)" }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{entry.name}</div>
      <div style={{ fontSize: 12 }}>{isPending(entry) ? "Not yet scored" : `${entry.percent_points}%`}</div>
    </div>
  );
}

export default function CategoryScoresChart({ categoryScores }) {
  const data = categoryScores.map((entry) => ({ ...entry, value: entry.percent_points ?? 0 }));

  return (
    <div className="card blueprint" style={{ padding: "var(--space-4)" }}>
      <CornerMarks />
      <div className="card-kicker">Category scores</div>
      <BarChart
        width={CHART_WIDTH}
        height={data.length * ROW_HEIGHT + CHART_MARGIN.top + CHART_MARGIN.bottom}
        data={data}
        layout="vertical"
        margin={CHART_MARGIN}
      >
        <XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={260} tick={{ fontSize: 12 }} />
        <Tooltip
          content={<CategoryTooltip />}
          cursor={{ fill: "color-mix(in srgb, var(--color-text) 6%, transparent)" }}
        />
        <Bar dataKey="value" barSize={20} radius={[0, 4, 4, 0]} isAnimationActive={true}>
          {data.map((entry) => (
            <Cell
              key={entry.id}
              fill={isPending(entry) ? "color-mix(in srgb, var(--color-text) 10%, transparent)" : "var(--color-accent)"}
            />
          ))}
          <LabelList content={(props) => <ValueLabel {...props} data={data} />} />
        </Bar>
      </BarChart>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- CategoryScoresChart --watchAll=false`
Expected: all 3 tests PASS. If Recharts' `LabelList`/`Bar` render differently than expected in jsdom (e.g. a prop name mismatch), adjust `ValueLabel`'s prop usage to match what Recharts actually passes — verify by temporarily logging `props` inside `ValueLabel` if a test fails on missing text.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/CategoryScoresChart.jsx frontend/src/components/CategoryScoresChart.test.jsx
git commit -m "feat: add CategoryScoresChart component backed by recharts"
```

---

### Task 3: Frontend — wire the chart into the running and completed screens

**Files:**
- Modify: `frontend/src/App.jsx`, `frontend/src/components/StatsDisplay.jsx`
- Test: `frontend/src/App.test.jsx`, `frontend/src/components/StatsDisplay.test.jsx`

**Interfaces:**
- Consumes: `CategoryScoresChart({ categoryScores })` (Task 2).
- Produces: `StatsDisplay` gains a new required prop `categoryScores` (breaking change to its prop shape, same pattern as the earlier `totalScorePct` addition) — `App.jsx` is the only caller and is updated in the same task.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/StatsDisplay.test.jsx`, add `categoryScores` to `baseProps` and add a new test. Update the top of the file:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatsDisplay from "./StatsDisplay";

const baseProps = {
  totalScorePct: 78,
  warnings: [],
  testCoverage: null,
  secretsFound: [],
  categoryScores: [
    { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
    { id: "2", name: "Reliability, Security & Observability", percent_points: 60.0 },
  ],
  stats: {},
  downloadUrl: "/api/reviews/abc-123/download",
  onReset: () => {},
};
```

Add this test after the existing `"shows warning and secret counts as outline tags"` test:

```jsx
test("renders the category scores chart with every category's score", () => {
  render(<StatsDisplay {...baseProps} />);
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
  expect(screen.getByText("Reliability, Security & Observability")).toBeInTheDocument();
  expect(screen.getByText("60%")).toBeInTheDocument();
});
```

In `frontend/src/App.test.jsx`, add `category_scores` to the completed-review mock in the happy-path test:

```jsx
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    category_scores: [
      { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
    ],
  });
```

and add an assertion in the same test, right after the existing `Total 78%` assertion:

```jsx
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
```

Also add `category_scores: []` to the other `getProgress.mockResolvedValue` call in `App.test.jsx` (the "review itself fails" test) so its fixture stays internally consistent with the real API shape — that one doesn't need a new assertion since it never reaches the completed screen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- StatsDisplay App.test --watchAll=false`
Expected: FAIL — `StatsDisplay` doesn't accept/render `categoryScores` yet; the `App.test.jsx` assertion for the category name won't be found.

- [ ] **Step 3: Wire `StatsDisplay.jsx`**

In `frontend/src/components/StatsDisplay.jsx`, add the import and prop, and render the chart between the result card and the findings grid:

```jsx
import CornerMarks from "./CornerMarks";
import FindingsPanel from "./FindingsPanel";
import CategoryScoresChart from "./CategoryScoresChart";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";
```

```jsx
export default function StatsDisplay({
  totalScorePct, warnings, testCoverage, secretsFound, categoryScores, stats, downloadUrl, onReset,
}) {
```

Insert the chart right after the closing `</div>` of the first `card blueprint elev-md` result card and before the existing `<FindingsPanel .../>` block:

```jsx
      <div style={{ marginTop: "var(--space-5)" }}>
        <CategoryScoresChart categoryScores={categoryScores} />
      </div>

      <div style={{ marginTop: "var(--space-5)" }}>
        <FindingsPanel warnings={warnings} testCoverage={testCoverage} secretsFound={secretsFound} />
      </div>
```

- [ ] **Step 4: Wire `App.jsx`**

Add the import:

```jsx
import CategoryScoresChart from "./components/CategoryScoresChart";
```

Pass `categoryScores` through to `StatsDisplay`:

```jsx
        {state === "completed" && progressData && (
          <StatsDisplay
            totalScorePct={progressData.total_score_pct}
            warnings={progressData.warnings}
            testCoverage={progressData.test_coverage}
            secretsFound={progressData.secrets_found}
            categoryScores={progressData.category_scores}
            stats={progressData.stats}
            downloadUrl={progressData.download_url}
            onReset={handleReset}
          />
        )}
```

Add the chart to the running screen, gated on the scoring step having started, between `ProgressTracker` and `FindingsPanel`:

```jsx
        {state === "polling" && reviewId && (
          <>
            <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
            {progressData && ["scoring", "generating"].includes(progressData.phase) && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <CategoryScoresChart categoryScores={progressData.category_scores} />
              </div>
            )}
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- --watchAll=false`
Expected: the entire frontend suite PASSES.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx frontend/src/components/StatsDisplay.jsx frontend/src/components/StatsDisplay.test.jsx
git commit -m "feat: show category scores chart on running and completed screens"
```

---

## Final Verification

```bash
cd backend && source venv/bin/activate && pytest -v
cd frontend && CI=true npm test -- --watchAll=false
```

Both must PASS with zero failures before considering this plan complete.
