# Quarterly Dashboard & Cycle Initiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add project platforms, a quarterly status dashboard (four tinted quarter cards per project), and coordinator-initiated quarterly review cycles with a reviewer assigned to each platform.

**Architecture:**
- **Backend:** one pure function (`app/quarterly.py`) decides each quarter's status. `GET /api/quarterly` builds four quarter entries per project from platforms, non-errored reviews and cycles. `POST /api/projects/{id}/cycles` validates a quarter and creates a cycle with an assignment per platform.
- **Frontend:** renders those entries as `QuarterCard`s on a `QuarterlyDashboardPage`, which is the coordinator's `/` and the admin/Management "Quarterly" link.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, pytest (SQLite in-memory); React 18 CRA, react-router v6, Jest + RTL.

**Spec:** `docs/superpowers/specs/2026-10-07-quarterly-dashboard-design.md`

## Global Constraints

- **Tracked platforms:** exactly `("Android", "iOS", ".NET")`, canonical label form. Comparisons against `platform_reviews.platform` are case-insensitive.
- **Dates and coverage:** all quarter dates are UTC. Q1 = Jan 1–Mar 31, Q2 = Apr 1–Jun 30, Q3 = Jul 1–Sep 30, Q4 = Oct 1–Dec 31. "Covered" means a review with `status <> 'error'` and `created_at` within the quarter.
- **Status order:** `not_applicable` → `done` → `overdue` → `in_progress` → `not_started`.
- **Capabilities:**
  - `cycles.view` and `cycles.initiate` go to admin, management and coordinator.
  - `projects.rename` is renamed to `projects.edit` everywhere.
  - Coordinator `home_path` becomes `/`.
- **Status codes:**
  - 409 detail: `This quarter's review has already been initiated.`
  - 400 for a project with no platforms, a platform-set mismatch, an invalid reviewer, or a quarter that can't be started.
- **UI copy:**
  - Statuses: `Done`, `In progress`, `Overdue`, `Not started`, `N/A`.
  - Prompt for a project with no platforms: `Set platforms to track quarterly reviews`.
  - Load error: `Couldn't load quarterly status.`
- **Commands:**
  - Backend tests: `cd backend && venv/bin/python -m pytest -q`.
  - Frontend tests: `cd frontend && CI=true npx react-scripts test --watchAll=false`.
- **Commits:** end every commit with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A quarter that ends today** (today = Sep 30, nothing covered) must be `in_progress`, not `overdue`. Overdue starts the next day. *Task 2 test `test_last_day_of_quarter_is_not_overdue`.*
2. **A project created after a quarter ended** shows N/A for that quarter, not Overdue. A project created mid-quarter is still tracked for that quarter. *Task 2 tests `test_quarter_before_project_creation_is_not_applicable` and `test_project_created_mid_quarter_is_tracked`.*
3. **Errored reviews and reviews with differently-cased platforms** ("android"): errored reviews never count as coverage, and the casing still matches. *Task 4 test `test_coverage_ignores_errors_and_matches_platform_case`.*
4. **Initiating a future quarter**, or one that is already done or started, is rejected. Initiating twice gives 409, never a duplicate cycle. *Task 4 tests `test_initiate_rejects_future_and_done_quarters` and `test_initiate_twice_conflicts`.*
5. **Deleting an empty project** that has platforms or a cycle succeeds, and doesn't fail on foreign keys. *Task 3 test `test_delete_project_removes_platforms_and_cycles`.*

---

### Task 1: Capabilities (`projects.edit`, `cycles.*`, coordinator home)

**Files:**
- Modify: `backend/app/auth/permissions.py`, `backend/app/api/projects.py`, `backend/tests/test_permissions.py`

**Interfaces:**
- Produces: the capability keys `projects.edit`, `cycles.view` and `cycles.initiate`, and `HOME_PATHS["coordinator"] == "/"`.

- [ ] **Step 1: Update the expected values in `test_permissions.py` (RED).**
  - In `EXPECTED`, replace `"projects.rename": {A, M, C},` with `"projects.edit": {A, M, C},`.
  - Add `"cycles.view": {A, M, C},` and `"cycles.initiate": {A, M, C},`.
  - In `test_home_paths`, change `C: "/projects"` to `C: "/"`.
- [ ] **Step 2: Run the tests and verify they fail.**
  Run: `cd backend && venv/bin/python -m pytest tests/test_permissions.py -q`
  Expected: FAIL (the map mismatches, and so does the home path)
- [ ] **Step 3: Implement.** In `permissions.py`:
  - Replace `"projects.rename": _PROJECT_STAFF,` with `"projects.edit": _PROJECT_STAFF,`.
  - Add `"cycles.view": _PROJECT_STAFF,` and `"cycles.initiate": _PROJECT_STAFF,`.
  - Set `COORDINATOR: "/"` in `HOME_PATHS`.
  - In `projects.py`, change `require_permission("projects.rename")` to `require_permission("projects.edit")`.
- [ ] **Step 4: Run the full backend suite.**
  Run: `cd backend && venv/bin/python -m pytest -q`
  Expected: PASS (the permission tests in other files reference roles, not this key)
- [ ] **Step 5: Commit** with the message `feat: add cycles capabilities, rename projects.rename to projects.edit`.

---

### Task 2: Quarter rules (`app/quarterly.py`)

**Files:**
- Create: `backend/app/quarterly.py`, `backend/tests/test_quarterly_rules.py`

**Interfaces:**
- Produces:
  - `TRACKED_PLATFORMS: tuple[str, ...]`
  - `canonical_platform(value: str | None) -> str | None`
  - `sort_platforms(platforms) -> list[str]`
  - `quarter_bounds(year, quarter) -> tuple[date, date]`
  - `quarter_status(project_created: date, platforms: list[str], covered: set[str], cycle_exists: bool, year: int, quarter: int, today: date) -> str`
  - `can_initiate(status: str, cycle_exists: bool, year: int, quarter: int, today: date) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_quarterly_rules.py
from datetime import date

import pytest

from app.quarterly import (
    TRACKED_PLATFORMS, can_initiate, canonical_platform, quarter_bounds, quarter_status, sort_platforms,
)

TODAY = date(2026, 10, 7)  # Q4 2026
CREATED = date(2025, 1, 1)
BOTH = ["Android", "iOS"]


def test_tracked_platforms():
    assert TRACKED_PLATFORMS == ("Android", "iOS", ".NET")


@pytest.mark.parametrize("raw,expected", [("android", "Android"), ("IOS", "iOS"), (".net", ".NET"), ("Web (React)", None), (None, None)])
def test_canonical_platform(raw, expected):
    assert canonical_platform(raw) == expected


def test_sort_platforms_uses_tracked_order():
    assert sort_platforms([".NET", "Android"]) == ["Android", ".NET"]


@pytest.mark.parametrize("quarter,start,end", [
    (1, date(2026, 1, 1), date(2026, 3, 31)),
    (2, date(2026, 4, 1), date(2026, 6, 30)),
    (3, date(2026, 7, 1), date(2026, 9, 30)),
    (4, date(2026, 10, 1), date(2026, 12, 31)),
])
def test_quarter_bounds(quarter, start, end):
    assert quarter_bounds(2026, quarter) == (start, end)


def test_done_when_every_platform_covered():
    assert quarter_status(CREATED, BOTH, {"Android", "iOS"}, False, 2026, 2, TODAY) == "done"


def test_done_even_for_current_quarter():
    assert quarter_status(CREATED, BOTH, {"Android", "iOS"}, False, 2026, 4, TODAY) == "done"


def test_overdue_when_past_and_incomplete():
    assert quarter_status(CREATED, BOTH, {"Android"}, True, 2026, 3, TODAY) == "overdue"
    assert quarter_status(CREATED, BOTH, set(), False, 2026, 1, TODAY) == "overdue"


def test_in_progress_with_cycle_or_partial_coverage():
    assert quarter_status(CREATED, BOTH, set(), True, 2026, 4, TODAY) == "in_progress"
    assert quarter_status(CREATED, BOTH, {"iOS"}, False, 2026, 4, TODAY) == "in_progress"


def test_not_started_current_quarter_with_nothing():
    assert quarter_status(CREATED, BOTH, set(), False, 2026, 4, TODAY) == "not_started"


def test_future_quarter_is_not_started():
    assert quarter_status(CREATED, BOTH, set(), False, 2027, 1, TODAY) == "not_started"


def test_last_day_of_quarter_is_not_overdue():
    assert quarter_status(CREATED, BOTH, set(), True, 2026, 3, date(2026, 9, 30)) == "in_progress"
    assert quarter_status(CREATED, BOTH, set(), True, 2026, 3, date(2026, 10, 1)) == "overdue"


def test_quarter_before_project_creation_is_not_applicable():
    assert quarter_status(date(2026, 8, 15), BOTH, set(), False, 2026, 2, TODAY) == "not_applicable"


def test_project_created_mid_quarter_is_tracked():
    assert quarter_status(date(2026, 8, 15), BOTH, set(), False, 2026, 3, TODAY) == "overdue"


def test_can_initiate():
    assert can_initiate("not_started", False, 2026, 4, TODAY) is True
    assert can_initiate("overdue", False, 2026, 2, TODAY) is True
    assert can_initiate("in_progress", False, 2026, 4, TODAY) is True
    assert can_initiate("in_progress", True, 2026, 4, TODAY) is False
    assert can_initiate("done", False, 2026, 2, TODAY) is False
    assert can_initiate("not_applicable", False, 2026, 1, TODAY) is False
    assert can_initiate("not_started", False, 2027, 1, TODAY) is False
```

