# Dashboard Filters & Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the main dashboard's project-sidebar/single-project view with an org-wide filter bar (Year/Platform/Project, all searchable), an aggregate overview (progress rings: average score + per-category averages) over whatever the filters currently match, and a results table listing every matching review.

**Architecture:** A new `GET /api/reviews` (filtered, org-wide list) and `GET /api/reviews/years` (distinct years) back the frontend. The frontend does all aggregation client-side from the one fetched list -- no backend aggregation endpoint. `ProjectSidebar.jsx` and `ProjectReviewHistory.jsx` are deleted; their project-create/rename dialog is relocated into a new shared `ProjectDialog.jsx`, reused by both the filter bar's Project dropdown and a new "Start review" dialog that also now hosts the platform picker and LLM-provider picker (both relocated from the old sidebar's right panel).

**Tech Stack:** FastAPI + SQLAlchemy (existing), React + a hand-rolled SVG progress ring (no new dependency -- Recharts' `RadialBarChart` was verified during planning not to reliably render its data-driven sector in this app's jsdom test environment).

## Global Constraints

- "Domains" (user's term) = this app's existing `platform` field (Android/iOS/.NET/Web (React)) -- no new data model.
- Year filter is always exactly one specific year (no "All years" option), defaulting to the current calendar year.
- Platform and Project filters default to "All" (no filter on that dimension).
- The results table **includes errored reviews** (matches today's per-project table); the overview's averages **exclude errored reviews** (they have no score).
- Ring color thresholds: red `<60`, orange `60-79`, green `>=80`.
- No new npm/pip dependencies.
- All new backend tests run against in-memory SQLite (existing convention, no live Postgres needed).

---

## File Structure

- Modify: `backend/app/db/crud.py` -- add `list_reviews`, `list_review_years`
- Modify: `backend/app/api/reviews.py` -- add `GET /api/reviews`, `GET /api/reviews/years`; relocate `_review_summary_to_dict` here (shared with `projects.py`)
- Modify: `backend/app/api/projects.py` -- import the relocated `_review_summary_to_dict` instead of defining its own copy
- Test: `backend/tests/test_db_crud.py` (extend), `backend/tests/test_reviews_list.py` (new)
- Modify: `frontend/src/services/api.js` -- add `getReviews`, `getReviewYears`
- Create: `frontend/src/components/SearchableSelect.jsx` -- generic type-to-filter single-select dropdown
- Create: `frontend/src/components/ProjectDialog.jsx` -- relocated from `ProjectSidebar.jsx`, shared create/rename dialog
- Create: `frontend/src/components/ProgressRing.jsx` -- hand-rolled SVG ring + `scoreTier` helper
- Create: `frontend/src/components/DashboardOverview.jsx`
- Create: `frontend/src/components/DashboardResultsTable.jsx`
- Create: `frontend/src/components/DashboardFilters.jsx`
- Create: `frontend/src/components/StartReviewDialog.jsx`
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx` -- full rewrite
- Modify: `frontend/src/pages/ProjectDashboardPage.test.jsx` -- full rewrite
- Delete: `frontend/src/components/ProjectSidebar.jsx`, `frontend/src/components/ProjectSidebar.test.jsx`
- Delete: `frontend/src/components/ProjectReviewHistory.jsx`, `frontend/src/components/ProjectReviewHistory.test.jsx`

---

### Task 1: `crud.list_reviews` and `crud.list_review_years`

**Files:**
- Modify: `backend/app/db/crud.py`
- Test: `backend/tests/test_db_crud.py`

**Interfaces:**
- Consumes: `app.db.models.PlatformReview` (existing)
- Produces: `crud.list_reviews(session, year: int, platform: str | None = None, project_id: str | None = None) -> list[PlatformReview]` (newest first, includes errored reviews, no status filter), `crud.list_review_years(session) -> list[int]` (distinct years with any review data, sorted ascending) -- both used by Task 2's endpoints.

- [ ] **Step 1: Write the failing tests**

Find the existing `_persist` helper near the bottom of `backend/tests/test_db_crud.py` (used by `test_get_review_by_id_*` and `test_list_reviews_for_project_*`). Add a `status` parameter to it so these new tests can create errored reviews too:

```python
async def _persist(session, review_id, project_id=None, platform="Android", created_at=None, total_score_pct=None, status="pending_approval"):
    return await crud.persist_review_result(
        session,
        review_id=review_id,
        project_id=project_id,
        platform=platform,
        status=status,
        project_name="MyApp",
        created_at=created_at or datetime.now(timezone.utc),
        completed_at=created_at or datetime.now(timezone.utc),
        total_score_pct=total_score_pct,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path=None,
        result_data={"category_scores": []},
    )
```

(This replaces the existing `_persist` definition -- same body, just the new `status="pending_approval"` parameter and passing `status=status` instead of the hardcoded `status="pending_approval"` string.)

Then append at the end of the file:

```python
async def test_list_reviews_filters_by_year(session):
    await _persist(session, "r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", created_at=datetime(2024, 6, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews(session, year=2025)

    assert [r.id for r in reviews] == ["r1"]


async def test_list_reviews_filters_by_platform(session):
    await _persist(session, "r1", platform=".NET", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", platform="Android", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews(session, year=2025, platform=".NET")

    assert [r.id for r in reviews] == ["r1"]


async def test_list_reviews_filters_by_project_id(session):
    await crud.create_project(session, project_id="p1", name="Payments")
    await crud.create_project(session, project_id="p2", name="Other")
    await _persist(session, "r1", project_id="p1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", project_id="p2", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews(session, year=2025, project_id="p1")

    assert [r.id for r in reviews] == ["r1"]


async def test_list_reviews_includes_errored_reviews(session):
    await _persist(session, "r1", status="pending_approval", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", status="error", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews(session, year=2025)

    assert sorted(r.id for r in reviews) == ["r1", "r2"]


async def test_list_reviews_orders_newest_first(session):
    await _persist(session, "r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews(session, year=2025)

    assert [r.id for r in reviews] == ["r1", "r2"]


async def test_list_review_years_returns_distinct_years_sorted(session):
    await _persist(session, "r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    await _persist(session, "r3", created_at=datetime(2025, 9, 1, tzinfo=timezone.utc))

    years = await crud.list_review_years(session)

    assert years == [2024, 2025]


async def test_list_review_years_returns_empty_list_when_no_reviews(session):
    years = await crud.list_review_years(session)

    assert years == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_db_crud.py -v -k "list_reviews or list_review_years"`
Expected: FAIL with `AttributeError: module 'app.db.crud' has no attribute 'list_reviews'`

- [ ] **Step 3: Implement**

In `backend/app/db/crud.py`, add `extract` to the existing `from sqlalchemy import delete, select` import line (making it `from sqlalchemy import delete, extract, select`), then add these two functions after `list_reviews_for_project`:

```python
async def list_reviews(
    session: AsyncSession,
    year: int,
    platform: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[PlatformReview]:
    query = select(PlatformReview).where(extract("year", PlatformReview.created_at) == year)
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if project_id:
        query = query.where(PlatformReview.project_id == project_id)
    query = query.order_by(PlatformReview.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_review_years(session: AsyncSession) -> list[int]:
    result = await session.execute(select(extract("year", PlatformReview.created_at)).distinct())
    return sorted({int(year) for (year,) in result.all()})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_db_crud.py -v -k "list_reviews or list_review_years"`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full backend suite to confirm the `_persist` signature change didn't break anything**

Run: `cd backend && venv/bin/python -m pytest tests/test_db_crud.py -v`
Expected: all tests in this file PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/crud.py backend/tests/test_db_crud.py
git commit -m "feat: add crud.list_reviews and crud.list_review_years"
```

---

### Task 2: `GET /api/reviews` and `GET /api/reviews/years`

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/api/projects.py`
- Test: `backend/tests/test_reviews_list.py` (new)

**Interfaces:**
- Consumes: `crud.list_reviews`, `crud.list_review_years` (Task 1)
- Produces: `GET /api/reviews?year=<int>&platform=<str,optional>&project_id=<str,optional>` -> `{"reviews": [...]}` (same trimmed shape as `GET /api/projects/{id}/reviews`: `id`, `project_id`, `project_name`, `platform`, `status`, `created_at`, `completed_at`, `total_score_pct`, `category_scores: [{id, name, percent_points}]`). `GET /api/reviews/years` -> `{"years": [2024, 2025, ...]}`.

- [ ] **Step 1: Relocate `_review_summary_to_dict` from `projects.py` into `reviews.py`**

In `backend/app/api/projects.py`, remove this function entirely:

```python
def _review_summary_to_dict(review) -> dict:
    result_data = review.result_data or {}
    return {
        "id": review.id,
        "platform": review.platform,
        "status": review.status,
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "total_score_pct": float(review.total_score_pct) if review.total_score_pct is not None else None,
        # Trimmed to just id/name/percent_points -- the dashboard's
        # per-clause chart doesn't need sub_criteria/remarks, and this
        # endpoint already returns every review for a project in one call.
        "category_scores": [
            {"id": category.get("id"), "name": category.get("name"), "percent_points": category.get("percent_points")}
            for category in result_data.get("category_scores", [])
        ],
    }
```

Replace it with an import from `reviews.py` at the top of `projects.py` (add to the existing imports):

```python
from app.api.reviews import _review_summary_to_dict
```

`projects.py`'s `list_project_reviews` endpoint (which calls `_review_summary_to_dict(r)` for each review) is otherwise unchanged.

In `backend/app/api/reviews.py`, add the relocated function right before the `GET /api/reviews/{review_id}/progress` route (i.e. right before line ~505, before every `{review_id}`-pattern route in the file -- this ordering matters, see Step 3), with `project_id` added to its output (the version in `projects.py` omitted it since it was always implicitly the one project being listed; the new org-wide endpoint needs it since results span multiple projects):

```python
def _review_summary_to_dict(review) -> dict:
    result_data = review.result_data or {}
    return {
        "id": review.id,
        "project_id": review.project_id,
        "project_name": review.project_name,
        "platform": review.platform,
        "status": review.status,
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "total_score_pct": float(review.total_score_pct) if review.total_score_pct is not None else None,
        "category_scores": [
            {"id": category.get("id"), "name": category.get("name"), "percent_points": category.get("percent_points")}
            for category in result_data.get("category_scores", [])
        ],
    }
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_reviews_list.py`:

```python
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
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


async def _persist(sessionmaker, review_id, project_id=None, platform="Android", created_at=None, status="pending_approval", total_score_pct=80.0):
    async with sessionmaker() as session:
        await crud.persist_review_result(
            session,
            review_id=review_id,
            project_id=project_id,
            platform=platform,
            status=status,
            project_name="MyApp",
            created_at=created_at or datetime.now(timezone.utc),
            completed_at=created_at or datetime.now(timezone.utc),
            total_score_pct=total_score_pct,
            llm_provider="azure",
            llm_model=None,
            compile_check_mode="compiler",
            source="upload",
            workbook_path=None,
            result_data={"category_scores": [{"id": "1", "name": "Structure", "percent_points": 80.0}]},
        )


async def test_list_reviews_filters_by_year_platform_and_project(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", project_id="p1", platform=".NET", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", project_id="p1", platform="Android", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r3", project_id="p2", platform=".NET", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025, "platform": ".NET", "project_id": "p1"})

    assert response.status_code == 200
    reviews = response.json()["reviews"]
    assert [r["id"] for r in reviews] == ["r1"]
    assert reviews[0]["category_scores"] == [{"id": "1", "name": "Structure", "percent_points": 80.0}]
    assert reviews[0]["project_id"] == "p1"


async def test_list_reviews_with_only_year_returns_everything_that_year(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", project_id="p1", platform=".NET", created_at=datetime(2025, 3, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", project_id="p2", platform="Android", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025})

    assert sorted(r["id"] for r in response.json()["reviews"]) == ["r1", "r2"]


async def test_list_reviews_includes_errored_reviews(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", status="pending_approval", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", status="error", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews", params={"year": 2025})

    assert sorted(r["id"] for r in response.json()["reviews"]) == ["r1", "r2"]


def test_list_reviews_requires_year(test_sessionmaker):
    response = client.get("/api/reviews")

    assert response.status_code == 422


async def test_list_review_years_returns_distinct_years_sorted(test_sessionmaker):
    await _persist(test_sessionmaker, "r1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    await _persist(test_sessionmaker, "r2", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))

    response = client.get("/api/reviews/years")

    assert response.status_code == 200
    assert response.json() == {"years": [2024, 2025]}


def test_list_review_years_returns_empty_when_no_reviews(test_sessionmaker):
    response = client.get("/api/reviews/years")

    assert response.json() == {"years": []}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_list.py -v`
Expected: FAIL with 404s (routes don't exist yet)

- [ ] **Step 4: Implement the endpoints**

In `backend/app/api/reviews.py`, add these two routes immediately after the `_review_summary_to_dict` function added in Step 1, and **before** `@router.get("/api/reviews/{review_id}/progress")` (route registration order matters: `/api/reviews/years` must be registered before `/api/reviews/{review_id}` or FastAPI would match "years" as a `review_id` path parameter instead):

```python
@router.get("/api/reviews")
async def list_reviews(year: int, platform: str | None = None, project_id: str | None = None):
    async with new_session() as session:
        reviews = await crud.list_reviews(session, year=year, platform=platform, project_id=project_id)
    return {"reviews": [_review_summary_to_dict(review) for review in reviews]}


@router.get("/api/reviews/years")
async def list_review_years():
    async with new_session() as session:
        years = await crud.list_review_years(session)
    return {"years": years}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_list.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && venv/bin/python -m pytest tests/ -q`
Expected: all tests pass (confirms the `_review_summary_to_dict` relocation didn't break `test_projects_api.py`)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/reviews.py backend/app/api/projects.py backend/tests/test_reviews_list.py
git commit -m "feat: add GET /api/reviews and GET /api/reviews/years"
```

---

### Task 3: Frontend API client functions

**Files:**
- Modify: `frontend/src/services/api.js`
- Test: `frontend/src/services/api.test.js`

**Interfaces:**
- Produces: `getReviews({year, platform, projectId}) -> Promise<Array>`, `getReviewYears() -> Promise<Array<number>>`

- [ ] **Step 1: Write the failing tests**

Add `getReviews, getReviewYears` to the existing import list at the top of `frontend/src/services/api.test.js`, then add this describe block after the `sendChatMessage` describe block at the end of the file:

```javascript
describe("getReviews", () => {
  it("sends year, platform, and projectId as query params and returns the reviews list", async () => {
    const reviews = [{ id: "r1", platform: ".NET", project_name: "Moove" }];
    axios.get.mockResolvedValue({ data: { reviews } });

    const result = await getReviews({ year: 2025, platform: ".NET", projectId: "p1" });

    expect(result).toEqual(reviews);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews"), {
      params: { year: 2025, platform: ".NET", project_id: "p1" },
    });
  });

  it("omits platform and project_id from params when not provided", async () => {
    axios.get.mockResolvedValue({ data: { reviews: [] } });

    await getReviews({ year: 2025 });

    const [, config] = axios.get.mock.calls[0];
    expect(config.params).toEqual({ year: 2025 });
  });
});

describe("getReviewYears", () => {
  it("fetches the distinct years with review data", async () => {
    axios.get.mockResolvedValue({ data: { years: [2024, 2025] } });

    const result = await getReviewYears();

    expect(result).toEqual([2024, 2025]);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews/years"));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: FAIL -- `getReviews`/`getReviewYears` not defined

- [ ] **Step 3: Implement**

Add to `frontend/src/services/api.js`, after `sendChatMessage`:

```javascript
export async function getReviews({ year, platform, projectId } = {}) {
  const params = { year };
  if (platform) params.platform = platform;
  if (projectId) params.project_id = projectId;
  const response = await axios.get(`${API_BASE_URL}/reviews`, { params });
  return response.data.reviews;
}

export async function getReviewYears() {
  const response = await axios.get(`${API_BASE_URL}/reviews/years`);
  return response.data.years;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js
git commit -m "feat: add getReviews and getReviewYears API client functions"
```

---

### Task 4: `SearchableSelect` component

**Files:**
- Create: `frontend/src/components/SearchableSelect.jsx`
- Test: `frontend/src/components/SearchableSelect.test.jsx`

**Interfaces:**
- Produces: `export default function SearchableSelect({ ariaLabel, options, value, onChange, placeholder, onAddNew, addNewLabel })`. `options: Array<{value: any, label: string}>`. Renders a button showing the selected option's label (or `placeholder`); clicking opens a panel with a search input + filtered option list + (if `onAddNew` provided) a trailing action row. Selecting an option calls `onChange(option.value)` and closes the panel. Clicking outside the component closes the panel. Used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/SearchableSelect.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchableSelect from "./SearchableSelect";

const options = [
  { value: null, label: "All platforms" },
  { value: "Android", label: "Android" },
  { value: ".NET", label: ".NET" },
  { value: "iOS", label: "iOS" },
];

test("shows the placeholder when nothing is selected", () => {
  render(<SearchableSelect ariaLabel="Platform" options={options} value={undefined} onChange={jest.fn()} placeholder="Choose…" />);
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("Choose…");
});

test("shows the selected option's label", () => {
  render(<SearchableSelect ariaLabel="Platform" options={options} value=".NET" onChange={jest.fn()} />);
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent(".NET");
});

test("clicking the trigger opens the option list", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));

  expect(screen.getByRole("button", { name: "Android" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: ".NET" })).toBeInTheDocument();
});

test("typing in the search box filters the option list", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.type(screen.getByLabelText(/search platform/i), "and");

  expect(screen.getByRole("button", { name: "Android" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: ".NET" })).not.toBeInTheDocument();
});

test("shows a 'No matches' message when the search filters everything out", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.type(screen.getByLabelText(/search platform/i), "zzz");

  expect(screen.getByText(/no matches/i)).toBeInTheDocument();
});

test("selecting an option calls onChange with its value and closes the panel", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={onChange} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(onChange).toHaveBeenCalledWith("Android");
  expect(screen.queryByLabelText(/search platform/i)).not.toBeInTheDocument();
});

test("clicking outside the component closes the panel", async () => {
  const user = userEvent.setup();
  render(
    <div>
      <SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />
      <button type="button">Outside</button>
    </div>
  );

  await user.click(screen.getByRole("button", { name: "Platform" }));
  expect(screen.getByLabelText(/search platform/i)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Outside" }));

  expect(screen.queryByLabelText(/search platform/i)).not.toBeInTheDocument();
});

test("renders the add-new action when onAddNew is provided, and calls it on click", async () => {
  const user = userEvent.setup();
  const onAddNew = jest.fn();
  render(
    <SearchableSelect
      ariaLabel="Project" options={options} value={null} onChange={jest.fn()}
      onAddNew={onAddNew} addNewLabel="+ Add new project"
    />
  );

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "+ Add new project" }));

  expect(onAddNew).toHaveBeenCalled();
});

test("does not render an add-new action when onAddNew is omitted", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));

  expect(screen.queryByText(/add new/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/SearchableSelect.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './SearchableSelect'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/SearchableSelect.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";

export default function SearchableSelect({ ariaLabel, options, value, onChange, placeholder = "Select…", onAddNew, addNewLabel }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = options.find((option) => option.value === value);
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));

  function handleSelect(option) {
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  function handleToggle() {
    setOpen((current) => !current);
    setQuery("");
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="input"
        aria-label={ariaLabel}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer", width: "100%" }}
        onClick={handleToggle}
      >
        <span>{selected ? selected.label : placeholder}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="card elev-md" style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50, padding: 8, maxHeight: 280, display: "flex", flexDirection: "column" }}>
          <input
            type="text"
            className="input"
            aria-label={`Search ${ariaLabel}`}
            placeholder="Search…"
            value={query}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
          <div style={{ overflowY: "auto", marginTop: 8 }}>
            {filtered.length === 0 && <p className="card-body" style={{ padding: "8px 4px" }}>No matches</p>}
            {filtered.map((option) => (
              <button
                key={option.value ?? "__all__"}
                type="button"
                className={`btn btn-block ${option.value === value ? "btn-primary" : ""}`}
                style={{ justifyContent: "flex-start", marginTop: 4 }}
                onClick={() => handleSelect(option)}
              >
                {option.label}
              </button>
            ))}
            {onAddNew && (
              <button
                type="button"
                className="btn btn-block btn-ghost"
                style={{ justifyContent: "flex-start", marginTop: 4 }}
                onClick={() => { setOpen(false); setQuery(""); onAddNew(); }}
              >
                {addNewLabel || "+ Add new"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/SearchableSelect.test.jsx --watchAll=false`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SearchableSelect.jsx frontend/src/components/SearchableSelect.test.jsx
git commit -m "feat: add SearchableSelect, a reusable type-to-filter dropdown"
```

---

### Task 5: `ProjectDialog` component (relocated)

**Files:**
- Create: `frontend/src/components/ProjectDialog.jsx`
- Test: `frontend/src/components/ProjectDialog.test.jsx`

**Interfaces:**
- Produces: `export default function ProjectDialog({ title, initialName, submitLabel, onSubmit, onClose })` -- identical behavior to the `ProjectDialog` currently defined inside `ProjectSidebar.jsx`, just moved to its own file so `DashboardFilters.jsx` (Task 9) and `StartReviewDialog.jsx` (Task 10) can both import it without duplicating it. `onSubmit` is an `async (name: string) => void` (throwing rejects show the error inline); calls `onClose()` after a successful submit.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ProjectDialog.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectDialog from "./ProjectDialog";

test("submitting calls onSubmit with the trimmed name, then onClose", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn().mockResolvedValue(undefined);
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.type(screen.getByLabelText(/project name/i), "  Payments  ");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(onSubmit).toHaveBeenCalledWith("Payments");
  expect(onClose).toHaveBeenCalled();
});

test("pre-fills the name field from initialName", () => {
  render(<ProjectDialog title="Rename project" initialName="Old Name" submitLabel="Save" onSubmit={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByLabelText(/project name/i)).toHaveValue("Old Name");
});

test("shows an error message and does not close when onSubmit rejects", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn().mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.type(screen.getByLabelText(/project name/i), "Payments");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

test("clicking Cancel calls onClose without submitting", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(onClose).toHaveBeenCalled();
});

test("the submit button is disabled when the name is empty", () => {
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByRole("button", { name: /create/i })).toBeDisabled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/ProjectDialog.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './ProjectDialog'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/ProjectDialog.jsx` (exact content currently inside `ProjectSidebar.jsx`'s local `ProjectDialog` function, unchanged):

```jsx
import { useState } from "react";

export default function ProjectDialog({ title, initialName, submitLabel, onSubmit, onClose }) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onSubmit(name.trim());
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">{title}</div>
        <div className="dialog-body">
          <div className="field">
            <label htmlFor="projectDialogName">Project name</label>
            <input
              id="projectDialogName"
              type="text"
              className="input"
              value={name}
              autoFocus
              disabled={saving}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? "Saving…" : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/ProjectDialog.test.jsx --watchAll=false`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProjectDialog.jsx frontend/src/components/ProjectDialog.test.jsx
git commit -m "feat: extract ProjectDialog into its own reusable component"
```

---

### Task 6: `ProgressRing` component

**Files:**
- Create: `frontend/src/components/ProgressRing.jsx`
- Test: `frontend/src/components/ProgressRing.test.jsx`

**Interfaces:**
- Produces: `export function scoreTier(value: number | null | undefined) -> "red" | "orange" | "green" | "unknown"` (red `<60`, orange `60-79`, green `>=80`). `export default function ProgressRing({ value, label, size = 120, strokeWidth = 10 })` -- renders an SVG ring colored by `scoreTier(value)`, the percentage (`value.toFixed(1) + "%"`, or "—" when `value` is `null`/`undefined`) in the center, `label` captioned below. Root element has `data-tier={scoreTier(value)}` for test/style targeting. Used by Task 7.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ProgressRing.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import ProgressRing, { scoreTier } from "./ProgressRing";

describe("scoreTier", () => {
  test("classifies red below 60", () => {
    expect(scoreTier(0)).toBe("red");
    expect(scoreTier(59.9)).toBe("red");
  });

  test("classifies orange from 60 to 79.9", () => {
    expect(scoreTier(60)).toBe("orange");
    expect(scoreTier(79.9)).toBe("orange");
  });

  test("classifies green at 80 and above", () => {
    expect(scoreTier(80)).toBe("green");
    expect(scoreTier(100)).toBe("green");
  });

  test("classifies null/undefined as unknown", () => {
    expect(scoreTier(null)).toBe("unknown");
    expect(scoreTier(undefined)).toBe("unknown");
  });
});

test("renders the percentage and label", () => {
  render(<ProgressRing value={74.5} label="Final Score" />);
  expect(screen.getByText("74.5%")).toBeInTheDocument();
  expect(screen.getByText("Final Score")).toBeInTheDocument();
});

test("renders an em dash when value is null", () => {
  render(<ProgressRing value={null} label="Security" />);
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("exposes the score tier as a data attribute for styling/testing", () => {
  const { container } = render(<ProgressRing value={90} label="Final Score" />);
  expect(container.querySelector('[data-tier="green"]')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/ProgressRing.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './ProgressRing'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/ProgressRing.jsx`:

```jsx
export function scoreTier(value) {
  if (value === null || value === undefined) return "unknown";
  if (value >= 80) return "green";
  if (value >= 60) return "orange";
  return "red";
}

const TIER_COLORS = { green: "#2E9E6B", orange: "#E4A72E", red: "#E4402C", unknown: "#C9D1DE" };

export default function ProgressRing({ value, label, size = 120, strokeWidth = 10 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  const offset = circumference * (1 - clamped / 100);
  const tier = scoreTier(value);

  return (
    <div style={{ display: "grid", justifyItems: "center", gap: 6 }} data-tier={tier}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-divider)" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={TIER_COLORS[tier]} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fontSize={size / 5} fontWeight="700" fill="var(--color-text)">
          {value === null || value === undefined ? "—" : `${value.toFixed(1)}%`}
        </text>
      </svg>
      <div className="card-body" style={{ textAlign: "center", fontWeight: 600, fontSize: 13 }}>{label}</div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/ProgressRing.test.jsx --watchAll=false`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressRing.jsx frontend/src/components/ProgressRing.test.jsx
git commit -m "feat: add ProgressRing, a hand-rolled SVG score ring"
```

---

### Task 7: `DashboardOverview` component

**Files:**
- Create: `frontend/src/components/DashboardOverview.jsx`
- Test: `frontend/src/components/DashboardOverview.test.jsx`

**Interfaces:**
- Consumes: `ProgressRing` (Task 6)
- Produces: `export default function DashboardOverview({ reviews })`. `reviews` is the array `GET /api/reviews` returns (each with `status`, `total_score_pct`, `category_scores: [{name, percent_points}]`). Computes and renders: a "Final Score" ring (average `total_score_pct` across non-`"error"` reviews) with a "Based on N review(s)" caption, and one ring per distinct category `name` present in those same reviews (average `percent_points` for that name, skipping `null`/`undefined` values). Shows an empty-state message instead when there are zero non-error reviews.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/DashboardOverview.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import DashboardOverview from "./DashboardOverview";

function buildReview(overrides) {
  return {
    id: "r", status: "pending_approval", total_score_pct: 80,
    category_scores: [{ id: "1", name: "Structure", percent_points: 80 }],
    ...overrides,
  };
}

test("shows an empty state when there are no non-error reviews", () => {
  render(<DashboardOverview reviews={[buildReview({ status: "error", total_score_pct: null, category_scores: [] })]} />);
  expect(screen.getByText(/no scored reviews match/i)).toBeInTheDocument();
});

test("shows an empty state when there are zero reviews at all", () => {
  render(<DashboardOverview reviews={[]} />);
  expect(screen.getByText(/no scored reviews match/i)).toBeInTheDocument();
});

test("renders the Final Score as the average total_score_pct across non-error reviews", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", total_score_pct: 80 }),
    buildReview({ id: "r2", total_score_pct: 60 }),
  ]} />);

  expect(screen.getByText("70.0%")).toBeInTheDocument();
  expect(screen.getByText("Final Score")).toBeInTheDocument();
});

test("excludes errored reviews from the Final Score average", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", total_score_pct: 80 }),
    buildReview({ id: "r2", status: "error", total_score_pct: null, category_scores: [] }),
  ]} />);

  expect(screen.getByText("80.0%")).toBeInTheDocument();
});

test("shows how many reviews the Final Score is based on", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1" }),
    buildReview({ id: "r2" }),
    buildReview({ id: "r3", status: "error", total_score_pct: null, category_scores: [] }),
  ]} />);

  expect(screen.getByText(/based on 2 reviews/i)).toBeInTheDocument();
});

test("uses singular wording for exactly one review", () => {
  render(<DashboardOverview reviews={[buildReview({ id: "r1" })]} />);
  expect(screen.getByText(/based on 1 review$/i)).toBeInTheDocument();
});

test("renders one ring per distinct category name, averaging percent_points across reviews that have it", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", category_scores: [{ id: "2", name: "Security", percent_points: 40 }] }),
    buildReview({ id: "r2", category_scores: [{ id: "2", name: "Security", percent_points: 90 }] }),
  ]} />);

  expect(screen.getByText("Security")).toBeInTheDocument();
  expect(screen.getByText("65.0%")).toBeInTheDocument();
});

test("skips null percent_points when averaging a category", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", category_scores: [{ id: "2", name: "Security", percent_points: 100 }] }),
    buildReview({ id: "r2", category_scores: [{ id: "2", name: "Security", percent_points: null }] }),
  ]} />);

  expect(screen.getByText("100.0%")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardOverview.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './DashboardOverview'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/DashboardOverview.jsx`:

```jsx
import ProgressRing from "./ProgressRing";

function average(values) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export default function DashboardOverview({ reviews }) {
  const scored = reviews.filter((review) => review.status !== "error");

  if (scored.length === 0) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-body">No scored reviews match these filters yet.</p>
      </div>
    );
  }

  const overallAverage = average(scored.map((review) => review.total_score_pct).filter((value) => value !== null && value !== undefined));

  const byCategoryName = new Map();
  for (const review of scored) {
    for (const category of review.category_scores || []) {
      if (category.percent_points === null || category.percent_points === undefined) continue;
      if (!byCategoryName.has(category.name)) byCategoryName.set(category.name, []);
      byCategoryName.get(category.name).push(category.percent_points);
    }
  }
  const categoryAverages = [...byCategoryName.entries()].map(([name, values]) => ({ name, average: average(values) }));

  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>Overview</div>
      <div style={{ display: "flex", gap: "var(--space-5)", flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ display: "grid", justifyItems: "center" }}>
          <ProgressRing value={overallAverage} label="Final Score" size={160} strokeWidth={14} />
          <p className="card-body" style={{ margin: "6px 0 0" }}>
            Based on {scored.length} review{scored.length === 1 ? "" : "s"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap", alignItems: "flex-start" }}>
          {categoryAverages.map(({ name, average: categoryAverage }) => (
            <ProgressRing key={name} value={categoryAverage} label={name} size={100} strokeWidth={8} />
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardOverview.test.jsx --watchAll=false`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DashboardOverview.jsx frontend/src/components/DashboardOverview.test.jsx
git commit -m "feat: add DashboardOverview with Final Score and per-category rings"
```

---

### Task 8: `DashboardResultsTable` component

**Files:**
- Create: `frontend/src/components/DashboardResultsTable.jsx`
- Test: `frontend/src/components/DashboardResultsTable.test.jsx`

**Interfaces:**
- Produces: `export default function DashboardResultsTable({ reviews })`. Renders a table (Date/Project/Platform/Status/Score columns) with one row per review, including errored ones; row click navigates to `/reports/{review.id}`. Empty-state message when `reviews` is empty.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/DashboardResultsTable.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import DashboardResultsTable from "./DashboardResultsTable";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
});

function renderTable(reviews) {
  return render(
    <MemoryRouter>
      <DashboardResultsTable reviews={reviews} />
    </MemoryRouter>
  );
}

const reviews = [
  { id: "r1", project_name: "Moove", platform: ".NET", status: "pending_approval", created_at: "2026-08-01T00:00:00Z", total_score_pct: 80 },
  { id: "r2", project_name: "Payments", platform: "Android", status: "error", created_at: "2026-08-02T00:00:00Z", total_score_pct: null },
];

test("renders a row per review including errored ones, with the project name shown", () => {
  renderTable(reviews);

  expect(screen.getByText("Moove")).toBeInTheDocument();
  expect(screen.getByText("Payments")).toBeInTheDocument();
  expect(screen.getByText("Error")).toBeInTheDocument();
  expect(screen.getByText("80%")).toBeInTheDocument();
});

test("shows an em dash for a review with no score", () => {
  renderTable(reviews);
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("navigates to the report page when a row is clicked", async () => {
  const user = userEvent.setup();
  renderTable(reviews);

  await user.click(screen.getByText("Moove"));

  expect(mockNavigate).toHaveBeenCalledWith("/reports/r1");
});

test("shows an empty state when there are no reviews", () => {
  renderTable([]);
  expect(screen.getByText(/no reviews match/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardResultsTable.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './DashboardResultsTable'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/DashboardResultsTable.jsx`:

```jsx
import { useNavigate } from "react-router-dom";

const STATUS_LABELS = {
  pending_approval: "Pending approval",
  approved: "Approved",
  completed: "Completed",
  error: "Error",
};

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

export default function DashboardResultsTable({ reviews }) {
  const navigate = useNavigate();

  if (reviews.length === 0) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-body">No reviews match these filters.</p>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 20 }}>
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Project</th>
            <th>Platform</th>
            <th>Status</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((review) => (
            <tr key={review.id} onClick={() => navigate(`/reports/${review.id}`)} style={{ cursor: "pointer" }}>
              <td>{formatDate(review.created_at)}</td>
              <td>{review.project_name}</td>
              <td>{review.platform}</td>
              <td>{STATUS_LABELS[review.status] || review.status}</td>
              <td>{review.total_score_pct !== null && review.total_score_pct !== undefined ? `${review.total_score_pct}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardResultsTable.test.jsx --watchAll=false`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DashboardResultsTable.jsx frontend/src/components/DashboardResultsTable.test.jsx
git commit -m "feat: add DashboardResultsTable"
```

---

### Task 9: `DashboardFilters` component

**Files:**
- Create: `frontend/src/components/DashboardFilters.jsx`
- Test: `frontend/src/components/DashboardFilters.test.jsx`

**Interfaces:**
- Consumes: `SearchableSelect` (Task 4), `ProjectDialog` (Task 5), `createProject`/`updateProject` from `../services/api`, `PLATFORMS` from `../platforms`
- Produces: `export default function DashboardFilters({ year, years, onYearChange, platform, onPlatformChange, projectId, projects, onProjectChange, onProjectCreated, onProjectRenamed, onReset })`. Renders the Year/Platform/Project `SearchableSelect`s and a Reset button. The Project select's "+ Add new project" opens a `ProjectDialog`; on success calls `onProjectCreated(project)` then `onProjectChange(project.id)` (auto-selects the new project as the active filter). When `projectId` is not `null` (a specific project, not "All"), a rename (pencil) button appears next to the Project select, opening a `ProjectDialog` pre-filled with that project's current name; on success calls `onProjectRenamed(project)`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/DashboardFilters.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardFilters from "./DashboardFilters";
import { createProject, updateProject } from "../services/api";

jest.mock("../services/api");

const projects = [
  { id: "p1", name: "Payments Service" },
  { id: "p2", name: "Notifications" },
];

function renderFilters(overrides = {}) {
  return render(
    <DashboardFilters
      year={2026} years={[2025, 2026]} onYearChange={jest.fn()}
      platform={null} onPlatformChange={jest.fn()}
      projectId={null} projects={projects} onProjectChange={jest.fn()} onProjectCreated={jest.fn()} onProjectRenamed={jest.fn()}
      onReset={jest.fn()}
      {...overrides}
    />
  );
}

test("shows the current year, All platforms, and All projects by default", () => {
  renderFilters();
  expect(screen.getByRole("button", { name: "Year" })).toHaveTextContent("2026");
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
  expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("All projects");
});

test("selecting a year calls onYearChange", async () => {
  const user = userEvent.setup();
  const onYearChange = jest.fn();
  renderFilters({ onYearChange });

  await user.click(screen.getByRole("button", { name: "Year" }));
  await user.click(screen.getByRole("button", { name: "2025" }));

  expect(onYearChange).toHaveBeenCalledWith(2025);
});

test("selecting a platform calls onPlatformChange with the platform label", async () => {
  const user = userEvent.setup();
  const onPlatformChange = jest.fn();
  renderFilters({ onPlatformChange });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(onPlatformChange).toHaveBeenCalledWith("Android");
});

test("selecting a project calls onProjectChange with its id", async () => {
  const user = userEvent.setup();
  const onProjectChange = jest.fn();
  renderFilters({ onProjectChange });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));

  expect(onProjectChange).toHaveBeenCalledWith("p1");
});

test("clicking Reset filters calls onReset", async () => {
  const user = userEvent.setup();
  const onReset = jest.fn();
  renderFilters({ onReset });

  await user.click(screen.getByRole("button", { name: /reset filters/i }));

  expect(onReset).toHaveBeenCalled();
});

test("creating a new project via the Project dropdown calls onProjectCreated and selects it", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const onProjectChange = jest.fn();
  const newProject = { id: "p3", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  renderFilters({ onProjectCreated, onProjectChange });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(createProject).toHaveBeenCalledWith("New Project");
  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  expect(onProjectChange).toHaveBeenCalledWith("p3");
});

test("does not show a rename button when 'All projects' is selected", () => {
  renderFilters({ projectId: null });
  expect(screen.queryByRole("button", { name: /rename/i })).not.toBeInTheDocument();
});

test("shows a rename button when a specific project is selected, pre-filled with its current name", async () => {
  const user = userEvent.setup();
  renderFilters({ projectId: "p1" });

  await user.click(screen.getByRole("button", { name: /rename/i }));

  expect(screen.getByLabelText(/project name/i)).toHaveValue("Payments Service");
});

test("renaming the selected project calls updateProject and onProjectRenamed", async () => {
  const user = userEvent.setup();
  const onProjectRenamed = jest.fn();
  const updated = { id: "p1", name: "Payments Team" };
  updateProject.mockResolvedValue(updated);
  renderFilters({ projectId: "p1", onProjectRenamed });

  await user.click(screen.getByRole("button", { name: /rename/i }));
  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Payments Team");
  await user.click(screen.getByRole("button", { name: /save/i }));

  expect(updateProject).toHaveBeenCalledWith("p1", "Payments Team");
  expect(onProjectRenamed).toHaveBeenCalledWith(updated);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardFilters.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './DashboardFilters'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/DashboardFilters.jsx`:

```jsx
import { useState } from "react";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, updateProject } from "../services/api";

const ALL_PLATFORMS_OPTION = { value: null, label: "All platforms" };
const ALL_PROJECTS_OPTION = { value: null, label: "All projects" };

export default function DashboardFilters({
  year, years, onYearChange,
  platform, onPlatformChange,
  projectId, projects, onProjectChange, onProjectCreated, onProjectRenamed,
  onReset,
}) {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showRenameDialog, setShowRenameDialog] = useState(false);

  const yearOptions = years.map((y) => ({ value: y, label: String(y) }));
  const platformOptions = [ALL_PLATFORMS_OPTION, ...PLATFORMS.map((p) => ({ value: p.label, label: p.label }))];
  const projectOptions = [ALL_PROJECTS_OPTION, ...projects.map((p) => ({ value: p.id, label: p.name }))];
  const selectedProject = projects.find((p) => p.id === projectId);

  async function handleCreate(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    onProjectChange(project.id);
  }

  async function handleRename(name) {
    const updated = await updateProject(selectedProject.id, name);
    onProjectRenamed(updated);
  }

  return (
    <div className="card" style={{ padding: 20, display: "flex", gap: "var(--space-3)", alignItems: "flex-end", flexWrap: "wrap" }}>
      <div className="field" style={{ minWidth: 140 }}>
        <label htmlFor="filterYear">Year</label>
        <SearchableSelect ariaLabel="Year" options={yearOptions} value={year} onChange={onYearChange} />
      </div>
      <div className="field" style={{ minWidth: 200 }}>
        <label htmlFor="filterPlatform">Platform</label>
        <SearchableSelect ariaLabel="Platform" options={platformOptions} value={platform} onChange={onPlatformChange} />
      </div>
      <div className="field" style={{ minWidth: 240, flex: 1 }}>
        <label htmlFor="filterProject">Project</label>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <div style={{ flex: 1 }}>
            <SearchableSelect
              ariaLabel="Project" options={projectOptions} value={projectId} onChange={onProjectChange}
              onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
            />
          </div>
          {selectedProject && (
            <button
              type="button" className="btn btn-ghost" aria-label={`Rename ${selectedProject.name}`}
              style={{ flexShrink: 0 }}
              onClick={() => setShowRenameDialog(true)}
            >
              ✎
            </button>
          )}
        </div>
      </div>
      <button type="button" className="btn" onClick={onReset}>Reset filters</button>

      {showCreateDialog && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create"
          onSubmit={handleCreate} onClose={() => setShowCreateDialog(false)}
        />
      )}

      {showRenameDialog && selectedProject && (
        <ProjectDialog
          title="Rename project" initialName={selectedProject.name} submitLabel="Save"
          onSubmit={handleRename} onClose={() => setShowRenameDialog(false)}
        />
      )}
    </div>
  );
}
```

Note: the `<label htmlFor="filterYear">` etc. don't correspond to a real `id` on `SearchableSelect`'s internal button (it's `aria-label`-identified, not `id`-identified) -- this is intentionally the same pattern already used elsewhere in this codebase for button-based (not native `<input>`/`<select>`-based) form controls; the visible `<label>` is for sighted layout/spacing via the existing `.field` CSS class, and `aria-label` on `SearchableSelect` itself is what actually names it for accessibility/testing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/DashboardFilters.test.jsx --watchAll=false`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DashboardFilters.jsx frontend/src/components/DashboardFilters.test.jsx
git commit -m "feat: add DashboardFilters (year/platform/project + reset)"
```

---

### Task 10: `StartReviewDialog` component

**Files:**
- Create: `frontend/src/components/StartReviewDialog.jsx`
- Test: `frontend/src/components/StartReviewDialog.test.jsx`

**Interfaces:**
- Consumes: `SearchableSelect` (Task 4), `ProjectDialog` (Task 5), `PLATFORMS`, `getOllamaModels`/`createProject` from `../services/api`, `getLlmProvider`/`setLlmProvider`/`getOllamaModel`/`setOllamaModel` from `../services/llmProviderStorage`
- Produces: `export default function StartReviewDialog({ projects, onProjectCreated, onClose })`. Lets the user pick a project (or create one inline), an LLM provider/model, then a platform; clicking an available platform navigates to `/review/{platform.id}` with `state: {projectId}` (React Router's `useNavigate`). Platform cards are disabled (no navigation) until a project is chosen or if the platform isn't available yet.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/StartReviewDialog.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import StartReviewDialog from "./StartReviewDialog";
import { getOllamaModels, createProject } from "../services/api";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getOllamaModels: jest.fn(),
  createProject: jest.fn(),
}));

const projects = [{ id: "p1", name: "Payments Service" }];

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
});

function renderDialog(overrides = {}) {
  return render(
    <MemoryRouter>
      <StartReviewDialog projects={projects} onProjectCreated={jest.fn()} onClose={jest.fn()} {...overrides} />
    </MemoryRouter>
  );
}

test("platform cards are disabled until a project is chosen", async () => {
  renderDialog();
  await screen.findByText("Android");

  await userEvent.setup().click(screen.getByRole("button", { name: "Android" }));

  expect(mockNavigate).not.toHaveBeenCalled();
});

test("selecting a project then clicking an available platform navigates with the project id in state", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(mockNavigate).toHaveBeenCalledWith("/review/android", { state: { projectId: "p1" } });
});

test("does not navigate when clicking an unavailable platform, even with a project chosen", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(screen.getByRole("button", { name: "Web (React)" }));

  expect(mockNavigate).not.toHaveBeenCalled();
});

test("defaults to Ollama highlighted when models are available", async () => {
  renderDialog();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
});

test("creating a project via the dialog selects it and calls onProjectCreated", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p2", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  renderDialog({ onProjectCreated });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  await user.click(screen.getByRole("button", { name: "Android" }));
  expect(mockNavigate).toHaveBeenCalledWith("/review/android", { state: { projectId: "p2" } });
});

test("clicking Cancel calls onClose", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  renderDialog({ onClose });

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/StartReviewDialog.test.jsx --watchAll=false`
Expected: FAIL -- `Cannot find module './StartReviewDialog'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/StartReviewDialog.jsx`:

```jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, getOllamaModels } from "../services/api";
import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "../services/llmProviderStorage";

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

export default function StartReviewDialog({ projects, onProjectCreated, onClose }) {
  const [projectId, setProjectId] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [llmProvider, setLlmProviderState] = useState(() => getLlmProvider());
  const [ollamaModel, setOllamaModelState] = useState(() => getOllamaModel());
  const [ollamaModels, setOllamaModels] = useState(null); // null = still loading
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    getOllamaModels()
      .then((models) => { if (!cancelled) setOllamaModels(models); })
      .catch(() => { if (!cancelled) setOllamaModels([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!ollamaModels || ollamaModels.length === 0) return;
    const initial = ollamaModels.includes(ollamaModel) ? ollamaModel : ollamaModels[0];
    if (initial !== ollamaModel) {
      setOllamaModel(initial);
      setOllamaModelState(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ollamaModels]);

  const ollamaEnabled = ollamaModels === null || ollamaModels.length > 0;
  const effectiveProvider = !ollamaEnabled && llmProvider === "ollama" ? "azure" : llmProvider;

  function handleSelectProvider(providerId) {
    setLlmProvider(providerId);
    setLlmProviderState(providerId);
  }

  function handleSelectModel(model) {
    setOllamaModel(model);
    setOllamaModelState(model);
  }

  async function handleCreateProject(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    setProjectId(project.id);
  }

  function handleSelectPlatform(platform) {
    if (!projectId || !platform.available) return;
    navigate(`/review/${platform.id}`, { state: { projectId } });
  }

  const projectOptions = projects.map((p) => ({ value: p.id, label: p.name }));

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="dialog-title">Start a review</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-4)" }}>
          <div className="field">
            <label htmlFor="startReviewProject">Project</label>
            <SearchableSelect
              ariaLabel="Project" options={projectOptions} value={projectId} onChange={setProjectId}
              placeholder="Choose a project…" onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
            />
          </div>

          <div className="field">
            <label>LLM provider</label>
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              {LLM_PROVIDERS.map((provider) => {
                const disabled = provider.id === "ollama" && !ollamaEnabled;
                return (
                  <button
                    key={provider.id} type="button"
                    className={`btn ${effectiveProvider === provider.id ? "btn-primary" : ""}`}
                    disabled={disabled} onClick={() => handleSelectProvider(provider.id)}
                  >
                    {provider.label}
                  </button>
                );
              })}
            </div>
            {effectiveProvider === "ollama" && ollamaModels && ollamaModels.length > 0 && (
              <select
                aria-label="Ollama model" value={ollamaModel || ollamaModels[0]}
                onChange={(event) => handleSelectModel(event.target.value)} className="input" style={{ marginTop: "var(--space-3)" }}
              >
                {ollamaModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            )}
          </div>

          <div className="field">
            <label>Platform</label>
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
                    cursor: projectId && platform.available ? "pointer" : "not-allowed",
                    opacity: platform.available ? 1 : 0.5,
                  }}
                  onClick={() => handleSelectPlatform(platform)}
                >
                  <div className="card-title" style={{ fontSize: 16 }}>{platform.label}</div>
                </div>
              ))}
            </div>
          </div>
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/StartReviewDialog.test.jsx --watchAll=false`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StartReviewDialog.jsx frontend/src/components/StartReviewDialog.test.jsx
git commit -m "feat: add StartReviewDialog (project + LLM provider + platform picker)"
```

---

### Task 11: Rewrite `ProjectDashboardPage`, delete `ProjectSidebar`/`ProjectReviewHistory`

**Files:**
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx` (full rewrite)
- Modify: `frontend/src/pages/ProjectDashboardPage.test.jsx` (full rewrite)
- Delete: `frontend/src/components/ProjectSidebar.jsx`, `frontend/src/components/ProjectSidebar.test.jsx`
- Delete: `frontend/src/components/ProjectReviewHistory.jsx`, `frontend/src/components/ProjectReviewHistory.test.jsx`

**Interfaces:**
- Consumes: `DashboardFilters` (Task 9), `DashboardOverview` (Task 7), `DashboardResultsTable` (Task 8), `StartReviewDialog` (Task 10), `ChatWidget` (existing, unchanged), `getProjects`/`getReviews`/`getReviewYears` (Task 3), `GearIcon` (existing)

- [ ] **Step 1: Delete the old files**

```bash
git rm frontend/src/components/ProjectSidebar.jsx frontend/src/components/ProjectSidebar.test.jsx
git rm frontend/src/components/ProjectReviewHistory.jsx frontend/src/components/ProjectReviewHistory.test.jsx
```

- [ ] **Step 2: Rewrite the page**

Replace the full contents of `frontend/src/pages/ProjectDashboardPage.jsx`:

```jsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardFilters from "../components/DashboardFilters";
import DashboardOverview from "../components/DashboardOverview";
import DashboardResultsTable from "../components/DashboardResultsTable";
import StartReviewDialog from "../components/StartReviewDialog";
import ChatWidget from "../components/ChatWidget";
import { GearIcon } from "../icons";
import { getProjects, getReviews, getReviewYears } from "../services/api";

function currentYear() {
  return new Date().getFullYear();
}

export default function ProjectDashboardPage() {
  const [projects, setProjects] = useState([]);
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(currentYear());
  const [platform, setPlatform] = useState(null);
  const [projectId, setProjectId] = useState(null);
  const [reviews, setReviews] = useState(null); // null = still loading
  const [startReviewOpen, setStartReviewOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProjects().then((result) => { if (!cancelled) setProjects(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getReviewYears().then((result) => { if (!cancelled) setYears(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    getReviews({ year, platform, projectId })
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setReviews([]); });
    return () => { cancelled = true; };
  }, [year, platform, projectId]);

  function handleProjectCreated(project) {
    setProjects((current) => [project, ...current]);
  }

  function handleProjectRenamed(project) {
    setProjects((current) => current.map((p) => (p.id === project.id ? project : p)));
  }

  function handleReset() {
    setYear(currentYear());
    setPlatform(null);
    setProjectId(null);
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav">
        <span className="logo-mark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">Code Review Automation</span>
        <Link to="/settings" className="btn btn-ghost" aria-label="Settings" style={{ marginLeft: "auto" }}><GearIcon /></Link>
      </nav>

      <main style={{ maxWidth: 1600, margin: "0 auto", padding: "40px 16px 96px", display: "grid", gap: "var(--space-4)" }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Filter review history by year, platform, and project.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
        </header>

        <DashboardFilters
          year={year} years={years} onYearChange={setYear}
          platform={platform} onPlatformChange={setPlatform}
          projectId={projectId} projects={projects} onProjectChange={setProjectId}
          onProjectCreated={handleProjectCreated} onProjectRenamed={handleProjectRenamed}
          onReset={handleReset}
        />

        {reviews !== null && (
          reviews.length === 0 ? (
            <div className="card" style={{ padding: 20 }}>
              <p className="card-body">No reviews match these filters.</p>
            </div>
          ) : (
            <>
              <DashboardOverview reviews={reviews} />
              <DashboardResultsTable reviews={reviews} />
            </>
          )
        )}
      </main>

      {startReviewOpen && (
        <StartReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onClose={() => setStartReviewOpen(false)}
        />
      )}

      <ChatWidget />
    </div>
  );
}
```

- [ ] **Step 3: Rewrite the page's test file**

Replace the full contents of `frontend/src/pages/ProjectDashboardPage.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectDashboardPage from "./ProjectDashboardPage";
import { getProjects, getReviews, getReviewYears, updateProject } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getProjects: jest.fn(),
  getReviews: jest.fn(),
  getReviewYears: jest.fn(),
  updateProject: jest.fn(),
}));

const projects = [
  { id: "p1", name: "Payments Service" },
  { id: "p2", name: "Notifications" },
];

const currentYear = new Date().getFullYear();

beforeEach(() => {
  jest.resetAllMocks();
  getProjects.mockResolvedValue(projects);
  getReviewYears.mockResolvedValue([currentYear - 1, currentYear]);
  getReviews.mockResolvedValue([]);
});

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ProjectDashboardPage />
    </MemoryRouter>
  );
}

test("fetches reviews for the current year with no platform/project filter by default", async () => {
  renderDashboard();

  await waitFor(() => expect(getReviews).toHaveBeenCalledWith({ year: currentYear, platform: null, projectId: null }));
});

test("shows the filter bar with the current year selected by default", async () => {
  renderDashboard();

  expect(await screen.findByRole("button", { name: "Year" })).toHaveTextContent(String(currentYear));
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
  expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("All projects");
});

test("changing a filter re-fetches reviews with the new params", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: "Android", projectId: null }));
});

test("Reset filters restores the defaults and re-fetches", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));
  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: "Android", projectId: null }));

  await user.click(screen.getByRole("button", { name: /reset filters/i }));

  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: null, projectId: null }));
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
});

test("renders the overview and results table once reviews load", async () => {
  getReviews.mockResolvedValue([
    { id: "r1", project_name: "Moove", platform: ".NET", status: "pending_approval", created_at: "2026-08-01T00:00:00Z", total_score_pct: 80, category_scores: [] },
  ]);
  renderDashboard();

  expect(await screen.findByText("Final Score")).toBeInTheDocument();
  expect(screen.getByText("Moove")).toBeInTheDocument();
});

test("clicking Start review opens the dialog", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(screen.getByText("Start a review")).toBeInTheDocument();
});

test("renders a Settings link pointing at /settings", async () => {
  renderDashboard();

  expect(await screen.findByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
});

test("renders the review-insights chat widget", async () => {
  renderDashboard();

  expect(await screen.findByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
});

test("shows one combined empty-state message, not the overview/table, when no reviews match", async () => {
  getReviews.mockResolvedValue([]);
  renderDashboard();

  expect(await screen.findByText(/no reviews match these filters/i)).toBeInTheDocument();
  expect(screen.queryByText("Final Score")).not.toBeInTheDocument();
});

test("renaming a project updates it in the Project dropdown", async () => {
  const user = userEvent.setup();
  const updated = { id: "p1", name: "Payments Team" };
  updateProject.mockResolvedValue(updated);
  renderDashboard();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: null, projectId: "p1" }));

  await user.click(screen.getByRole("button", { name: /rename payments service/i }));
  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Payments Team");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("Payments Team"));
});
```

- [ ] **Step 4: Run this page's tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/ProjectDashboardPage.test.jsx --watchAll=false`
Expected: PASS (10 tests)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all tests pass (confirms deleting `ProjectSidebar`/`ProjectReviewHistory` didn't leave any other file importing them)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ProjectDashboardPage.jsx frontend/src/pages/ProjectDashboardPage.test.jsx
git commit -m "feat: rewrite dashboard around filters + overview + results table"
```

---

### Task 12: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && venv/bin/python -m pytest tests/ -q`
Expected: all tests pass, zero failures

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all tests pass, zero failures

- [ ] **Step 3: Rebuild and start the Docker stack**

Run: `docker compose up -d --build backend frontend`
Expected: both containers start cleanly; `docker compose logs backend --tail 20` shows `Application startup complete` with no errors

- [ ] **Step 4: Smoke-test the new endpoints against real data**

```bash
curl -s "http://localhost:8000/api/reviews/years" | python3 -m json.tool
curl -s "http://localhost:8000/api/reviews?year=<a year from the previous response>" | python3 -m json.tool | head -40
```

Expected: `years` lists real years with data; the reviews list includes `category_scores` per review, and `project_id`/`project_name` correctly identify which project each review belongs to.

- [ ] **Step 5: Smoke-test filtering**

```bash
curl -s "http://localhost:8000/api/reviews?year=<year>&platform=.NET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['reviews']), 'reviews'); print(set(r['platform'] for r in d['reviews']))"
```

Expected: only `.NET` reviews returned for that year.

- [ ] **Step 6: Manual UI check**

Open `http://localhost:3000/` in a browser. Confirm: the filter bar shows the current year / "All platforms" / "All projects" by default; changing any filter updates the overview rings and results table; the Project dropdown is searchable and its "+ Add new project" opens a working create dialog; "Start review" opens a dialog that requires picking a project before a platform becomes clickable, and successfully navigates into the existing review flow; the chat widget and Settings link still work as before.

- [ ] **Step 7: Commit any fixes found during manual verification**

If Steps 1-6 required any fixes, commit them:

```bash
git add -A
git commit -m "fix: address issues found during dashboard redesign final verification"
```