- [ ] **Step 2: Run and verify it fails**
  Run: `cd backend && venv/bin/python -m pytest tests/test_quarterly_rules.py -q`
  Expected: FAIL, `ModuleNotFoundError: No module named 'app.quarterly'`

- [ ] **Step 3: Implement**

```python
# backend/app/quarterly.py
"""Quarterly review rules: which quarter a date falls in, and a quarter's status.

A project's quarter is done once every platform it has received at least one
non-errored review dated inside that quarter (UTC).
"""
from datetime import date

TRACKED_PLATFORMS = ("Android", "iOS", ".NET")

_QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
_MONTH_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}
_INITIABLE = {"in_progress", "not_started", "overdue"}


def canonical_platform(value: str | None) -> str | None:
    if not value:
        return None
    for platform in TRACKED_PLATFORMS:
        if platform.lower() == value.strip().lower():
            return platform
    return None


def sort_platforms(platforms) -> list[str]:
    return sorted(set(platforms), key=TRACKED_PLATFORMS.index)


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    first_month, last_month = _QUARTER_MONTHS[quarter]
    return date(year, first_month, 1), date(year, last_month, _MONTH_END_DAY[last_month])


def quarter_status(
    project_created: date, platforms: list[str], covered: set[str], cycle_exists: bool,
    year: int, quarter: int, today: date,
) -> str:
    start, end = quarter_bounds(year, quarter)
    if end < project_created:
        return "not_applicable"
    if platforms and set(platforms) <= covered:
        return "done"
    if today > end:
        return "overdue"
    if today >= start and (cycle_exists or covered):
        return "in_progress"
    return "not_started"


def can_initiate(status: str, cycle_exists: bool, year: int, quarter: int, today: date) -> bool:
    start, _ = quarter_bounds(year, quarter)
    return not cycle_exists and today >= start and status in _INITIABLE
```

- [ ] **Step 4: Run and verify it passes**
  Run: `cd backend && venv/bin/python -m pytest tests/test_quarterly_rules.py -q`
  Expected: PASS
- [ ] **Step 5: Commit** with the message `feat: add quarterly status rules`.

---

### Task 3: Data model, migration with backfill, crud

**Files:**
- Modify: `backend/app/db/models.py`, `backend/app/db/crud.py`
- Create: `backend/app/db/backfills.py`, `backend/alembic/versions/c3d4e5f6a7b8_project_platforms_and_review_cycles.py`, `backend/tests/test_db_quarterly.py`

**Interfaces:**
- Consumes: `canonical_platform`, `sort_platforms` (Task 2).
- Produces:
  - Models `ProjectPlatform`, `ReviewCycle`, `ReviewCycleAssignment`.
  - `backfill_project_platforms(connection)`, which takes a sync connection.
  - crud:
    - `get_platforms_for_projects(session, project_ids) -> dict[str, list[str]]`
    - `set_platforms_for_project(session, project_id, platforms)`
    - `list_live_reviews_for_projects_in_year(session, project_ids, year) -> list[PlatformReview]` (newest first, excluding `error`)
    - `list_cycles_for_projects_in_year(session, project_ids, year) -> list[ReviewCycle]`
    - `get_cycle_assignments(session, cycle_ids) -> dict[str, list[ReviewCycleAssignment]]`
    - `get_cycle(session, project_id, year, quarter) -> ReviewCycle | None`
    - `create_cycle(session, cycle_id, project_id, year, quarter, initiated_by, assignments: list[tuple[str, str]]) -> ReviewCycle`
    - `get_users_by_ids(session, user_ids) -> dict[str, User]`
    - `delete_project` also removes platforms, cycles and assignments.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db_quarterly.py
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.backfills import backfill_project_platforms
from app.db.models import Base


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    sessionmaker.engine = engine
    yield sessionmaker
    await engine.dispose()


async def _review(session, review_id, project_id, platform, status="pending_approval", when=datetime(2026, 5, 1, tzinfo=timezone.utc)):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform=platform, status=status,
        project_name="P", created_at=when, completed_at=None, total_score_pct=1, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None, result_data={},
    )


async def test_platforms_roundtrip(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.create_project(s, "p2", "Two")
        await crud.set_platforms_for_project(s, "p1", [".NET", "Android", "Android"])
        assert await crud.get_platforms_for_projects(s, ["p1", "p2"]) == {"p1": ["Android", ".NET"], "p2": []}
        await crud.set_platforms_for_project(s, "p1", ["iOS"])
        assert (await crud.get_platforms_for_projects(s, ["p1"]))["p1"] == ["iOS"]


async def test_backfill_from_non_errored_reviews(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await _review(s, "r1", "p1", "android")
        await _review(s, "r2", "p1", "Android")
        await _review(s, "r3", "p1", "iOS", status="error")
        await _review(s, "r4", "p1", "Web (React)")
        await _review(s, "r5", None, ".NET")
    async with maker.engine.begin() as conn:
        await conn.run_sync(backfill_project_platforms)
    async with maker() as s:
        assert await crud.get_platforms_for_projects(s, ["p1"]) == {"p1": ["Android"]}


async def test_live_reviews_in_year_excludes_errors_and_other_years(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await _review(s, "r1", "p1", "Android")
        await _review(s, "r2", "p1", "Android", status="error")
        await _review(s, "r3", "p1", "Android", when=datetime(2025, 5, 1, tzinfo=timezone.utc))
        assert [r.id for r in await crud.list_live_reviews_for_projects_in_year(s, ["p1"], 2026)] == ["r1"]


async def test_create_and_read_cycle(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        cycle = await crud.create_cycle(s, "c1", "p1", 2026, 4, "rev", [("Android", "rev")])
        assert cycle.initiated_at is not None
        assert (await crud.get_cycle(s, "p1", 2026, 4)).id == "c1"
        assert await crud.get_cycle(s, "p1", 2026, 3) is None
        assert [c.id for c in await crud.list_cycles_for_projects_in_year(s, ["p1"], 2026)] == ["c1"]
        assignments = await crud.get_cycle_assignments(s, ["c1"])
        assert [(a.platform, a.reviewer_id) for a in assignments["c1"]] == [("Android", "rev")]
        assert (await crud.get_users_by_ids(s, ["rev", "ghost"]))["rev"].name == "Rae"


async def test_delete_project_removes_platforms_and_cycles(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "One")
        await crud.set_platforms_for_project(s, "p1", ["Android"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None)])
        assert await crud.delete_project(s, "p1") is True
        assert await crud.get_cycle(s, "p1", 2026, 4) is None
        assert await crud.get_platforms_for_projects(s, ["p1"]) == {"p1": []}
        assert await crud.get_cycle_assignments(s, ["c1"]) == {"c1": []}
```

- [ ] **Step 2: Run and verify it fails**
  Run: `cd backend && venv/bin/python -m pytest tests/test_db_quarterly.py -q`
  Expected: FAIL, `ModuleNotFoundError: No module named 'app.db.backfills'`

- [ ] **Step 3: Add the models.** Add `Integer` to the sqlalchemy import in `models.py`, then append:

```python
class ProjectPlatform(Base):
    """Which tracked platforms (app.quarterly.TRACKED_PLATFORMS) a project has."""

    __tablename__ = "project_platforms"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    platform: Mapped[str] = mapped_column(String, primary_key=True)


class ReviewCycle(Base):
    """A project's review for one calendar quarter, started by a coordinator."""

    __tablename__ = "review_cycles"
    __table_args__ = (UniqueConstraint("project_id", "year", "quarter"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    initiated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewCycleAssignment(Base):
    __tablename__ = "review_cycle_assignments"

    cycle_id: Mapped[str] = mapped_column(ForeignKey("review_cycles.id", ondelete="CASCADE"), primary_key=True)
    platform: Mapped[str] = mapped_column(String, primary_key=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 4: Add the backfill helper**

```python
# backend/app/db/backfills.py
"""Data backfills shared by Alembic migrations and their tests (sync connections)."""
from sqlalchemy import text

from app.quarterly import canonical_platform


def backfill_project_platforms(connection) -> None:
    """Give each project the tracked platforms it has already been reviewed on."""
    rows = connection.execute(text(
        "SELECT DISTINCT project_id, platform FROM platform_reviews "
        "WHERE project_id IS NOT NULL AND status <> 'error'"
    )).all()
    pairs = {(project_id, canonical_platform(platform)) for project_id, platform in rows}
    for project_id, platform in sorted(p for p in pairs if p[1] is not None):
        connection.execute(
            text("INSERT INTO project_platforms (project_id, platform) VALUES (:project_id, :platform)"),
            {"project_id": project_id, "platform": platform},
        )
```

- [ ] **Step 5: Write the migration**

```python
# backend/alembic/versions/c3d4e5f6a7b8_project_platforms_and_review_cycles.py
"""project platforms and quarterly review cycles

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.backfills import backfill_project_platforms


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_platforms",
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("platform", sa.String(), primary_key=True),
    )
    op.create_table(
        "review_cycles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("initiated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "year", "quarter"),
    )
    op.create_table(
        "review_cycle_assignments",
        sa.Column("cycle_id", sa.String(), sa.ForeignKey("review_cycles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("platform", sa.String(), primary_key=True),
        sa.Column("reviewer_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    backfill_project_platforms(op.get_bind())


def downgrade() -> None:
    op.drop_table("review_cycle_assignments")
    op.drop_table("review_cycles")
    op.drop_table("project_platforms")
```

- [ ] **Step 6: Implement the crud functions.**
  - Extend the models import with `ProjectPlatform, ReviewCycle, ReviewCycleAssignment`.
  - Add `from app.quarterly import sort_platforms`.
  - Append:

```python
# --- quarterly ---

async def get_platforms_for_projects(session: AsyncSession, project_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {project_id: [] for project_id in project_ids}
    if not project_ids:
        return mapping
    result = await session.execute(
        select(ProjectPlatform.project_id, ProjectPlatform.platform).where(ProjectPlatform.project_id.in_(project_ids))
    )
    for project_id, platform in result.all():
        mapping[project_id].append(platform)
    return {project_id: sort_platforms(platforms) for project_id, platforms in mapping.items()}


async def set_platforms_for_project(session: AsyncSession, project_id: str, platforms: list[str]) -> None:
    await session.execute(delete(ProjectPlatform).where(ProjectPlatform.project_id == project_id))
    for platform in sort_platforms(platforms):
        session.add(ProjectPlatform(project_id=project_id, platform=platform))
    await session.commit()


async def list_live_reviews_for_projects_in_year(session: AsyncSession, project_ids: list[str], year: int) -> list[PlatformReview]:
    if not project_ids:
        return []
    result = await session.execute(
        select(PlatformReview)
        .where(
            PlatformReview.project_id.in_(project_ids),
            PlatformReview.status != "error",
            extract("year", PlatformReview.created_at) == year,
        )
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.scalars().all())


async def list_cycles_for_projects_in_year(session: AsyncSession, project_ids: list[str], year: int) -> list[ReviewCycle]:
    if not project_ids:
        return []
    result = await session.execute(
        select(ReviewCycle).where(ReviewCycle.project_id.in_(project_ids), ReviewCycle.year == year)
    )
    return list(result.scalars().all())


async def get_cycle_assignments(session: AsyncSession, cycle_ids: list[str]) -> dict[str, list[ReviewCycleAssignment]]:
    mapping: dict[str, list[ReviewCycleAssignment]] = {cycle_id: [] for cycle_id in cycle_ids}
    if not cycle_ids:
        return mapping
    result = await session.execute(select(ReviewCycleAssignment).where(ReviewCycleAssignment.cycle_id.in_(cycle_ids)))
    for assignment in result.scalars().all():
        mapping[assignment.cycle_id].append(assignment)
    return mapping


async def get_cycle(session: AsyncSession, project_id: str, year: int, quarter: int) -> Optional[ReviewCycle]:
    result = await session.execute(
        select(ReviewCycle).where(
            ReviewCycle.project_id == project_id, ReviewCycle.year == year, ReviewCycle.quarter == quarter,
        )
    )
    return result.scalar_one_or_none()


async def create_cycle(
    session: AsyncSession, cycle_id: str, project_id: str, year: int, quarter: int,
    initiated_by: Optional[str], assignments: list[tuple[str, Optional[str]]],
) -> ReviewCycle:
    cycle = ReviewCycle(
        id=cycle_id, project_id=project_id, year=year, quarter=quarter,
        initiated_by=initiated_by, initiated_at=datetime.now(timezone.utc),
    )
    session.add(cycle)
    await session.flush()
    for platform, reviewer_id in assignments:
        session.add(ReviewCycleAssignment(cycle_id=cycle_id, platform=platform, reviewer_id=reviewer_id))
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def get_users_by_ids(session: AsyncSession, user_ids: list[str]) -> dict[str, User]:
    ids = [user_id for user_id in set(user_ids) if user_id]
    if not ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return {user.id: user for user in result.scalars().all()}
```

  Replace `delete_project` with:

```python
async def delete_project(session: AsyncSession, project_id: str) -> bool:
    # Explicit, not just ON DELETE CASCADE: SQLite (tests) doesn't enforce FKs by default.
    cycle_ids = select(ReviewCycle.id).where(ReviewCycle.project_id == project_id)
    await session.execute(delete(ReviewCycleAssignment).where(ReviewCycleAssignment.cycle_id.in_(cycle_ids)))
    await session.execute(delete(ReviewCycle).where(ReviewCycle.project_id == project_id))
    await session.execute(delete(ProjectPlatform).where(ProjectPlatform.project_id == project_id))
    await session.execute(delete(ProjectManager).where(ProjectManager.project_id == project_id))
    result = await session.execute(delete(Project).where(Project.id == project_id))
    await session.commit()
    return result.rowcount > 0
```

- [ ] **Step 7: Run the tests and check the migration head**
  Run: `cd backend && venv/bin/python -m pytest tests/test_db_quarterly.py tests/test_db_crud_access.py -q && venv/bin/alembic heads`
  Expected: PASS, and `c3d4e5f6a7b8 (head)`
- [ ] **Step 8: Commit** with the message `feat: add project platforms and review cycle tables with backfill`.

---

### Task 4: Quarterly and platforms API

**Files:**
- Create: `backend/app/api/quarterly.py`, `backend/tests/test_quarterly_api.py`
- Modify: `backend/app/api/projects.py`, `backend/main.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `GET /api/quarterly?year=` and `POST /api/projects/{id}/cycles` (shapes per the spec).
  - `PUT /api/projects/{id}/platforms`.
  - Project dicts gain `platforms`.
  - `app.api.quarterly._today()`, a function tests can override.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_quarterly_api.py
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
import app.api.quarterly as quarterly_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


async def _review(session, review_id, project_id, platform, when, status="pending_approval"):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform=platform, status=status,
        project_name="P", created_at=when, completed_at=None, total_score_pct=1, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None, result_data={},
    )


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(quarterly_module, "new_session", lambda: maker())
    monkeypatch.setattr(projects_module, "new_session", lambda: maker())
    monkeypatch.setattr(quarterly_module, "_today", lambda: date(2026, 10, 7))
    async with maker() as s:
        for project in (await crud.create_project(s, "p1", "Alpha"), await crud.create_project(s, "p2", "Beta")):
            project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)  # tracked for all of 2026
        await s.commit()
        await crud.set_platforms_for_project(s, "p1", ["Android", "iOS"])
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await _review(s, "a2", "p1", "Android", datetime(2026, 5, 2, tzinfo=timezone.utc))
        await _review(s, "i2", "p1", "ios", datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc))
        await _review(s, "a3", "p1", "Android", datetime(2026, 8, 1, tzinfo=timezone.utc))
        await _review(s, "i3err", "p1", "iOS", datetime(2026, 8, 2, tzinfo=timezone.utc), status="error")
    yield maker
    await engine.dispose()


def _as(role, user_id="u1"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _quarters(body, project_id="p1"):
    project = next(p for p in body["projects"] if p["id"] == project_id)
    return {q["quarter"]: q for q in project["quarters"]}


def test_quarterly_statuses(db):
    _as("coordinator")
    body = client.get("/api/quarterly?year=2026").json()
    assert body["year"] == 2026 and body["today"] == "2026-10-07"
    assert [p["name"] for p in body["projects"]] == ["Alpha", "Beta"]
    quarters = _quarters(body)
    assert {q: e["status"] for q, e in quarters.items()} == {1: "overdue", 2: "done", 3: "overdue", 4: "not_started"}
    assert quarters[2]["start"] == "2026-04-01" and quarters[2]["end"] == "2026-06-30"
    assert quarters[3]["missing"] == ["iOS"]
    assert [c["review_id"] for c in quarters[3]["covered"]] == ["a3"]
    assert quarters[4]["can_initiate"] is True and quarters[2]["can_initiate"] is False


def test_coverage_ignores_errors_and_matches_platform_case(db):
    _as("coordinator")
    quarters = _quarters(client.get("/api/quarterly?year=2026").json())
    assert [c["platform"] for c in quarters[2]["covered"]] == ["Android", "iOS"]
    assert "iOS" in quarters[3]["missing"]


def test_project_without_platforms_has_no_quarters(db):
    _as("coordinator")
    beta = next(p for p in client.get("/api/quarterly?year=2026").json()["projects"] if p["id"] == "p2")
    assert beta["platforms"] == [] and beta["quarters"] == []


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_quarterly_forbidden(db, role):
    _as(role)
    assert client.get("/api/quarterly").status_code == 403


def test_initiate_cycle(db):
    _as("coordinator", "coord")
    response = client.post("/api/projects/p1/cycles", json={
        "year": 2026, "quarter": 4,
        "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}],
    })
    assert response.status_code == 200
    entry = response.json()
    assert entry["status"] == "in_progress" and entry["can_initiate"] is False
    assert entry["cycle"]["assignments"] == [
        {"platform": "Android", "reviewer_id": "rev", "reviewer_name": "Rae"},
        {"platform": "iOS", "reviewer_id": "rev", "reviewer_name": "Rae"},
    ]


def test_initiate_twice_conflicts(db):
    _as("coordinator", "coord")
    payload = {"year": 2026, "quarter": 3, "assignments": [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}]}
    assert client.post("/api/projects/p1/cycles", json=payload).status_code == 200
    response = client.post("/api/projects/p1/cycles", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "This quarter's review has already been initiated."


def test_initiate_rejects_future_and_done_quarters(db):
    _as("coordinator", "coord")
    both = [{"platform": "Android", "reviewer_id": "rev"}, {"platform": "iOS", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2027, "quarter": 1, "assignments": both}).status_code == 400
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 2, "assignments": both}).status_code == 400


def test_initiate_validation(db):
    _as("coordinator", "coord")
    android_only = [{"platform": "Android", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": android_only}).status_code == 400
    bad_reviewer = [{"platform": "Android", "reviewer_id": "pm"}, {"platform": "iOS", "reviewer_id": "rev"}]
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": bad_reviewer}).status_code == 400
    assert client.post("/api/projects/p2/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 400
    assert client.post("/api/projects/nope/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 404


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_initiate_forbidden(db, role):
    _as(role)
    assert client.post("/api/projects/p1/cycles", json={"year": 2026, "quarter": 4, "assignments": []}).status_code == 403


def test_set_platforms(db):
    _as("coordinator")
    response = client.put("/api/projects/p2/platforms", json={"platforms": [".net", "Android"]})
    assert response.status_code == 200
    assert response.json()["platforms"] == ["Android", ".NET"]
    listed = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert listed["p2"]["platforms"] == ["Android", ".NET"]


def test_set_platforms_validation_and_permissions(db):
    _as("coordinator")
    assert client.put("/api/projects/p2/platforms", json={"platforms": ["Web (React)"]}).status_code == 400
    assert client.put("/api/projects/nope/platforms", json={"platforms": []}).status_code == 404
    _as("project_manager")
    assert client.put("/api/projects/p2/platforms", json={"platforms": ["iOS"]}).status_code == 403
```

- [ ] **Step 2: Run and verify it fails**
  Run: `cd backend && venv/bin/python -m pytest tests/test_quarterly_api.py -q`
  Expected: FAIL, `ModuleNotFoundError: No module named 'app.api.quarterly'`

- [ ] **Step 3: Implement `app/api/quarterly.py`**

```python
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.permissions import PERMISSIONS, require_permission
from app.db import crud
from app.db.session import new_session
from app.quarterly import (
    TRACKED_PLATFORMS, can_initiate, canonical_platform, quarter_bounds, quarter_status, sort_platforms,
)

router = APIRouter()


class AssignmentIn(BaseModel):
    platform: str
    reviewer_id: str


class InitiateCycleRequest(BaseModel):
    year: int
    quarter: int
    assignments: list[AssignmentIn]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _display_name(user) -> str | None:
    return (user.name or user.email) if user else None


async def _quarter_entries(session, projects, year: int, today: date) -> dict[str, list[dict]]:
    project_ids = [p.id for p in projects]
    platforms_by_project = await crud.get_platforms_for_projects(session, project_ids)
    reviews = await crud.list_live_reviews_for_projects_in_year(session, project_ids, year)
    cycles = await crud.list_cycles_for_projects_in_year(session, project_ids, year)
    assignments = await crud.get_cycle_assignments(session, [c.id for c in cycles])
    user_ids = [c.initiated_by for c in cycles] + [a.reviewer_id for rows in assignments.values() for a in rows]
    users = await crud.get_users_by_ids(session, user_ids)
    cycle_by_key = {(c.project_id, c.quarter): c for c in cycles}

    entries: dict[str, list[dict]] = {}
    for project in projects:
        platforms = platforms_by_project[project.id]
        if not platforms:
            entries[project.id] = []
            continue
        project_quarters = []
        for quarter in (1, 2, 3, 4):
            start, end = quarter_bounds(year, quarter)
            latest_by_platform = {}
            for review in reviews:  # newest first
                platform = canonical_platform(review.platform)
                if (
                    review.project_id == project.id and platform in platforms
                    and platform not in latest_by_platform and start <= _as_date(review.created_at) <= end
                ):
                    latest_by_platform[platform] = review
            covered = set(latest_by_platform)
            cycle = cycle_by_key.get((project.id, quarter))
            status = quarter_status(_as_date(project.created_at), platforms, covered, cycle is not None, year, quarter, today)
            project_quarters.append({
                "quarter": quarter,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": status,
                "covered": [
                    {"platform": p, "review_id": latest_by_platform[p].id, "reviewed_at": latest_by_platform[p].created_at.isoformat()}
                    for p in sort_platforms(covered)
                ],
                "missing": [p for p in platforms if p not in covered],
                "can_initiate": can_initiate(status, cycle is not None, year, quarter, today),
                "cycle": None if cycle is None else {
                    "id": cycle.id,
                    "initiated_at": cycle.initiated_at.isoformat(),
                    "initiated_by_name": _display_name(users.get(cycle.initiated_by)),
                    "assignments": [
                        {"platform": a.platform, "reviewer_id": a.reviewer_id, "reviewer_name": _display_name(users.get(a.reviewer_id))}
                        for a in sorted(assignments[cycle.id], key=lambda a: TRACKED_PLATFORMS.index(a.platform))
                    ],
                },
            })
        entries[project.id] = project_quarters
    return entries


@router.get("/api/quarterly")
async def get_quarterly(year: int | None = None, user=Depends(require_permission("cycles.view"))):
    today = _today()
    year = year or today.year
    async with new_session() as session:
        projects = sorted(await crud.list_projects(session), key=lambda p: p.name.lower())
        platforms = await crud.get_platforms_for_projects(session, [p.id for p in projects])
        entries = await _quarter_entries(session, projects, year, today)
    return {
        "year": year,
        "today": today.isoformat(),
        "projects": [
            {"id": p.id, "name": p.name, "platforms": platforms[p.id], "quarters": entries[p.id]} for p in projects
        ],
    }


@router.post("/api/projects/{project_id}/cycles")
async def initiate_cycle(project_id: str, body: InitiateCycleRequest, user=Depends(require_permission("cycles.initiate"))):
    if body.quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="quarter must be 1-4")
    today = _today()
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        if not platforms:
            raise HTTPException(status_code=400, detail="Set this project's platforms before initiating a review.")
        requested = [canonical_platform(a.platform) for a in body.assignments]
        if sorted(p or "" for p in requested) != sorted(platforms) or len(set(requested)) != len(requested):
            raise HTTPException(status_code=400, detail="Assign exactly one reviewer to each of the project's platforms.")
        reviewers = await crud.get_users_by_ids(session, [a.reviewer_id for a in body.assignments])
        for assignment in body.assignments:
            reviewer = reviewers.get(assignment.reviewer_id)
            if reviewer is None or not reviewer.is_active or reviewer.role not in PERMISSIONS["reviews.finalize_own"]:
                raise HTTPException(status_code=400, detail="Each reviewer must be an active reviewer, management or admin account.")
        if await crud.get_cycle(session, project_id, body.year, body.quarter) is not None:
            raise HTTPException(status_code=409, detail="This quarter's review has already been initiated.")
        current = (await _quarter_entries(session, [project], body.year, today))[project_id][body.quarter - 1]
        if not current["can_initiate"]:
            raise HTTPException(status_code=400, detail="This quarter can't be initiated.")
        await crud.create_cycle(
            session, str(uuid.uuid4()), project_id, body.year, body.quarter, user.id,
            [(canonical_platform(a.platform), a.reviewer_id) for a in body.assignments],
        )
        return (await _quarter_entries(session, [project], body.year, today))[project_id][body.quarter - 1]
```

- [ ] **Step 4: Register the router and add platforms to projects.**
  - **`main.py`:** add `from app.api.quarterly import router as quarterly_router` and `app.include_router(quarterly_router)`.
  - **`projects.py`:**
    - Import `from app.quarterly import canonical_platform`.
    - Add a `platforms: list[str] | None = None` parameter to `_project_to_dict`. When it's not None, set `data["platforms"] = platforms`.
    - `create_project` returns `platforms=[]`.
    - `list_projects` fetches `crud.get_platforms_for_projects(session, ids)` and passes `platforms.get(p.id, [])`.
    - `update_project` and `set_project_managers` pass `(await crud.get_platforms_for_projects(session, [project_id]))[project_id]`.
    - Add the platforms endpoint:

```python
class SetPlatformsRequest(BaseModel):
    platforms: list[str]


@router.put("/api/projects/{project_id}/platforms")
async def set_project_platforms(project_id: str, body: SetPlatformsRequest, user=Depends(require_permission("projects.edit"))):
    canonical = [canonical_platform(p) for p in body.platforms]
    if any(p is None for p in canonical):
        raise HTTPException(status_code=400, detail="platforms must be Android, iOS or .NET")
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await crud.set_platforms_for_project(session, project_id, canonical)
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        review_count = await crud.count_reviews_for_project(session, project_id)
        return _project_to_dict(project, review_count, platforms=platforms)
```

- [ ] **Step 5: Run the tests**
  Run: `cd backend && venv/bin/python -m pytest -q`
  Expected: PASS. If `test_projects_management_api.py` / `test_projects_api.py` assert exact project dicts, add the `platforms` key there.
- [ ] **Step 6: Commit** with the message `feat: add quarterly status and cycle initiation API, project platforms endpoint`.

---

### Task 5: Frontend permissions, API client, routing and nav

**Files:**
- Modify:
  - `frontend/src/testUtils/authUsers.js`, `frontend/src/context/AuthContext.jsx`
  - `frontend/src/components/DashboardFilters.jsx`, `frontend/src/pages/ProjectsPage.jsx`
  - `frontend/src/services/api.js`
  - `frontend/src/components/RouteGuards.jsx` (+test), `frontend/src/components/AppNav.jsx` (+test), `frontend/src/AppRoutes.jsx`
- Create: `frontend/src/pages/QuarterlyDashboardPage.jsx` (a stub, replaced in Task 6)

**Interfaces:**
- Produces:
  - `getQuarterly(year)` returns the response body.
  - `initiateCycle(projectId, { year, quarter, assignments })` returns a quarter entry.
  - `setProjectPlatforms(projectId, platforms)` returns a project.
  - `DashboardOrHome({ children, quarterly })`.

- [ ] **Step 1: Update the tests (RED)**
  - **`RouteGuards.test.jsx`:**
    - Render `/` as `<RequireAuth><DashboardOrHome quarterly={<div>quarterly dashboard</div>}><div>dashboard</div></DashboardOrHome></RequireAuth>`.
    - Change the coordinator row to `["coordinator", "quarterly dashboard"]`.
  - **`AppNav.test.jsx`:** the expected links become:

    | Role | Links |
    |---|---|
    | admin | `["Dashboard", "Quarterly", "My reviews", "Projects", "Users"]` |
    | management | `["Dashboard", "Quarterly", "My reviews", "Projects"]` |
    | coordinator | `["Dashboard", "Projects"]` |
    | reviewer | `["My reviews"]` |
    | project_manager | `["Dashboard"]` |

  - **The "brand links to the user's home" test** stays as-is: the reviewer goes to `/my-reviews`.
- [ ] **Step 2: Run and verify they fail**
  Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/components/RouteGuards.test.jsx src/components/AppNav.test.jsx`
  Expected: FAIL
- [ ] **Step 3: Implement**
  - **`authUsers.js`:** in `ROLE_PERMISSIONS`, replace `"projects.rename"` with `"projects.edit"`. Add `"cycles.initiate", "cycles.view"` to admin, management and coordinator. Set `HOME_PATHS.coordinator = "/"`.
  - **`AuthContext.jsx`:** make the same change in the default admin permission list.
  - **`DashboardFilters.jsx` and `ProjectsPage.jsx`:** change `"projects.rename"` to `"projects.edit"`.
  - **`api.js`:** append:

```js
export async function getQuarterly(year) {
  const response = await axios.get(`${API_BASE_URL}/quarterly`, { params: { year } });
  return response.data;
}

export async function initiateCycle(projectId, { year, quarter, assignments }) {
  const response = await axios.post(`${API_BASE_URL}/projects/${projectId}/cycles`, { year, quarter, assignments });
  return response.data;
}

export async function setProjectPlatforms(projectId, platforms) {
  const response = await axios.put(`${API_BASE_URL}/projects/${projectId}/platforms`, { platforms });
  return response.data;
}
```

  - **`RouteGuards.jsx`:** replace `DashboardOrHome` with:

```jsx
// "/" is the scores dashboard for roles that have one, the quarterly dashboard
// for roles that only track cycles (coordinator), and otherwise the user's home.
export function DashboardOrHome({ children, quarterly = null }) {
  const { user } = useAuth();
  if (hasAny(user, ["dashboard.view_all", "dashboard.view_assigned"])) return children;
  if (quarterly && hasAny(user, ["cycles.view"])) return quarterly;
  return <Navigate to={user?.home_path && user.home_path !== "/" ? user.home_path : "/login"} replace />;
}
```

  - **`AppNav.jsx`:** replace `LINKS` and its filter with:

```jsx
const DASHBOARDS = ["dashboard.view_all", "dashboard.view_assigned"];

const LINKS = [
  { to: "/", label: "Dashboard", end: true, show: (user) => hasAny(user, [...DASHBOARDS, "cycles.view"]) },
  { to: "/quarterly", label: "Quarterly", show: (user) => hasAny(user, DASHBOARDS) && hasAny(user, ["cycles.view"]) },
  { to: "/my-reviews", label: "My reviews", show: (user) => hasAny(user, ["my_reviews.view"]) },
  { to: "/projects", label: "Projects", show: (user) => hasAny(user, ["projects.view"]) },
  { to: "/users", label: "Users", show: (user) => hasAny(user, ["users.manage"]) },
];
```

    and use `LINKS.filter((link) => link.show(user))`.
  - **`QuarterlyDashboardPage.jsx` stub:** `export default function QuarterlyDashboardPage() { return null; }`
  - **`AppRoutes.jsx`:**
    - Import `QuarterlyDashboardPage`.
    - The `/` route element becomes `<RequireAuth><DashboardOrHome quarterly={<QuarterlyDashboardPage />}><ProjectDashboardPage /></DashboardOrHome></RequireAuth>`.
    - Add `<Route path="/quarterly" element={<RequirePermission anyOf={["cycles.view"]}><QuarterlyDashboardPage /></RequirePermission>} />`.
- [ ] **Step 4: Run the full frontend suite.** Expected: PASS
- [ ] **Step 5: Commit** with the message `feat: route coordinators to a quarterly dashboard and add Quarterly nav for admins`.

---

### Task 6: QuarterCard, InitiateCycleDialog, QuarterlyDashboardPage

**Files:**
- Create:
  - `frontend/src/components/QuarterCard.jsx` (+test)
  - `frontend/src/components/InitiateCycleDialog.jsx` (+test)
  - `frontend/src/pages/QuarterlyDashboardPage.jsx` (replaces the stub, +test)
- Modify: `frontend/src/design-system.css`

**Interfaces:**
- Consumes: `getQuarterly`, `initiateCycle`, `getReviewers`, `useCan`.
- Produces:
  - `<QuarterCard entry platforms canInitiate onInitiate />`
  - `<InitiateCycleDialog project year entry onInitiated onClose />`
  - `STATUS_LABELS` and `QUARTER_MONTHS`, exported from `QuarterCard.jsx`

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/components/QuarterCard.test.jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuarterCard from "./QuarterCard";

const base = {
  quarter: 3, start: "2026-07-01", end: "2026-09-30", status: "overdue",
  covered: [{ platform: "Android", review_id: "a3", reviewed_at: "2026-08-01T00:00:00Z" }],
  missing: ["iOS"], can_initiate: true, cycle: null,
};

test.each([
  ["done", "Done"], ["in_progress", "In progress"], ["overdue", "Overdue"],
  ["not_started", "Not started"], ["not_applicable", "N/A"],
])("%s card shows its badge and tint class", (status, label) => {
  const { container } = render(<QuarterCard entry={{ ...base, status }} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  expect(container.firstChild).toHaveClass(`quarter-card--${status.replace("_", "-")}`);
});

test("lists covered and missing platforms with the quarter label", () => {
  render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText("Q3 · Jul–Sep")).toBeInTheDocument();
  expect(screen.getByText(/Android/).closest("li")).toHaveTextContent("✓");
  expect(screen.getByText(/iOS/).closest("li")).toHaveTextContent("○");
});

test("shows cycle info", () => {
  const entry = { ...base, can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora",
    assignments: [{ platform: "Android", reviewer_id: "r", reviewer_name: "Rae" }],
  } };
  render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate onInitiate={jest.fn()} />);
  expect(screen.getByText(/Initiated .* by Cora/)).toBeInTheDocument();
  expect(screen.getByText(/Rae/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /initiate review/i })).not.toBeInTheDocument();
});

test("Initiate button only when allowed by entry and permission", async () => {
  const user = userEvent.setup();
  const onInitiate = jest.fn();
  const { rerender } = render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate onInitiate={onInitiate} />);
  await user.click(screen.getByRole("button", { name: /initiate review/i }));
  expect(onInitiate).toHaveBeenCalled();
  rerender(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={onInitiate} />);
  expect(screen.queryByRole("button", { name: /initiate review/i })).not.toBeInTheDocument();
});
```

```jsx
// frontend/src/components/InitiateCycleDialog.test.jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InitiateCycleDialog from "./InitiateCycleDialog";
import { getReviewers, initiateCycle } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getReviewers: jest.fn(), initiateCycle: jest.fn() }));

const project = { id: "p1", name: "Alpha", platforms: ["Android", "iOS"] };
const entry = { quarter: 4, status: "not_started" };

beforeEach(() => {
  jest.resetAllMocks();
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }, { id: "r2", email: "sam@example.com", name: null }]);
});

test("requires a reviewer per platform, then posts assignments", async () => {
  const user = userEvent.setup();
  const onInitiated = jest.fn();
  initiateCycle.mockResolvedValue({ quarter: 4, status: "in_progress" });
  render(<InitiateCycleDialog project={project} year={2026} entry={entry} onInitiated={onInitiated} onClose={jest.fn()} />);
  expect(screen.getByText("Initiate Q4 2026 review — Alpha")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "Initiate" });
  await screen.findByRole("option", { name: "Rae" });
  expect(submit).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  expect(submit).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Reviewer for iOS"), "r2");
  await user.click(submit);
  await waitFor(() => expect(initiateCycle).toHaveBeenCalledWith("p1", {
    year: 2026, quarter: 4,
    assignments: [{ platform: "Android", reviewer_id: "r1" }, { platform: "iOS", reviewer_id: "r2" }],
  }));
  expect(onInitiated).toHaveBeenCalledWith({ quarter: 4, status: "in_progress" });
});

test("shows the API error", async () => {
  const user = userEvent.setup();
  initiateCycle.mockRejectedValue({ response: { data: { detail: "This quarter's review has already been initiated." } } });
  render(<InitiateCycleDialog project={{ ...project, platforms: ["Android"] }} year={2026} entry={entry} onInitiated={jest.fn()} onClose={jest.fn()} />);
  await screen.findByRole("option", { name: "Rae" });
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  expect(await screen.findByText("This quarter's review has already been initiated.")).toBeInTheDocument();
});
```

```jsx
// frontend/src/pages/QuarterlyDashboardPage.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import QuarterlyDashboardPage from "./QuarterlyDashboardPage";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getQuarterly, getReviewers, getReviewYears, initiateCycle } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getQuarterly: jest.fn(), getReviewers: jest.fn(), getReviewYears: jest.fn(), initiateCycle: jest.fn(),
}));

const q = (quarter, status, extra = {}) => ({
  quarter, start: "2026-01-01", end: "2026-03-31", status, covered: [], missing: ["Android"],
  can_initiate: false, cycle: null, ...extra,
});

const data = {
  year: 2026, today: "2026-10-07",
  projects: [
    { id: "p1", name: "Alpha", platforms: ["Android"], quarters: [q(1, "done"), q(2, "done"), q(3, "overdue", { can_initiate: true }), q(4, "not_started", { can_initiate: true })] },
    { id: "p2", name: "Beta", platforms: [], quarters: [] },
  ],
};

beforeEach(() => {
  jest.resetAllMocks();
  getQuarterly.mockResolvedValue(data);
  getReviewYears.mockResolvedValue([2025, 2026]);
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }]);
});

function renderAs(role = "coordinator") {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><QuarterlyDashboardPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

test("renders a row per project with four quarter cards", async () => {
  renderAs();
  const row = await screen.findByRole("region", { name: "Alpha" });
  expect(within(row).getAllByText(/^Q[1-4] · /)).toHaveLength(4);
  expect(within(row).getAllByText("Done")).toHaveLength(2);
});

test("prompts to set platforms for projects without any", async () => {
  renderAs();
  const row = await screen.findByRole("region", { name: "Beta" });
  expect(within(row).getByRole("link", { name: "Set platforms to track quarterly reviews" })).toHaveAttribute("href", "/projects");
});

test("changing the year refetches", async () => {
  const user = userEvent.setup();
  renderAs();
  await screen.findByRole("region", { name: "Alpha" });
  await user.selectOptions(screen.getByLabelText("Year"), "2025");
  await waitFor(() => expect(getQuarterly).toHaveBeenLastCalledWith(2025));
});

test("search filters projects", async () => {
  const user = userEvent.setup();
  renderAs();
  await screen.findByRole("region", { name: "Alpha" });
  await user.type(screen.getByRole("searchbox", { name: "Search projects" }), "bet");
  expect(screen.queryByRole("region", { name: "Alpha" })).not.toBeInTheDocument();
});

test("initiating replaces the quarter card", async () => {
  const user = userEvent.setup();
  initiateCycle.mockResolvedValue(q(4, "in_progress", { cycle: { id: "c1", initiated_at: "2026-10-07T00:00:00Z", initiated_by_name: "Cora", assignments: [] } }));
  renderAs();
  const row = await screen.findByRole("region", { name: "Alpha" });
  await user.click(within(row).getAllByRole("button", { name: /initiate review/i })[1]);
  await screen.findByRole("option", { name: "Rae" });
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  expect(await within(row).findByText("In progress")).toBeInTheDocument();
});

test("load error", async () => {
  getQuarterly.mockRejectedValue(new Error("boom"));
  renderAs();
  expect(await screen.findByText("Couldn't load quarterly status.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify they fail**
  Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/components/QuarterCard.test.jsx src/components/InitiateCycleDialog.test.jsx src/pages/QuarterlyDashboardPage.test.jsx`
  Expected: FAIL

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/QuarterCard.jsx
export const STATUS_LABELS = {
  done: "Done", in_progress: "In progress", overdue: "Overdue", not_started: "Not started", not_applicable: "N/A",
};

export const QUARTER_MONTHS = { 1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec" };

function shortDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export default function QuarterCard({ entry, platforms, canInitiate, onInitiate }) {
  const coveredByPlatform = Object.fromEntries(entry.covered.map((c) => [c.platform, c]));
  const reviewerByPlatform = Object.fromEntries((entry.cycle?.assignments || []).map((a) => [a.platform, a.reviewer_name]));
  const statusClass = entry.status.replace("_", "-");

  return (
    <div className={`quarter-card quarter-card--${statusClass}`}>
      <div className="quarter-card-head">
        <span className="quarter-card-title">Q{entry.quarter} · {QUARTER_MONTHS[entry.quarter]}</span>
        <span className={`quarter-badge quarter-badge--${statusClass}`}>{STATUS_LABELS[entry.status]}</span>
      </div>
      {entry.status !== "not_applicable" && (
        <ul className="quarter-card-platforms">
          {platforms.map((platform) => {
            const covered = coveredByPlatform[platform];
            return (
              <li key={platform}>
                <span aria-hidden="true" className={covered ? "quarter-tick" : "quarter-dot"}>{covered ? "✓" : "○"}</span>
                {" "}{platform}
                {covered && <span className="quarter-card-meta"> · {shortDate(covered.reviewed_at)}</span>}
                {!covered && reviewerByPlatform[platform] && <span className="quarter-card-meta"> · {reviewerByPlatform[platform]}</span>}
              </li>
            );
          })}
        </ul>
      )}
      {entry.cycle && (
        <p className="quarter-card-meta" style={{ margin: 0 }}>
          Initiated {shortDate(entry.cycle.initiated_at)}{entry.cycle.initiated_by_name ? ` by ${entry.cycle.initiated_by_name}` : ""}
        </p>
      )}
      {canInitiate && entry.can_initiate && (
        <button type="button" className="btn btn-primary quarter-card-action" onClick={onInitiate}>Initiate review</button>
      )}
    </div>
  );
}
```

```jsx
// frontend/src/components/InitiateCycleDialog.jsx
import { useEffect, useState } from "react";
import { getReviewers, initiateCycle } from "../services/api";

export default function InitiateCycleDialog({ project, year, entry, onInitiated, onClose }) {
  const [reviewers, setReviewers] = useState([]);
  const [selected, setSelected] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const complete = project.platforms.every((platform) => selected[platform]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await initiateCycle(project.id, {
        year, quarter: entry.quarter,
        assignments: project.platforms.map((platform) => ({ platform, reviewer_id: selected[platform] })),
      });
      onInitiated(updated);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate the review.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Initiate Q{entry.quarter} {year} review — {project.name}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>Assign a reviewer to each platform.</p>
          {project.platforms.map((platform) => (
            <div className="field" key={platform}>
              <label htmlFor={`reviewer-${platform}`}>{platform}</label>
              <select
                id={`reviewer-${platform}`} aria-label={`Reviewer for ${platform}`} className="input"
                value={selected[platform] || ""}
                onChange={(event) => setSelected((current) => ({ ...current, [platform]: event.target.value }))}
              >
                <option value="" disabled>Choose a reviewer…</option>
                {reviewers.map((reviewer) => (
                  <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>
                ))}
              </select>
            </div>
          ))}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !complete}>{saving ? "Initiating…" : "Initiate"}</button>
        </div>
      </form>
    </div>
  );
}
```

```jsx
// frontend/src/pages/QuarterlyDashboardPage.jsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import QuarterCard from "../components/QuarterCard";
import InitiateCycleDialog from "../components/InitiateCycleDialog";
import { useCan } from "../context/AuthContext";
import { getQuarterly, getReviewYears } from "../services/api";

export default function QuarterlyDashboardPage() {
  const can = useCan();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [years, setYears] = useState([thisYear - 2, thisYear - 1, thisYear]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [initiating, setInitiating] = useState(null); // { project, entry }

  useEffect(() => {
    let cancelled = false;
    getReviewYears()
      .then((reviewYears) => { if (!cancelled) setYears((current) => [...new Set([...current, ...reviewYears])].sort((a, b) => b - a)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError("");
    getQuarterly(year)
      .then((result) => { if (!cancelled) setData(result); })
      .catch(() => { if (!cancelled) setError("Couldn't load quarterly status."); });
    return () => { cancelled = true; };
  }, [year]);

  function replaceEntry(projectId, updated) {
    setData((current) => ({
      ...current,
      projects: current.projects.map((project) => (project.id !== projectId ? project : {
        ...project,
        quarters: project.quarters.map((entry) => (entry.quarter === updated.quarter ? updated : entry)),
      })),
    }));
  }

  const projects = (data?.projects || []).filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));
  const sortedYears = [...years].sort((a, b) => b - a);

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Quarterly reviews</h1>
            <p className="page-subtitle">Each project needs at least one review per platform every quarter.</p>
          </div>
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="search" className="input" aria-label="Search projects" placeholder="Search projects…"
              value={query} onChange={(event) => setQuery(event.target.value)} style={{ width: 220 }}
            />
            <select aria-label="Year" className="input" value={year} onChange={(event) => setYear(Number(event.target.value))} style={{ width: 110 }}>
              {sortedYears.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {data && projects.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No projects found.</p></div>
        )}

        {projects.map((project) => (
          <section key={project.id} className="card quarterly-row" aria-label={project.name}>
            <div className="quarterly-row-head">
              <div className="quarterly-row-name">{project.name}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {project.platforms.map((platform) => <span key={platform} className="tag tag-outline">{platform}</span>)}
              </div>
            </div>
            {project.platforms.length === 0 ? (
              <Link to="/projects" className="card-body">Set platforms to track quarterly reviews</Link>
            ) : (
              <div className="quarter-grid">
                {project.quarters.map((entry) => (
                  <QuarterCard
                    key={entry.quarter} entry={entry} platforms={project.platforms}
                    canInitiate={can("cycles.initiate")}
                    onInitiate={() => setInitiating({ project, entry })}
                  />
                ))}
              </div>
            )}
          </section>
        ))}
      </main>

      {initiating && (
        <InitiateCycleDialog
          project={initiating.project} year={year} entry={initiating.entry}
          onInitiated={(updated) => replaceEntry(initiating.project.id, updated)}
          onClose={() => setInitiating(null)}
        />
      )}
    </div>
  );
}
```

  Append to `design-system.css`:

```css
/* — quarterly dashboard — */
.quarterly-row { padding: 20px; display: grid; gap: var(--space-3); }
.quarterly-row-head { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
.quarterly-row-name { font-family: var(--font-heading); font-weight: var(--font-heading-weight); font-size: 18px; }
.quarter-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-3); }
@media (max-width: 900px) { .quarter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .quarter-grid { grid-template-columns: 1fr; } }
.quarter-card {
  display: flex; flex-direction: column; gap: var(--space-2);
  padding: 14px; border-radius: 10px; border: 1px solid var(--color-divider); min-height: 140px;
}
.quarter-card--done { background: color-mix(in srgb, #2e9e5b 12%, var(--color-bg)); border-color: color-mix(in srgb, #2e9e5b 35%, var(--color-divider)); }
.quarter-card--in-progress { background: color-mix(in srgb, #e0b400 16%, var(--color-bg)); border-color: color-mix(in srgb, #e0b400 40%, var(--color-divider)); }
.quarter-card--overdue { background: color-mix(in srgb, var(--color-brand-coral) 12%, var(--color-bg)); border-color: color-mix(in srgb, var(--color-brand-coral) 40%, var(--color-divider)); }
.quarter-card--not-started { background: var(--color-bg); }
.quarter-card--not-applicable { background: var(--color-surface); color: var(--color-text-muted); }
.quarter-card-head { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); }
.quarter-card-title { font-weight: 600; font-size: 14px; }
.quarter-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.quarter-badge--done { background: #2e9e5b; color: #fff; }
.quarter-badge--in-progress { background: #e0b400; color: #3a2f00; }
.quarter-badge--overdue { background: var(--color-brand-coral); color: #fff; }
.quarter-badge--not-started { background: var(--color-surface); color: var(--color-text-muted); border: 1px solid var(--color-divider); }
.quarter-badge--not-applicable { background: transparent; color: var(--color-text-muted); border: 1px solid var(--color-divider); }
.quarter-card-platforms { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 13px; }
.quarter-tick { color: #2e9e5b; font-weight: 700; }
.quarter-dot { color: var(--color-text-muted); }
.quarter-card-meta { font-size: 12px; color: var(--color-text-muted); }
.quarter-card-action { margin-top: auto; align-self: flex-start; }
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS
- [ ] **Step 5: Commit** with the message `feat: add quarterly dashboard with tinted quarter cards and cycle initiation`.

---

### Task 7: Platforms on the Projects page

**Files:**
- Modify: `frontend/src/components/ProjectDialog.jsx`, `frontend/src/pages/ProjectsPage.jsx`, `frontend/src/pages/ProjectsPage.test.jsx`

**Interfaces:**
- Consumes: `setProjectPlatforms`, `PLATFORMS` (from `platforms.js`, `available` only).
- Produces:
  - `ProjectDialog` gains optional `initialPlatforms` and `withPlatforms` props.
  - `onSubmit(name, platforms)`. The `platforms` argument is `undefined` when `withPlatforms` is false, so existing callers are unchanged.

- [ ] **Step 1: Write the failing tests (append to `ProjectsPage.test.jsx`)**
  - Add `setProjectPlatforms: jest.fn()` to the api mock and import it.
  - Give both fixture projects `platforms`: p1 gets `["Android", "iOS"]` and p2 gets `[]`.

```jsx
test("shows each project's platforms", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByText("Android")).toBeInTheDocument();
  expect(within(row("Alpha")).getByText("iOS")).toBeInTheDocument();
});

test("creating a project saves its platforms", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, manager_ids: [], platforms: [] });
  setProjectPlatforms.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, platforms: ["Android", ".NET"] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(screen.getByRole("button", { name: "New project" }));
  await user.type(screen.getByLabelText("Project name"), "Gamma");
  await user.click(screen.getByRole("checkbox", { name: "Android" }));
  await user.click(screen.getByRole("checkbox", { name: ".NET" }));
  await user.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => expect(setProjectPlatforms).toHaveBeenCalledWith("p3", ["Android", ".NET"]));
  expect(await within(row("Gamma")).findByText(".NET")).toBeInTheDocument();
});

test("editing a project pre-checks and saves platforms", async () => {
  const user = userEvent.setup();
  updateProject.mockResolvedValue({ ...projects[0] });
  setProjectPlatforms.mockResolvedValue({ ...projects[0], platforms: ["Android"] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(within(row("Alpha")).getByRole("button", { name: "Edit Alpha" }));
  expect(screen.getByRole("checkbox", { name: "iOS" })).toBeChecked();
  await user.click(screen.getByRole("checkbox", { name: "iOS" }));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setProjectPlatforms).toHaveBeenCalledWith("p1", ["Android"]));
});
```

  Also rename the existing "renaming a project" test's button lookup from `"Rename Beta"` to `"Edit Beta"`, since the action is now labelled Edit.

- [ ] **Step 2: Run and verify they fail.** Expected: FAIL

- [ ] **Step 3: Implement.** In `ProjectDialog.jsx`:
  - Add the props `initialPlatforms = []` and `withPlatforms = false`.
  - Add the state `const [platforms, setPlatforms] = useState(initialPlatforms);`.
  - In submit, `await onSubmit(name.trim(), withPlatforms ? PLATFORM_LABELS.filter((p) => platforms.includes(p)) : undefined);`, with `const PLATFORM_LABELS = PLATFORMS.filter((p) => p.available).map((p) => p.label);` from `../platforms`.
  - After the name field, when `withPlatforms`, render:

```jsx
<fieldset className="field" style={{ border: "none", padding: 0, margin: "var(--space-3) 0 0" }}>
  <legend style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Platforms</legend>
  <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
    {PLATFORM_LABELS.map((platform) => (
      <label key={platform} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
        <input
          type="checkbox" checked={platforms.includes(platform)}
          onChange={() => setPlatforms((current) => current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform])}
        />
        {platform}
      </label>
    ))}
  </div>
</fieldset>
```

  In `ProjectsPage.jsx`:
  - **Platforms column:** add a `Platforms` column after Project, with `(project.platforms || []).map(tag)`, or `—` when there are none.
  - **Rename becomes Edit:** the button text is `Edit`, its aria-label is `Edit ${project.name}`, and it's still gated by `projects.edit`.
  - **Create dialog:** pass `withPlatforms`, with `onSubmit={async (name, platforms) => { const project = await createProject(name); const saved = platforms.length ? await setProjectPlatforms(project.id, platforms) : project; setProjects((current) => [{ ...project, ...saved }, ...(current || [])]); }}`.
  - **Edit dialog** (titled "Edit project"): pass `withPlatforms initialPlatforms={renaming.platforms || []}`, with `onSubmit={async (name, platforms) => { const renamed = name !== renaming.name ? await updateProject(renaming.id, name) : {}; const saved = await setProjectPlatforms(renaming.id, platforms); replaceProject({ ...renamed, ...saved, id: renaming.id }); }}`.

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS
- [ ] **Step 5: Commit** with the message `feat: set project platforms from the Projects page`.

---

### Task 8: Docker smoke test and progress log

- [ ] **Step 1: Run both suites in full.** Expected: all pass.
- [ ] **Step 2: Back up the database, then check it.**
  - Back up: `docker compose exec -T postgres pg_dump -U postgres codereviews > <scratchpad>/codereviews-before-quarterly.sql`.
  - Read `select id, name from projects` and the review counts per project and platform.
- [ ] **Step 3: Rebuild and migrate.**
  - Run `docker compose up -d --build --no-deps backend frontend`.
  - Confirm the backend log shows `Running upgrade b7c8d9e0f1a2 -> c3d4e5f6a7b8`.
  - Confirm `select * from project_platforms` matches the platforms each project has non-errored reviews for.
- [ ] **Step 4: Run the API smoke test as a temporary coordinator** (`smoke-coordinator@example.com`):
  - `GET /api/quarterly` returns 200 with 8 projects.
  - Spot-check one project's statuses against its review dates.
  - Create `Smoke Project` with platforms `Android`, initiate the current quarter with a temporary reviewer, and confirm it comes back `in_progress`. A second initiate returns 409.
  - Clean up: delete `Smoke Project` as admin (it has no reviews, so this exercises the cascade) and delete the smoke users.
  - Confirm the projects, reviews and project_platforms counts are back to their earlier values.
- [ ] **Step 5: Update `progress.md`** with a Phase 9 entry (quarterly dashboard and cycle initiation), then commit with the message `docs: log quarterly dashboard work in progress.md`.
