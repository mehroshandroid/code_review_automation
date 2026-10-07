# Roles & Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `management`, `coordinator` and `project_manager` roles (retiring `user`), a Projects page with PM assignment, PM-scoped dashboard data, a reviewer "My reviews" page, and one shared professional navbar.

**Architecture:**
- **Permissions:** one capability map (`app/auth/permissions.py`) is the single source of truth for permissions. Endpoints depend on `require_permission(...)`.
- **Project visibility:** one function, `visible_project_ids(session, user)`, returns `None` (all projects) or a set of project IDs. Every listing query and every single-review check goes through it.
- **Frontend:** `/api/auth/me` returns the user's permission keys. The frontend gates UI and routes with `hasPermission(user, key)`, never with role names, except for role labels on the Users page.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), Alembic, Postgres (SQLite in-memory for tests), pytest; React 18 (CRA), react-router v6, Jest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-07-roles-and-access-design.md`

## Global Constraints

- **Roles** are exactly: `admin`, `management`, `coordinator`, `reviewer`, `project_manager`. `user` is retired.
- **Capability keys** are exactly as in the spec's matrix:
  - `dashboard.view_all`, `dashboard.view_assigned`
  - `reviews.create`, `reviews.edit`, `reviews.assign_reviewer`, `reviews.finalize_own`, `reviews.delete`
  - `my_reviews.view`, `settings.manage`, `users.manage`
  - `projects.view`, `projects.create`, `projects.rename`, `projects.assign_pm`, `projects.delete`
  - `chat.use`
- **Home paths:** admin, management and project_manager go to `/`; reviewer to `/my-reviews`; coordinator to `/projects`.
- **Status codes:**
  - 403 when the user can see the resource but lacks the capability.
  - 404 when the user can't see the resource. This applies to single reviews, `/api/projects/{id}/reviews` and download.
  - 400 for an unknown role, or for assigning a non-PM or inactive user as a project's PM.
  - 409 for deleting a project that has reviews. Message: `This project has N reviews and can't be deleted.`
- **Reviews with no project** (`project_id IS NULL`) are visible only to `dashboard.view_all` and to the assigned reviewer.
- **Unassigned PM message:** `No projects assigned yet — contact your admin.`
- **Role labels:** Admin, Management, Coordinator, Reviewer, Project Manager.
- **Test isolation:** backend endpoint tests replace each API module's `new_session` with an in-memory SQLite sessionmaker. Any helper that needs the database therefore takes the caller's `session` and never opens its own.
- **Dev rules:** TDD for every task. Commit after each task, ending the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Commands:**
  - Backend tests: `cd backend && python -m pytest -q`.
  - Frontend tests: `cd frontend && CI=true npx react-scripts test --watchAll=false`.

## Review Focus

1. **A PM pastes a deep link** to a review on a project they aren't assigned: the report page shows "Review not found" (API 404), never the data. *Task 4 test `test_pm_cannot_open_review_outside_assigned_projects`.*
2. **A review with no project** (an old ad-hoc review): hidden from PMs in both list and detail views, but visible to its assigned reviewer. *Task 4 tests `test_unlinked_review_hidden_from_pm` and `test_assigned_reviewer_can_open_unlinked_review`.*
3. **A coordinator assigns a reviewer** to a review they can't otherwise see: allowed. Assignment needs only the capability, not visibility. *Task 4 test `test_coordinator_can_assign_reviewer`.*
4. **A brand-new Microsoft SSO user** is provisioned as `project_manager` with no projects. They land on an empty dashboard with the unassigned message, not an error. *Task 5 test `test_sso_provisions_new_user_as_project_manager_with_name`, and Task 11 test `shows the unassigned message for a PM with no projects`.*
5. **A PM with zero projects uses the chatbot:** the tool returns no rows and runs no query. It never falls back to org-wide data. *Task 6 test `test_query_reviews_with_empty_scope_returns_nothing`.*

---

## File Structure

**Backend:**
- Create `backend/app/auth/permissions.py`: capability map, home paths, `can`, `permissions_for`, `require_permission`, `visible_project_ids`, `can_view_review`.
- Modify `backend/app/auth/dependencies.py`: remove `require_roles` once there are no callers left (Task 6).
- Modify `backend/app/db/models.py`: `User.name`, new `ProjectManager` model.
- Create `backend/alembic/versions/b7c8d9e0f1a2_roles_and_project_managers.py`.
- Modify `backend/app/db/crud.py`: scoped list functions, manager-assignment functions, project delete and count functions, `list_reviews_for_reviewer`, `name` support.
- Modify `backend/app/api/projects.py`, `reviews.py`, `users.py`, `auth.py`, `settings.py`, `ollama.py`, `chat.py`.
- Modify `backend/app/chatbot/tools.py` and `agent.py`: project-scoped tool.

**Frontend:**
- Create `frontend/src/permissions.js`: `ROLE_LABELS`, `ROLES`, `hasPermission`, `initialsFor`.
- Create `frontend/src/testUtils/authUsers.js`: test-only `userWithRole(role, overrides)` that mirrors the backend map.
- Modify `frontend/src/context/AuthContext.jsx`: the default test user gets `permissions` and `home_path`. Add a `useCan()` hook.
- Modify `frontend/src/components/RouteGuards.jsx`: add `RequirePermission` and `DashboardOrHome`, remove `RequireRole`.
- Create `frontend/src/components/AppNav.jsx` and its test. Delete `TopNav.jsx`, `NavActions.jsx` and their tests.
- Create `frontend/src/components/MultiSelect.jsx`, `AssignManagersDialog.jsx`, `pages/ProjectsPage.jsx` and `pages/MyReviewsPage.jsx`, each with tests.
- Modify `frontend/src/AppRoutes.jsx`, `services/api.js`, `design-system.css`, `pages/ProjectDashboardPage.jsx`, `pages/ReviewReportPage.jsx`, `pages/UsersPage.jsx`, `components/DashboardFilters.jsx`, `components/UploadForm.jsx`, and every page that renders `TopNav`.

---

### Task 1: Permission map

**Files:**
- Create: `backend/app/auth/permissions.py`
- Test: `backend/tests/test_permissions.py`

**Interfaces:**
- Produces:
  - `ALL_ROLES: frozenset[str]`
  - `PERMISSIONS: dict[str, frozenset[str]]`
  - `HOME_PATHS: dict[str, str]`
  - `can(user, capability: str) -> bool`
  - `permissions_for(user) -> list[str]` (sorted)
  - `require_permission(*capabilities: str)`: FastAPI dependency, any-of, returns the `User`
  - `async visible_project_ids(session, user) -> set[str] | None`
  - `async can_view_review(session, user, review) -> bool`
  - The last two are added in Task 2, once the crud function exists.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_permissions.py
import pytest
from fastapi import HTTPException

from app.auth.permissions import ALL_ROLES, HOME_PATHS, PERMISSIONS, can, permissions_for, require_permission
from app.db.models import User

A, M, C, R, P = "admin", "management", "coordinator", "reviewer", "project_manager"

EXPECTED = {
    "dashboard.view_all": {A, M},
    "dashboard.view_assigned": {P},
    "reviews.create": {A, M},
    "reviews.edit": {A, M},
    "reviews.assign_reviewer": {A, M, C},
    "reviews.finalize_own": {A, M, R},
    "reviews.delete": {A},
    "my_reviews.view": {A, M, R},
    "settings.manage": {A, M},
    "users.manage": {A},
    "projects.view": {A, M, C},
    "projects.create": {A, M, C},
    "projects.rename": {A, M, C},
    "projects.assign_pm": {A, M, C},
    "projects.delete": {A, M},
    "chat.use": {A, M, P},
}


def _user(role):
    return User(id="u1", email="x@example.com", role=role, is_active=True, password_hash="", created_at=None)


def test_all_roles():
    assert ALL_ROLES == {A, M, C, R, P}


def test_permission_map_matches_spec_exactly():
    assert {key: set(roles) for key, roles in PERMISSIONS.items()} == EXPECTED


@pytest.mark.parametrize("capability", sorted(EXPECTED))
@pytest.mark.parametrize("role", sorted({A, M, C, R, P}))
def test_can_for_every_role_and_capability(role, capability):
    assert can(_user(role), capability) == (role in EXPECTED[capability])


def test_retired_user_role_has_no_capabilities():
    assert permissions_for(_user("user")) == []


def test_home_paths():
    assert HOME_PATHS == {A: "/", M: "/", P: "/", R: "/my-reviews", C: "/projects"}


def test_permissions_for_is_sorted():
    assert permissions_for(_user(R)) == ["my_reviews.view", "reviews.finalize_own"]


async def test_require_permission_allows_any_of():
    check = require_permission("reviews.create", "settings.manage")
    user = _user(M)
    assert await check(current_user=user) is user


async def test_require_permission_rejects_with_403():
    check = require_permission("users.manage")
    with pytest.raises(HTTPException) as exc:
        await check(current_user=_user(C))
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd backend && python -m pytest tests/test_permissions.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.auth.permissions'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/auth/permissions.py
"""Single source of truth for who may do what.

Endpoints depend on require_permission(...) instead of listing roles, and
every listing/detail query is scoped through visible_project_ids(...), so
adding a role or widening one only ever means editing PERMISSIONS here.
"""
from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.db.models import User

ADMIN, MANAGEMENT, COORDINATOR, REVIEWER, PROJECT_MANAGER = (
    "admin", "management", "coordinator", "reviewer", "project_manager",
)
ALL_ROLES = frozenset({ADMIN, MANAGEMENT, COORDINATOR, REVIEWER, PROJECT_MANAGER})

_PROJECT_STAFF = frozenset({ADMIN, MANAGEMENT, COORDINATOR})

PERMISSIONS: dict[str, frozenset[str]] = {
    "dashboard.view_all": frozenset({ADMIN, MANAGEMENT}),
    "dashboard.view_assigned": frozenset({PROJECT_MANAGER}),
    "reviews.create": frozenset({ADMIN, MANAGEMENT}),
    "reviews.edit": frozenset({ADMIN, MANAGEMENT}),
    "reviews.assign_reviewer": _PROJECT_STAFF,
    "reviews.finalize_own": frozenset({ADMIN, MANAGEMENT, REVIEWER}),
    "reviews.delete": frozenset({ADMIN}),
    "my_reviews.view": frozenset({ADMIN, MANAGEMENT, REVIEWER}),
    "settings.manage": frozenset({ADMIN, MANAGEMENT}),
    "users.manage": frozenset({ADMIN}),
    "projects.view": _PROJECT_STAFF,
    "projects.create": _PROJECT_STAFF,
    "projects.rename": _PROJECT_STAFF,
    "projects.assign_pm": _PROJECT_STAFF,
    "projects.delete": frozenset({ADMIN, MANAGEMENT}),
    "chat.use": frozenset({ADMIN, MANAGEMENT, PROJECT_MANAGER}),
}

HOME_PATHS: dict[str, str] = {
    ADMIN: "/",
    MANAGEMENT: "/",
    PROJECT_MANAGER: "/",
    REVIEWER: "/my-reviews",
    COORDINATOR: "/projects",
}


def can(user: User, capability: str) -> bool:
    return user.role in PERMISSIONS[capability]


def permissions_for(user: User) -> list[str]:
    return sorted(key for key, roles in PERMISSIONS.items() if user.role in roles)


def require_permission(*capabilities: str):
    """Allow the request if the user holds ANY of the given capabilities."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if not any(can(current_user, capability) for capability in capabilities):
            raise HTTPException(status_code=403, detail="You don't have permission to do this")
        return current_user
    return _check
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `cd backend && python -m pytest tests/test_permissions.py -q`
Expected: PASS (all parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/permissions.py backend/tests/test_permissions.py
git commit -m "feat: add capability map as the single source of truth for permissions"
```

---

### Task 2: Data model, migration, crud for assignments and scoping

**Files:**
- Modify: `backend/app/db/models.py` (add `User.name`, `ProjectManager`)
- Create: `backend/alembic/versions/b7c8d9e0f1a2_roles_and_project_managers.py`
- Modify: `backend/app/db/crud.py`
- Modify: `backend/app/auth/permissions.py` (add `visible_project_ids`, `can_view_review`)
- Test: `backend/tests/test_db_crud_access.py`, extend `backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: `can` from Task 1.
- Produces (crud):
  - `list_projects(session, project_ids: set[str] | None = None)`
  - `list_reviews(session, year, platform=None, project_id=None, project_ids=None)`
  - `list_review_years(session, project_ids=None)`
  - `list_reviews_for_reviewer(session, user_id) -> list[PlatformReview]`
  - `get_project_ids_for_manager(session, user_id) -> set[str]`
  - `get_project_ids_for_managers(session, user_ids: list[str]) -> dict[str, list[str]]`
  - `get_manager_ids_for_projects(session, project_ids: list[str]) -> dict[str, list[str]]`
  - `set_managers_for_project(session, project_id, user_ids: list[str]) -> None`
  - `clear_projects_for_manager(session, user_id) -> None`
  - `count_reviews_by_project(session) -> dict[str, int]`
  - `count_reviews_for_project(session, project_id) -> int`
  - `delete_project(session, project_id) -> bool`
  - `list_reviewer_candidates(session, roles: frozenset[str])`
  - `create_user(..., name: str | None = None)`
  - `update_user(..., name: str | None = None)`. The string `""` clears the name.
- Produces (permissions):
  - `visible_project_ids(session, user) -> set[str] | None`
  - `can_view_review(session, user, review) -> bool`

- [ ] **Step 1: Write the failing crud tests**

```python
# backend/tests/test_db_crud_access.py
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.models import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def _review(session, review_id, project_id, reviewer_id=None, year=2026):
    review = await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform="Android",
        status="pending_approval", project_name="P",
        created_at=datetime(year, 3, 1, tzinfo=timezone.utc), completed_at=None,
        total_score_pct=50, llm_provider="azure", llm_model=None, compile_check_mode="compiler",
        source="upload", workbook_path=None, result_data={},
    )
    if reviewer_id:
        await crud.set_review_reviewer(session, review_id, reviewer_id)
    return review


async def _seed(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_project(session, "p2", "Two")
    await crud.create_user(session, "pm1", "pm1@example.com", "h", "project_manager", name="Pat Manager")
    await crud.create_user(session, "pm2", "pm2@example.com", "h", "project_manager")


async def test_create_user_stores_name(session):
    await _seed(session)
    assert (await crud.get_user_by_id(session, "pm1")).name == "Pat Manager"


async def test_update_user_name_and_clear(session):
    await _seed(session)
    await crud.update_user(session, "pm2", name="  Sam  ")
    assert (await crud.get_user_by_id(session, "pm2")).name == "Sam"
    await crud.update_user(session, "pm2", name="")
    assert (await crud.get_user_by_id(session, "pm2")).name is None


async def test_set_managers_replaces_the_set(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1", "pm2"])
    await crud.set_managers_for_project(session, "p1", ["pm2"])
    assert await crud.get_manager_ids_for_projects(session, ["p1", "p2"]) == {"p1": ["pm2"], "p2": []}
    assert await crud.get_project_ids_for_manager(session, "pm2") == {"p1"}
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()


async def test_get_project_ids_for_managers_bulk(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1"])
    await crud.set_managers_for_project(session, "p2", ["pm1"])
    assert await crud.get_project_ids_for_managers(session, ["pm1", "pm2"]) == {"pm1": ["p1", "p2"], "pm2": []}


async def test_clear_projects_for_manager(session):
    await _seed(session)
    await crud.set_managers_for_project(session, "p1", ["pm1"])
    await crud.clear_projects_for_manager(session, "pm1")
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()


async def test_list_projects_scoped(session):
    await _seed(session)
    assert {p.id for p in await crud.list_projects(session, project_ids={"p2"})} == {"p2"}
    assert await crud.list_projects(session, project_ids=set()) == []
    assert len(await crud.list_projects(session)) == 2


async def test_list_reviews_and_years_scoped(session):
    await _seed(session)
    await _review(session, "r1", "p1", year=2025)
    await _review(session, "r2", "p2", year=2026)
    await _review(session, "r3", None, year=2026)
    assert [r.id for r in await crud.list_reviews(session, year=2026, project_ids={"p2"})] == ["r2"]
    assert await crud.list_reviews(session, year=2026, project_ids=set()) == []
    assert {r.id for r in await crud.list_reviews(session, year=2026)} == {"r2", "r3"}
    assert await crud.list_review_years(session, project_ids={"p1"}) == [2025]
    assert await crud.list_review_years(session, project_ids=set()) == []


async def test_list_reviews_for_reviewer(session):
    await _seed(session)
    await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer")
    await _review(session, "r1", "p1", reviewer_id="rev")
    await _review(session, "r2", "p2")
    assert [r.id for r in await crud.list_reviews_for_reviewer(session, "rev")] == ["r1"]


async def test_review_counts_and_delete_project(session):
    await _seed(session)
    await _review(session, "r1", "p1")
    await crud.set_managers_for_project(session, "p2", ["pm1"])
    assert await crud.count_reviews_by_project(session) == {"p1": 1}
    assert await crud.count_reviews_for_project(session, "p1") == 1
    assert await crud.delete_project(session, "p2") is True
    assert await crud.get_project_ids_for_manager(session, "pm1") == set()
    assert await crud.delete_project(session, "nope") is False


async def test_list_reviewer_candidates_by_roles(session):
    await _seed(session)
    await crud.create_user(session, "m1", "m@example.com", "h", "management")
    await crud.create_user(session, "c1", "c@example.com", "h", "coordinator")
    candidates = await crud.list_reviewer_candidates(session, frozenset({"management", "reviewer", "admin"}))
    assert [u.id for u in candidates] == ["m1"]
```

- [ ] **Step 2: Run and verify it fails**

Run: `cd backend && python -m pytest tests/test_db_crud_access.py -q`
Expected: FAIL. `create_user()` gets an unexpected keyword argument `name`, and other attributes are missing.

- [ ] **Step 3: Add the models**

In `backend/app/db/models.py`, add `name` to `User` and update the `role` comment:

```python
    role: Mapped[str] = mapped_column(String, nullable=False)  # see app.auth.permissions.ALL_ROLES
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

Then append:

```python
class ProjectManager(Base):
    """Which project_manager users may see which projects (many-to-many)."""

    __tablename__ = "project_managers"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
```

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/b7c8d9e0f1a2_roles_and_project_managers.py
"""roles & project managers: users.name, project_managers, retire 'user' role

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))
    op.create_table(
        "project_managers",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    )
    op.execute("UPDATE users SET role = 'project_manager' WHERE role = 'user'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'user' WHERE role = 'project_manager'")
    op.execute("UPDATE users SET role = 'reviewer' WHERE role IN ('management', 'coordinator')")
    op.drop_table("project_managers")
    op.drop_column("users", "name")
```

- [ ] **Step 5: Implement the crud changes**

In `backend/app/db/crud.py`:
- Add `ProjectManager` to the models import.
- Replace `list_projects`, `list_reviews`, `list_review_years`, `list_reviewer_candidates`, `create_user` and `update_user`.
- Add the new functions.

```python
async def list_projects(session: AsyncSession, project_ids: Optional[set[str]] = None) -> list[Project]:
    if project_ids is not None and not project_ids:
        return []
    query = select(Project).order_by(Project.created_at.desc())
    if project_ids is not None:
        query = query.where(Project.id.in_(project_ids))
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_reviews(
    session: AsyncSession,
    year: int,
    platform: Optional[str] = None,
    project_id: Optional[str] = None,
    project_ids: Optional[set[str]] = None,
) -> list[PlatformReview]:
    if project_ids is not None and not project_ids:
        return []
    query = select(PlatformReview).where(extract("year", PlatformReview.created_at) == year)
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if project_id:
        query = query.where(PlatformReview.project_id == project_id)
    if project_ids is not None:
        query = query.where(PlatformReview.project_id.in_(project_ids))
    query = query.order_by(PlatformReview.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_review_years(session: AsyncSession, project_ids: Optional[set[str]] = None) -> list[int]:
    if project_ids is not None and not project_ids:
        return []
    query = select(extract("year", PlatformReview.created_at)).distinct()
    if project_ids is not None:
        query = query.where(PlatformReview.project_id.in_(project_ids))
    result = await session.execute(query)
    return sorted({int(year) for (year,) in result.all()})


async def list_reviews_for_reviewer(session: AsyncSession, user_id: str) -> list[PlatformReview]:
    result = await session.execute(
        select(PlatformReview)
        .where(PlatformReview.reviewer_id == user_id)
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.scalars().all())


async def list_reviewer_candidates(session: AsyncSession, roles: frozenset[str]) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.role.in_(roles), User.is_active.is_(True))
        .order_by(User.email)
    )
    return list(result.scalars().all())


# --- project managers ---

async def get_project_ids_for_manager(session: AsyncSession, user_id: str) -> set[str]:
    result = await session.execute(select(ProjectManager.project_id).where(ProjectManager.user_id == user_id))
    return {project_id for (project_id,) in result.all()}


async def get_project_ids_for_managers(session: AsyncSession, user_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return mapping
    result = await session.execute(
        select(ProjectManager.user_id, ProjectManager.project_id)
        .where(ProjectManager.user_id.in_(user_ids))
        .order_by(ProjectManager.project_id)
    )
    for user_id, project_id in result.all():
        mapping[user_id].append(project_id)
    return mapping


async def get_manager_ids_for_projects(session: AsyncSession, project_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {project_id: [] for project_id in project_ids}
    if not project_ids:
        return mapping
    result = await session.execute(
        select(ProjectManager.project_id, ProjectManager.user_id)
        .where(ProjectManager.project_id.in_(project_ids))
        .order_by(ProjectManager.user_id)
    )
    for project_id, user_id in result.all():
        mapping[project_id].append(user_id)
    return mapping


async def set_managers_for_project(session: AsyncSession, project_id: str, user_ids: list[str]) -> None:
    await session.execute(delete(ProjectManager).where(ProjectManager.project_id == project_id))
    for user_id in dict.fromkeys(user_ids):
        session.add(ProjectManager(user_id=user_id, project_id=project_id))
    await session.commit()


async def clear_projects_for_manager(session: AsyncSession, user_id: str) -> None:
    await session.execute(delete(ProjectManager).where(ProjectManager.user_id == user_id))
    await session.commit()


async def count_reviews_by_project(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(PlatformReview.project_id, func.count())
        .where(PlatformReview.project_id.is_not(None))
        .group_by(PlatformReview.project_id)
    )
    return {project_id: count for project_id, count in result.all()}


async def count_reviews_for_project(session: AsyncSession, project_id: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(PlatformReview).where(PlatformReview.project_id == project_id)
    )
    return result.scalar_one()


async def delete_project(session: AsyncSession, project_id: str) -> bool:
    # Explicit, not just ON DELETE CASCADE: SQLite (tests) doesn't enforce FKs by default.
    await session.execute(delete(ProjectManager).where(ProjectManager.project_id == project_id))
    result = await session.execute(delete(Project).where(Project.id == project_id))
    await session.commit()
    return result.rowcount > 0
```

Replace `create_user` and `update_user`:

```python
async def create_user(
    session: AsyncSession, user_id: str, email: str, password_hash: str, role: str, name: Optional[str] = None,
) -> User:
    user = User(
        id=user_id, email=email, password_hash=password_hash, role=role, name=(name or "").strip() or None,
        is_active=True, created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession, user_id: str,
    role: Optional[str] = None, is_active: Optional[bool] = None, password_hash: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[User]:
    user = await session.get(User, user_id)
    if user is None:
        return None
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if password_hash is not None:
        user.password_hash = password_hash
    if name is not None:
        user.name = name.strip() or None
    await session.commit()
    await session.refresh(user)
    return user
```

Also make `delete_user` remove the user's assignment rows first:

```python
async def delete_user(session: AsyncSession, user_id: str) -> bool:
    await session.execute(delete(ProjectManager).where(ProjectManager.user_id == user_id))
    result = await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
    return result.rowcount > 0
```

- [ ] **Step 6: Add the visibility helpers and their tests**

Append to `backend/tests/test_permissions.py`:

```python
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.permissions import can_view_review, visible_project_ids
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


def _named(role, user_id):
    return User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)


async def test_visible_project_ids_by_role(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_user(session, "pm", "pm@example.com", "h", P)
    await crud.set_managers_for_project(session, "p1", ["pm"])
    assert await visible_project_ids(session, _named(A, "a")) is None
    assert await visible_project_ids(session, _named(M, "m")) is None
    assert await visible_project_ids(session, _named(P, "pm")) == {"p1"}
    assert await visible_project_ids(session, _named(P, "pm-unassigned")) == set()
    assert await visible_project_ids(session, _named(C, "c")) == set()
    assert await visible_project_ids(session, _named(R, "r")) == set()


async def test_can_view_review(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_user(session, "pm", "pm@example.com", "h", P)
    await crud.create_user(session, "rev", "rev@example.com", "h", R)
    await crud.set_managers_for_project(session, "p1", ["pm"])
    linked = await crud.persist_review_result(
        session, review_id="r1", project_id="p1", platform="Android", status="pending_approval",
        project_name="One", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=1,
        llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
        workbook_path=None, result_data={},
    )
    unlinked = await crud.persist_review_result(
        session, review_id="r2", project_id=None, platform="Android", status="pending_approval",
        project_name="Adhoc", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=1,
        llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
        workbook_path=None, result_data={},
    )
    unlinked = await crud.set_review_reviewer(session, "r2", "rev")
    assert await can_view_review(session, _named(P, "pm"), linked) is True
    assert await can_view_review(session, _named(P, "pm"), unlinked) is False
    assert await can_view_review(session, _named(A, "a"), unlinked) is True
    assert await can_view_review(session, _named(R, "rev"), unlinked) is True
    assert await can_view_review(session, _named(R, "other"), linked) is False
```

Append to `backend/app/auth/permissions.py`:

```python
async def visible_project_ids(session, user: User) -> set[str] | None:
    """None = every project; otherwise the exact set this user may see (possibly empty).

    Takes the caller's session so endpoint tests' in-memory DB is used.
    """
    if can(user, "dashboard.view_all"):
        return None
    if can(user, "dashboard.view_assigned"):
        return await crud.get_project_ids_for_manager(session, user.id)
    return set()


async def can_view_review(session, user: User, review) -> bool:
    if review.reviewer_id is not None and review.reviewer_id == user.id:
        return True
    visible = await visible_project_ids(session, user)
    if visible is None:
        return True
    return review.project_id is not None and review.project_id in visible
```

Add `from app.db import crud` to the imports at the top of `permissions.py`.

- [ ] **Step 7: Run the tests and verify they pass**

Run: `cd backend && python -m pytest tests/test_db_crud_access.py tests/test_permissions.py tests/test_db_crud.py -q`
Expected: PASS. Then run the full suite: `python -m pytest -q`. The existing `test_reviews_reviewer.py` fails, because `list_reviewer_candidates` now needs `roles`. Task 4 fixes the endpoint, so leave that one failing until then. Everything else should pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/models.py backend/app/db/crud.py backend/app/auth/permissions.py \
  backend/alembic/versions/b7c8d9e0f1a2_roles_and_project_managers.py \
  backend/tests/test_db_crud_access.py backend/tests/test_permissions.py
git commit -m "feat: add project manager assignments, user names, and project-scoped queries"
```

---

### Task 3: Projects API (manage, assign PMs, delete, scoped listing)

**Files:**
- Modify: `backend/app/api/projects.py`
- Test: rewrite `backend/tests/test_projects_permissions.py`, create `backend/tests/test_projects_management_api.py`

**Interfaces:**
- Consumes: `require_permission`, `can`, `visible_project_ids` (Tasks 1–2); the crud functions from Task 2.
- Produces:
  - `GET /api/projects` returns `{projects: [{id, name, created_at, review_count, manager_ids?}]}`. `manager_ids` is present only for `projects.view`.
  - `POST /api/projects` and `PATCH /api/projects/{id}`.
  - `PUT /api/projects/{id}/managers` with body `{user_ids}`, returning the project dict.
  - `DELETE /api/projects/{id}`, returning 204.
  - `GET /api/project-managers` returns `{managers: [{id, email, name}]}`.
  - `GET /api/projects/{id}/reviews` returns 404 if the project isn't visible.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_projects_management_api.py
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.projects as projects_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(projects_module, "new_session", lambda: sessionmaker())
    async with sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_project(session, "p2", "Two")
        await crud.create_user(session, "pm1", "pm1@example.com", "h", "project_manager", name="Pat")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer")
        await crud.persist_review_result(
            session, review_id="r1", project_id="p1", platform="Android", status="approved",
            project_name="One", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=80,
            llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
            workbook_path=None, result_data={},
        )
    yield sessionmaker
    await engine.dispose()


def _as(role, user_id="u1"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_coordinator_lists_all_projects_with_managers_and_counts(db):
    _as("coordinator")
    projects = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert set(projects) == {"p1", "p2"}
    assert projects["p1"]["review_count"] == 1
    assert projects["p2"]["manager_ids"] == []


def test_pm_lists_only_assigned_projects_without_manager_ids(db):
    _as("coordinator")
    client.put("/api/projects/p2/managers", json={"user_ids": ["pm1"]})
    _as("project_manager", "pm1")
    projects = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in projects] == ["p2"]
    assert "manager_ids" not in projects[0]


def test_reviewer_sees_no_projects(db):
    _as("reviewer", "rev")
    assert client.get("/api/projects").json()["projects"] == []


@pytest.mark.parametrize("role", ["admin", "management", "coordinator"])
def test_project_staff_can_create_and_rename(db, role):
    _as(role)
    created = client.post("/api/projects", json={"name": f"New {role}"})
    assert created.status_code == 200
    renamed = client.patch(f"/api/projects/{created.json()['id']}", json={"name": f"Renamed {role}"})
    assert renamed.status_code == 200


@pytest.mark.parametrize("role", ["reviewer", "project_manager"])
def test_others_cannot_create_or_rename(db, role):
    _as(role)
    assert client.post("/api/projects", json={"name": "X"}).status_code == 403
    assert client.patch("/api/projects/p1", json={"name": "X"}).status_code == 403


def test_assign_managers_replaces_set(db):
    _as("coordinator")
    response = client.put("/api/projects/p1/managers", json={"user_ids": ["pm1"]})
    assert response.status_code == 200
    assert response.json()["manager_ids"] == ["pm1"]
    response = client.put("/api/projects/p1/managers", json={"user_ids": []})
    assert response.json()["manager_ids"] == []


def test_assign_managers_rejects_non_pm_and_unknown(db):
    _as("coordinator")
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["rev"]}).status_code == 400
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["ghost"]}).status_code == 404
    assert client.put("/api/projects/nope/managers", json={"user_ids": []}).status_code == 404


def test_assign_managers_forbidden_for_pm(db):
    _as("project_manager", "pm1")
    assert client.put("/api/projects/p1/managers", json={"user_ids": ["pm1"]}).status_code == 403


def test_coordinator_cannot_delete(db):
    _as("coordinator")
    assert client.delete("/api/projects/p2").status_code == 403


@pytest.mark.parametrize("role", ["admin", "management"])
def test_delete_empty_project(db, role):
    _as(role)
    assert client.delete("/api/projects/p2").status_code == 204
    assert client.delete("/api/projects/p2").status_code == 404


def test_delete_project_with_reviews_conflicts(db):
    _as("admin")
    response = client.delete("/api/projects/p1")
    assert response.status_code == 409
    assert response.json()["detail"] == "This project has 1 reviews and can't be deleted."


def test_list_project_managers(db):
    _as("coordinator")
    assert client.get("/api/project-managers").json() == {
        "managers": [{"id": "pm1", "email": "pm1@example.com", "name": "Pat"}],
    }
    _as("reviewer")
    assert client.get("/api/project-managers").status_code == 403


def test_project_reviews_404_outside_scope(db):
    _as("project_manager", "pm1")
    assert client.get("/api/projects/p1/reviews").status_code == 404
    _as("admin")
    assert len(client.get("/api/projects/p1/reviews").json()["reviews"]) == 1
```

Replace the body of `backend/tests/test_projects_permissions.py`. Keep its fixture and `_as`, and replace every test after `_as` with:

```python
def test_list_projects_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/projects")
    assert response.status_code == 401


def test_list_projects_allowed_for_pm(test_sessionmaker):
    _as("project_manager")
    assert client.get("/api/projects").status_code == 200


def test_create_project_forbidden_for_pm(test_sessionmaker):
    _as("project_manager")
    assert client.post("/api/projects", json={"name": "Nope"}).status_code == 403


def test_rename_project_forbidden_for_reviewer(test_sessionmaker):
    _as("reviewer")
    assert client.patch("/api/projects/does-not-matter", json={"name": "Renamed"}).status_code == 403


def test_rename_project_allowed_for_coordinator_reaches_the_404_not_the_403(test_sessionmaker):
    _as("coordinator")
    assert client.patch("/api/projects/does-not-exist", json={"name": "Renamed"}).status_code == 404
```

- [ ] **Step 2: Run and verify they fail**

Run: `cd backend && python -m pytest tests/test_projects_management_api.py tests/test_projects_permissions.py -q`
Expected: FAIL, because the new endpoints are missing and the role checks are wrong.

- [ ] **Step 3: Implement**

Replace `backend/app/api/projects.py` with:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.reviews import _review_summary_to_dict
from app.auth.dependencies import get_current_user
from app.auth.permissions import PROJECT_MANAGER, can, require_permission, visible_project_ids
from app.db import crud
from app.db.session import new_session

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


class SetManagersRequest(BaseModel):
    user_ids: list[str]


def _project_to_dict(project, review_count: int = 0, manager_ids: list[str] | None = None) -> dict:
    data = {
        "id": project.id, "name": project.name, "created_at": project.created_at.isoformat(),
        "review_count": review_count,
    }
    if manager_ids is not None:
        data["manager_ids"] = manager_ids
    return data


@router.post("/api/projects")
async def create_project(body: CreateProjectRequest, user=Depends(require_permission("projects.create"))):
    async with new_session() as session:
        try:
            project = await crud.create_project(session, project_id=str(uuid.uuid4()), name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        return _project_to_dict(project, manager_ids=[])


@router.get("/api/projects")
async def list_projects(user=Depends(get_current_user)):
    async with new_session() as session:
        staff = can(user, "projects.view")
        scope = None if staff else await visible_project_ids(session, user)
        projects = await crud.list_projects(session, project_ids=scope)
        counts = await crud.count_reviews_by_project(session)
        managers = await crud.get_manager_ids_for_projects(session, [p.id for p in projects]) if staff else {}
    return {"projects": [
        _project_to_dict(p, counts.get(p.id, 0), managers.get(p.id, []) if staff else None) for p in projects
    ]}


@router.patch("/api/projects/{project_id}")
async def update_project(project_id: str, body: CreateProjectRequest, user=Depends(require_permission("projects.rename"))):
    async with new_session() as session:
        try:
            project = await crud.update_project_name(session, project_id=project_id, name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _project_to_dict(project)


@router.put("/api/projects/{project_id}/managers")
async def set_project_managers(project_id: str, body: SetManagersRequest, user=Depends(require_permission("projects.assign_pm"))):
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        for user_id in body.user_ids:
            candidate = await crud.get_user_by_id(session, user_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
            if candidate.role != PROJECT_MANAGER or not candidate.is_active:
                raise HTTPException(status_code=400, detail=f"{candidate.email} is not an active project manager.")
        await crud.set_managers_for_project(session, project_id, body.user_ids)
        manager_ids = (await crud.get_manager_ids_for_projects(session, [project_id]))[project_id]
        review_count = await crud.count_reviews_for_project(session, project_id)
        return _project_to_dict(project, review_count, manager_ids)


@router.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, user=Depends(require_permission("projects.delete"))):
    async with new_session() as session:
        if await crud.get_project(session, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        review_count = await crud.count_reviews_for_project(session, project_id)
        if review_count > 0:
            raise HTTPException(status_code=409, detail=f"This project has {review_count} reviews and can't be deleted.")
        await crud.delete_project(session, project_id)
    return Response(status_code=204)


@router.get("/api/project-managers")
async def list_project_managers(user=Depends(require_permission("projects.assign_pm"))):
    async with new_session() as session:
        candidates = await crud.list_reviewer_candidates(session, frozenset({PROJECT_MANAGER}))
    return {"managers": [{"id": c.id, "email": c.email, "name": c.name} for c in candidates]}


@router.get("/api/projects/{project_id}/reviews")
async def list_project_reviews(project_id: str, user=Depends(get_current_user)):
    async with new_session() as session:
        scope = await visible_project_ids(session, user)
        if scope is not None and project_id not in scope:
            raise HTTPException(status_code=404, detail="Project not found")
        reviews = await crud.list_reviews_for_project(session, project_id)
        return {"reviews": [_review_summary_to_dict(r) for r in reviews]}
```

(`list_reviewer_candidates` is reused with the PM role. It already filters on active users and sorts by email.)

- [ ] **Step 4: Run and verify they pass**

Run: `cd backend && python -m pytest tests/test_projects_management_api.py tests/test_projects_permissions.py tests/test_projects_api.py -q`
Expected: PASS. If `test_projects_api.py` asserts the exact old dict shape (`{"id","name","created_at"}`), update those assertions to include `"review_count": 0` and, for the default admin user, `"manager_ids": []`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/projects.py backend/tests/test_projects_management_api.py backend/tests/test_projects_permissions.py backend/tests/test_projects_api.py
git commit -m "feat: add project management API with PM assignment and guarded delete"
```

---

### Task 4: Reviews API scoping, reviewer finalization, My reviews

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: create `backend/tests/test_reviews_access.py`; update `test_reviews_permissions.py`, `test_reviews_reviewer.py`, `test_reviews_create.py`, `test_reviews_clause_preview.py` and `test_reviews_delete.py` wherever they use the `user` or old `reviewer` roles.

**Interfaces:**
- Consumes: `require_permission`, `can`, `visible_project_ids`, `can_view_review`, `PERMISSIONS` (Tasks 1–2).
- Produces:
  - `GET /api/my/reviews` returns `{reviews: [summary]}`.
  - The summary dict gains `reviewer_id`.
  - `GET /api/reviewers` returns `{reviewers: [{id, email, name}]}`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_reviews_access.py
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


async def _review(session, review_id, project_id, reviewer_id=None):
    await crud.persist_review_result(
        session, review_id=review_id, project_id=project_id, platform="Android", status="pending_approval",
        project_name="P", created_at=NOW, completed_at=NOW, total_score_pct=50, llm_provider="azure",
        llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None,
        result_data={"category_scores": []},
    )
    if reviewer_id:
        await crud.set_review_reviewer(session, review_id, reviewer_id)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reviews_module, "new_session", lambda: sessionmaker())
    async with sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_project(session, "p2", "Two")
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(session, "mgmt", "mgmt@example.com", "h", "management")
        await crud.create_user(session, "coord", "coord@example.com", "h", "coordinator")
        await crud.set_managers_for_project(session, "p1", ["pm"])
        await _review(session, "in-scope", "p1")
        await _review(session, "out-scope", "p2", reviewer_id="rev")
        await _review(session, "unlinked", None, reviewer_id="rev")
    yield sessionmaker
    await engine.dispose()


def _as(role, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_pm_lists_only_assigned_reviews(db):
    _as("project_manager", "pm")
    assert [r["id"] for r in client.get("/api/reviews?year=2026").json()["reviews"]] == ["in-scope"]
    assert client.get("/api/reviews/years").json() == {"years": [2026]}


def test_unlinked_review_hidden_from_pm(db):
    _as("project_manager", "pm")
    assert client.get("/api/reviews/unlinked").status_code == 404


def test_pm_cannot_open_review_outside_assigned_projects(db):
    _as("project_manager", "pm")
    assert client.get("/api/reviews/out-scope").status_code == 404
    assert client.get("/api/reviews/out-scope/download").status_code == 404
    assert client.get("/api/reviews/in-scope").status_code == 200


def test_assigned_reviewer_can_open_unlinked_review(db):
    _as("reviewer", "rev")
    assert client.get("/api/reviews/unlinked").status_code == 200
    assert client.get("/api/reviews/in-scope").status_code == 404


def test_reviewer_has_no_dashboard_data(db):
    _as("reviewer", "rev")
    assert client.get("/api/reviews?year=2026").json()["reviews"] == []
    assert client.get("/api/reviews/years").json() == {"years": []}


def test_my_reviews(db):
    _as("reviewer", "rev")
    ids = [r["id"] for r in client.get("/api/my/reviews").json()["reviews"]]
    assert set(ids) == {"out-scope", "unlinked"}
    _as("project_manager", "pm")
    assert client.get("/api/my/reviews").status_code == 403


def test_assigned_reviewer_can_finalize(db):
    _as("reviewer", "rev")
    response = client.patch("/api/reviews/out-scope", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_unassigned_reviewer_cannot_finalize(db):
    _as("reviewer", "someone-else")
    assert client.patch("/api/reviews/out-scope", json={"status": "approved"}).status_code == 404


def test_pm_can_see_but_not_edit(db):
    _as("project_manager", "pm")
    assert client.patch("/api/reviews/in-scope", json={"status": "approved"}).status_code == 403


def test_management_can_edit_any(db):
    _as("management", "mgmt")
    assert client.patch("/api/reviews/in-scope", json={"status": "approved"}).status_code == 200


def test_reviewer_cannot_reassign(db):
    _as("reviewer", "rev")
    assert client.patch("/api/reviews/out-scope/reviewer", json={"reviewer_id": None}).status_code == 403


def test_coordinator_can_assign_reviewer(db):
    _as("coordinator", "coord")
    response = client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "mgmt"})
    assert response.status_code == 200
    assert response.json()["reviewer_id"] == "mgmt"


def test_cannot_assign_pm_as_reviewer(db):
    _as("coordinator", "coord")
    assert client.patch("/api/reviews/in-scope/reviewer", json={"reviewer_id": "pm"}).status_code == 400


def test_reviewer_candidates_include_management(db):
    _as("coordinator", "coord")
    reviewers = client.get("/api/reviewers").json()["reviewers"]
    assert {r["id"] for r in reviewers} == {"rev", "mgmt"}
    assert {"id": "rev", "email": "rev@example.com", "name": "Rae"} in reviewers


@pytest.mark.parametrize("role", ["coordinator", "reviewer", "project_manager"])
def test_only_creators_can_start_or_upload(db, role):
    _as(role, "x")
    assert client.post("/api/reviews", data={"platform": "Android"}).status_code == 403
    assert client.post("/api/reviews/clause-preview", data={"platform": "Android"}).status_code == 403
    assert client.get("/api/reviews/nonexistent/progress").status_code == 403


def test_delete_review_admin_only(db):
    _as("management", "mgmt")
    assert client.delete("/api/reviews/in-scope").status_code == 403
```

- [ ] **Step 2: Run and verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_access.py -q`
Expected: FAIL (scoping is missing, `/api/my/reviews` returns 404, and so on)

- [ ] **Step 3: Implement in `backend/app/api/reviews.py`**

1. Imports: replace `from app.auth.dependencies import get_current_user, require_roles` with:

```python
from app.auth.dependencies import get_current_user
from app.auth.permissions import PERMISSIONS, can, can_view_review, require_permission, visible_project_ids
```

2. `create_review`: change its dependency to `user=Depends(require_permission("reviews.create"))`. In the override block, delete the inner role check, so it reads:

```python
    clause_overrides: dict = {}
    if input_error is None and clauseChecklistOverrides:
        try:
            clause_overrides = json.loads(clauseChecklistOverrides)
        except json.JSONDecodeError:
            input_error = "clauseChecklistOverrides must be valid JSON."
```

3. `_review_summary_to_dict`: add `"reviewer_id": review.reviewer_id,` after `"status"`.

4. Replace the list, years, my-reviews, upload and preview dependencies:

```python
@router.get("/api/reviews")
async def list_reviews(year: int, platform: str | None = None, project_id: str | None = None, user=Depends(get_current_user)):
    async with new_session() as session:
        scope = await visible_project_ids(session, user)
        reviews = await crud.list_reviews(session, year=year, platform=platform, project_id=project_id, project_ids=scope)
    return {"reviews": [_review_summary_to_dict(review) for review in reviews]}


@router.get("/api/reviews/years")
async def list_review_years(user=Depends(get_current_user)):
    async with new_session() as session:
        scope = await visible_project_ids(session, user)
        years = await crud.list_review_years(session, project_ids=scope)
    return {"years": years}


@router.get("/api/my/reviews")
async def list_my_reviews(user=Depends(require_permission("my_reviews.view"))):
    async with new_session() as session:
        reviews = await crud.list_reviews_for_reviewer(session, user.id)
    return {"reviews": [_review_summary_to_dict(review) for review in reviews]}
```

   - `upload_completed_review`: `user=Depends(require_permission("reviews.create"))`.
   - `clause_preview`: `user=Depends(require_permission("reviews.create"))`.

5. `get_progress`: `user=Depends(require_permission("reviews.create"))`. Progress only serves live, in-memory runs started from the run-review screen.

6. Replace `get_review`, `update_review`, `delete_review`, `list_reviewers` and `update_review_reviewer`:

```python
async def _get_visible_review(session, user, review_id):
    review = await crud.get_review_by_id(session, review_id)
    if review is None or not await can_view_review(session, user, review):
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.get("/api/reviews/{review_id}")
async def get_review(review_id: str, user=Depends(get_current_user)):
    async with new_session() as session:
        review = await _get_visible_review(session, user, review_id)
    return _review_to_dict(review)


@router.patch("/api/reviews/{review_id}")
async def update_review(review_id: str, body: UpdateReviewRequest, user=Depends(get_current_user)):
    if body.status is not None and body.status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_REVIEW_STATUSES)}")

    async with new_session() as session:
        existing = await _get_visible_review(session, user, review_id)
    is_assigned = existing.reviewer_id == user.id
    if not (can(user, "reviews.edit") or (can(user, "reviews.finalize_own") and is_assigned)):
        raise HTTPException(status_code=403, detail="You don't have permission to do this")

    category_scores = None
    total_score_pct = None
    if body.category_scores is not None:
        category_scores, total_score_pct = _recompute_category_scores(body.category_scores)

    async with new_session() as session:
        review = await crud.update_review(
            session, review_id, category_scores=category_scores, total_score_pct=total_score_pct, status=body.status,
        )
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return _review_to_dict(review)


@router.delete("/api/reviews/{review_id}", status_code=204)
async def delete_review(review_id: str, user=Depends(require_permission("reviews.delete"))):
    async with new_session() as session:
        review = await crud.get_review_by_id(session, review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Review not found")
        workbook_path = review.workbook_path
        await crud.delete_review(session, review_id)
    if workbook_path:
        Path(workbook_path).unlink(missing_ok=True)
    return Response(status_code=204)


REVIEWER_ROLES = PERMISSIONS["reviews.finalize_own"]


@router.get("/api/reviewers")
async def list_reviewers(user=Depends(require_permission("reviews.assign_reviewer"))):
    async with new_session() as session:
        candidates = await crud.list_reviewer_candidates(session, REVIEWER_ROLES)
    return {"reviewers": [{"id": c.id, "email": c.email, "name": c.name} for c in candidates]}


@router.patch("/api/reviews/{review_id}/reviewer")
async def update_review_reviewer(
    review_id: str, body: UpdateReviewerRequest, user=Depends(require_permission("reviews.assign_reviewer")),
):
    if body.reviewer_id is not None:
        async with new_session() as session:
            candidate = await crud.get_user_by_id(session, body.reviewer_id)
        if candidate is None or not candidate.is_active or candidate.role not in REVIEWER_ROLES:
            raise HTTPException(status_code=400, detail="reviewer_id must be an active reviewer, management or admin account.")

    async with new_session() as session:
        review = await crud.set_review_reviewer(session, review_id, body.reviewer_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return _review_to_dict(review)
```

7. `download_review`: keep the live-state branch, but only for users with `reviews.create`. Scope the persisted branch:

```python
@router.get("/api/reviews/{review_id}/download")
async def download_review(review_id: str, user=Depends(get_current_user)):
    state = _reviews.get(review_id)
    if state is not None and state["download_path"] is not None and can(user, "reviews.create"):
        ...  # unchanged live-file branch
    async with new_session() as session:
        review = await crud.get_review_by_id(session, review_id)
        visible = review is not None and await can_view_review(session, user, review)
    if not visible or review.workbook_path is None:
        raise HTTPException(status_code=404, detail="Result not available")
    ...  # unchanged persisted-file branch
```

- [ ] **Step 4: Update the legacy tests that use retired or narrowed roles**

- `test_reviews_permissions.py`:
  - Rename `"user"` → `"project_manager"`. Listing returns 200 with `[]`, and download returns 404, because a PM with no projects sees nothing.
  - `test_edit_review_scores_forbidden_for_user` becomes `_as("project_manager")`, expecting 404, because a non-visible review returns 404 before the capability check.
  - The `reviewer` edit test becomes `_as("management")`, expecting 404 (still the unknown-review path).
- `test_reviews_reviewer.py`:
  - Seed users with roles `admin`, `reviewer`, `management` and `project_manager`. Assert that the list is the active admin, reviewer and management users, each including `"name"`.
  - Any assertion that a `user`-role caller may assign a reviewer becomes `project_manager`, expecting **403**.
  - Assigning a `project_manager` as reviewer returns 400.
- `test_reviews_create.py` / `test_reviews_clause_preview.py`: tests asserting that the `user` role can't set clause overrides now assert that `project_manager` gets **403** from `POST /api/reviews` and from `/api/reviews/clause-preview`.
- `test_reviews_delete.py`: `"reviewer"` / `"user"` forbidden cases become `"management"` / `"project_manager"`, still 403.
- `test_review_detail_api.py` / `test_reviews_download.py` / `test_reviews_update.py`: these run as the default admin, so no change. If a test seeds data through its own sessionmaker, make sure `can_view_review` sees the same session. It does, because the endpoint passes its own session.

Run: `cd backend && python -m pytest -q`
Expected: the whole suite passes, except tests in files that Tasks 5–6 rewrite: `test_users_api.py`, `test_auth_api.py`, `test_settings_permissions.py` and `test_ollama_chat_permissions.py`, wherever they reference the `user` role.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/
git commit -m "feat: scope reviews by project, let assigned reviewers finalize, add My reviews endpoint"
```

---

### Task 5: Users API and auth (`/me`, names, SSO provisioning)

**Files:**
- Modify: `backend/app/api/users.py`, `backend/app/api/auth.py`
- Test: update `backend/tests/test_users_api.py` and `backend/tests/test_auth_api.py`, and add tests as below

**Interfaces:**
- Consumes: `ALL_ROLES`, `HOME_PATHS`, `PROJECT_MANAGER`, `permissions_for`, `require_permission`; crud `name` / `clear_projects_for_manager` / `get_project_ids_for_managers`.
- Produces:
  - `GET /api/auth/me` returns `{id, email, role, name, home_path, permissions}`.
  - `GET /api/users` rows add `name`, plus `project_ids` for PMs.
  - `POST /api/users` and `PATCH /api/users/{id}` accept `name`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_users_api.py`, reusing that file's existing sessionmaker fixture (`test_sessionmaker`) and admin default:

```python
async def test_create_user_with_new_role_and_name(test_sessionmaker):
    response = client.post("/api/users", json={
        "email": "co@example.com", "password": "longenough", "role": "coordinator", "name": "Cora",
    })
    assert response.status_code == 200
    assert response.json()["role"] == "coordinator"
    assert response.json()["name"] == "Cora"


async def test_create_user_rejects_retired_user_role(test_sessionmaker):
    response = client.post("/api/users", json={"email": "u@example.com", "password": "longenough", "role": "user"})
    assert response.status_code == 400


async def test_list_users_includes_pm_project_ids(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.set_managers_for_project(session, "p1", ["pm"])
    rows = {u["id"]: u for u in client.get("/api/users").json()["users"]}
    assert rows["pm"]["project_ids"] == ["p1"]


async def test_role_change_away_from_pm_clears_assignments(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.set_managers_for_project(session, "p1", ["pm"])
    client.patch("/api/users/pm", json={"role": "reviewer"})
    async with test_sessionmaker() as session:
        assert await crud.get_project_ids_for_manager(session, "pm") == set()


async def test_deactivating_pm_clears_assignments(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.create_project(session, "p1", "One")
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.set_managers_for_project(session, "p1", ["pm"])
    client.patch("/api/users/pm", json={"is_active": False})
    async with test_sessionmaker() as session:
        assert await crud.get_project_ids_for_manager(session, "pm") == set()


async def test_update_user_name(test_sessionmaker):
    async with test_sessionmaker() as session:
        await crud.create_user(session, "r", "r@example.com", "h", "reviewer")
    assert client.patch("/api/users/r", json={"name": "Rae"}).json()["name"] == "Rae"


def test_users_api_forbidden_for_management():
    user = User(id="m", email="m@example.com", role="management", is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user
    assert client.get("/api/users").status_code == 403
```

(If `test_users_api.py` lacks any of these imports, add `from app.db import crud`, `from app.db.models import User` and `from app.auth.dependencies import get_current_user`. Change any existing test that creates a `"user"`-role account to use `"project_manager"`.)

Append to `backend/tests/test_auth_api.py`, reusing its fixtures and `_create_user` helper:

```python
async def test_me_returns_name_home_path_and_permissions(test_sessionmaker):
    await _create_user(test_sessionmaker, email="rev@example.com", password="correct horse", role="reviewer")
    client.post("/api/auth/login", json={"email": "rev@example.com", "password": "correct horse"})
    body = client.get("/api/auth/me").json()
    assert body["home_path"] == "/my-reviews"
    assert body["permissions"] == ["my_reviews.view", "reviews.finalize_own"]
    assert "name" in body


async def test_sso_provisions_new_user_as_project_manager_with_name(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(auth_module.microsoft_auth, "exchange_code_for_claims",
                        lambda code: {"email": "new@example.com", "name": "New Person"})
    client.cookies.set("sso_state", "s1")
    response = client.get("/api/auth/microsoft/callback?code=c&state=s1", follow_redirects=False)
    assert response.status_code in (302, 307)
    async with test_sessionmaker() as session:
        user = await crud.get_user_by_email(session, "new@example.com")
    assert user.role == "project_manager"
    assert user.name == "New Person"
```

(Match `auth_module`, `crud` and the session-fixture names to what `test_auth_api.py` already imports. Its existing SSO tests show how it patches `exchange_code_for_claims`, so follow that pattern exactly. Change any existing assertion that SSO provisions `role == "user"` to `"project_manager"`.)

- [ ] **Step 2: Run and verify they fail**

Run: `cd backend && python -m pytest tests/test_users_api.py tests/test_auth_api.py -q`
Expected: FAIL

- [ ] **Step 3: Implement `users.py`**

```python
# top of backend/app/api/users.py
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.auth.hashing import hash_password
from app.auth.permissions import ALL_ROLES, PROJECT_MANAGER, require_permission
from app.db import crud
from app.db.session import new_session

router = APIRouter(dependencies=[Depends(require_permission("users.manage"))])

ALLOWED_ROLES = ALL_ROLES
MIN_PASSWORD_LENGTH = 8


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str
    name: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    name: str | None = None


def _user_to_dict(user, project_ids: list[str] | None = None) -> dict:
    data = {
        "id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "is_active": user.is_active, "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if user.role == PROJECT_MANAGER:
        data["project_ids"] = project_ids or []
    return data
```

- In `create_user`, pass `name=body.name` to `crud.create_user`.
- In `list_users`:

```python
@router.get("/api/users")
async def list_users():
    async with new_session() as session:
        users = await crud.list_users(session)
        assignments = await crud.get_project_ids_for_managers(
            session, [u.id for u in users if u.role == PROJECT_MANAGER],
        )
    return {"users": [_user_to_dict(u, assignments.get(u.id)) for u in users]}
```

- In `update_user`:
  - Replace `current_user=Depends(require_roles("admin"))` with `current_user=Depends(require_permission("users.manage"))`, and do the same in `delete_user`.
  - Pass `name=body.name` to `crud.update_user`.
  - After the update, clear the assignments when needed:

```python
    password_hash = hash_password(body.password) if body.password is not None else None
    async with new_session() as session:
        user = await crud.update_user(
            session, user_id, role=body.role, is_active=body.is_active, password_hash=password_hash, name=body.name,
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.role != PROJECT_MANAGER or not user.is_active:
            await crud.clear_projects_for_manager(session, user.id)
        assignments = await crud.get_project_ids_for_managers(session, [user.id]) if user.role == PROJECT_MANAGER else {}
    return _user_to_dict(user, assignments.get(user.id))
```

- [ ] **Step 4: Implement `auth.py`**

```python
from app.auth.permissions import HOME_PATHS, PROJECT_MANAGER, permissions_for


def _user_to_dict(user) -> dict:
    return {
        "id": user.id, "email": user.email, "role": user.role, "name": user.name,
        "home_path": HOME_PATHS.get(user.role, "/"),
        "permissions": permissions_for(user),
    }
```

In `microsoft_callback`, replace the provisioning block:

```python
    display_name = claims.get("name")
    async with new_session() as session:
        user = await crud.get_user_by_email(session, email)
        if user is None:
            user = await crud.create_user(
                session, user_id=str(uuid.uuid4()), email=email, password_hash="",
                role=PROJECT_MANAGER, name=display_name,
            )
        elif not user.name and display_name:
            user = await crud.update_user(session, user.id, name=display_name)
```

- [ ] **Step 5: Run and verify they pass**

Run: `cd backend && python -m pytest tests/test_users_api.py tests/test_auth_api.py tests/test_admin_seed.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/users.py backend/app/api/auth.py backend/tests/test_users_api.py backend/tests/test_auth_api.py
git commit -m "feat: support new roles and names in users API, expose permissions and home path on /me"
```

---

### Task 6: Settings, Ollama and chat permissions; scoped chatbot; remove `require_roles`

**Files:**
- Modify: `backend/app/api/settings.py`, `backend/app/api/ollama.py`, `backend/app/api/chat.py`, `backend/app/chatbot/tools.py`, `backend/app/chatbot/agent.py`, `backend/app/auth/dependencies.py`
- Test: update `test_settings_permissions.py`, `test_ollama_chat_permissions.py`, `test_chat_api.py`, `test_chatbot_agent.py` and `test_auth_dependencies.py`; extend `test_chatbot_tools.py`

**Interfaces:**
- Consumes: `require_permission`, `visible_project_ids`.
- Produces:
  - `_query_reviews(..., project_ids: set[str] | None = None)`
  - `make_query_reviews_tool(project_ids)`, which returns a LangChain tool named `query_reviews`
  - `_build_agent_executor(project_ids=None)`
  - `answer_question(message, history, project_ids=None)`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_chatbot_tools.py`, using its existing DB fixture and seeding pattern:

```python
async def test_query_reviews_with_empty_scope_returns_nothing(monkeypatch):
    from app.chatbot import tools as tools_module

    def _boom():
        raise AssertionError("must not open a session for an empty scope")

    monkeypatch.setattr(tools_module, "new_session", _boom)
    assert await tools_module._query_reviews(project_ids=set()) == []


async def test_query_reviews_filters_to_scope(<existing db fixture>):
    # seed one review on project "p1" and one on "p2" with the file's existing helper
    from app.chatbot.tools import _query_reviews
    results = await _query_reviews(project_ids={"p1"})
    assert {r["id"] for r in results} == {<id of the p1 review>}
```

(The second test must use the fixture and seeding helper already in `test_chatbot_tools.py`. Give the two seeded reviews `project_id="p1"` and `project_id="p2"`.)

In `test_chatbot_agent.py`, replace every `lambda: fake_executor` with `lambda project_ids=None: fake_executor`, and add:

```python
async def test_answer_question_passes_scope_to_executor(monkeypatch):
    seen = {}

    def fake_build(project_ids=None):
        seen["project_ids"] = project_ids
        return _FakeExecutor({"output": "ok", "intermediate_steps": []})

    monkeypatch.setattr(agent_module, "_build_agent_executor", fake_build)
    await answer_question("q", [], project_ids={"p1"})
    assert seen["project_ids"] == {"p1"}
```

(Use whatever fake-executor class the file already defines, and match its constructor.)

In `test_chat_api.py`, change both `fake_answer_question(message, history)` to `fake_answer_question(message, history, project_ids=None)`. Then add a fixture override that stubs `visible_project_ids`, since that test doesn't configure a DB:

```python
@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    async def _all(session, user):
        return None

    class _NullSession:
        async def __aenter__(self): return None
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(chat_module, "visible_project_ids", _all)
    monkeypatch.setattr(chat_module, "new_session", lambda: _NullSession())
```

Rewrite `test_ollama_chat_permissions.py`'s role tests:

```python
def test_list_ollama_models_forbidden_for_pm():
    _as("project_manager")
    assert client.get("/api/ollama/models").status_code == 403


def test_list_ollama_models_allowed_for_management(monkeypatch):
    _as("management")
    async def _models():
        return []
    monkeypatch.setattr(ollama_module.ollama_client, "list_models", _models)
    assert client.get("/api/ollama/models").status_code == 200


def test_chat_forbidden_for_coordinator():
    _as("coordinator")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 403


def test_chat_forbidden_for_reviewer():
    _as("reviewer")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 403
```

(Add `import app.api.ollama as ollama_module` if it isn't imported already. Keep the existing `requires_login` tests.)

In `test_settings_permissions.py`:
- Change `_as("user")` → `_as("project_manager")` (still 403).
- Change `_as("reviewer")` "allowed" → `_as("management")` (200).
- Add a test that `_as("reviewer")` gets 403 on `GET /api/settings/llm-provider`.

In `test_auth_dependencies.py`: delete the `require_roles` tests. `test_permissions.py` covers `require_permission`.

- [ ] **Step 2: Run and verify they fail**

Run: `cd backend && python -m pytest tests/test_chatbot_tools.py tests/test_chatbot_agent.py tests/test_chat_api.py tests/test_ollama_chat_permissions.py tests/test_settings_permissions.py -q`
Expected: FAIL

- [ ] **Step 3: Implement**

`settings.py`:

```python
from app.auth.permissions import require_permission

router = APIRouter(dependencies=[Depends(require_permission("settings.manage"))])
```

`ollama.py`:

```python
from app.auth.permissions import require_permission


@router.get("/api/ollama/models")
async def list_ollama_models(user=Depends(require_permission("reviews.create", "settings.manage"))):
    return {"models": await ollama_client.list_models()}
```

`chat.py`:

```python
from app.auth.permissions import require_permission, visible_project_ids
from app.db.session import new_session


@router.post("/api/chat")
async def chat(body: ChatRequest, user=Depends(require_permission("chat.use"))):
    if is_stub_mode():
        ...  # unchanged
    async with new_session() as session:
        project_ids = await visible_project_ids(session, user)
    history = [{"role": message.role, "content": message.content} for message in body.history]
    return await answer_question(body.message, history, project_ids=project_ids)
```

`tools.py`:
- Add `project_ids: Optional[set[str]] = None` as the last parameter of `_query_reviews`.
- At the top of its body, before building the query:

```python
    if project_ids is not None and not project_ids:
        return []
```

- After the existing filters:

```python
    if project_ids is not None:
        query = query.where(PlatformReview.project_id.in_(project_ids))
```

- Keep the module-level `query_reviews` tool (unscoped, used only by existing tests) and add a factory under it:

```python
def make_query_reviews_tool(project_ids: Optional[set[str]]):
    """A query_reviews tool bound to one user's visible projects (None = all).

    Scoping lives here in code -- not in the prompt -- so the model can't
    talk its way into another project's data.
    """
    @tool("query_reviews")
    async def scoped_query_reviews(
        platform: Optional[str] = None,
        year: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_score: Optional[float] = None,
        min_score: Optional[float] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[dict]:
        return await _query_reviews(platform, year, start_date, end_date, max_score, min_score, limit, project_ids)

    scoped_query_reviews.description = query_reviews.description
    return scoped_query_reviews
```

`agent.py`:

```python
from app.chatbot.tools import make_query_reviews_tool


def _build_agent_executor(project_ids=None) -> AgentExecutor:
    llm = ...  # unchanged
    prompt = ...  # unchanged
    tool = make_query_reviews_tool(project_ids)
    agent = create_tool_calling_agent(llm, [tool], prompt)
    return AgentExecutor(agent=agent, tools=[tool], return_intermediate_steps=True, max_iterations=5)


async def answer_question(message: str, history: list[dict], project_ids=None) -> dict:
    executor = _build_agent_executor(project_ids)
    ...  # unchanged
```

`dependencies.py`: delete `require_roles`. Then confirm there are no callers left:

Run: `cd backend && grep -rn "require_roles" app tests`
Expected: no output.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: every test passes. Fix any remaining test that still uses `"user"`, or relies on the old `reviewer` access to settings or the dashboard, by switching it to the role that now holds that capability.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: gate settings/ollama/chat by capability and scope the chatbot to visible projects"
```

---

### Task 7: Frontend permissions plumbing (AuthContext, guards, API client)

**Files:**
- Create: `frontend/src/permissions.js`, `frontend/src/permissions.test.js`, `frontend/src/testUtils/authUsers.js`
- Modify: `frontend/src/context/AuthContext.jsx`, `frontend/src/components/RouteGuards.jsx`, `frontend/src/components/RouteGuards.test.jsx`, `frontend/src/services/api.js`

**Interfaces:**
- Produces:
  - `ROLES` (ordered array), `ROLE_LABELS`, `hasPermission(user, permission)`, `hasAny(user, permissions)`, `initialsFor(user)`.
  - `useCan()`, which returns `(permission) => boolean`.
  - `userWithRole(role, overrides)` (tests only).
  - `RequirePermission({ anyOf, children })` and `DashboardOrHome({ children })`.
  - New api functions:
    - `getMyReviews()`
    - `getProjectManagers()`
    - `setProjectManagers(projectId, userIds)`
    - `deleteProject(projectId)`
    - `createUser(email, password, role, name)`
    - `updateUser(userId, { role, isActive, password, name })`

- [ ] **Step 1: Write the failing tests**

```js
// frontend/src/permissions.test.js
import { hasPermission, hasAny, initialsFor, ROLES, ROLE_LABELS } from "./permissions";

test("hasPermission reads the user's permission list", () => {
  expect(hasPermission({ permissions: ["chat.use"] }, "chat.use")).toBe(true);
  expect(hasPermission({ permissions: [] }, "chat.use")).toBe(false);
  expect(hasPermission(null, "chat.use")).toBe(false);
});

test("hasAny", () => {
  expect(hasAny({ permissions: ["a"] }, ["b", "a"])).toBe(true);
  expect(hasAny({ permissions: ["a"] }, ["b"])).toBe(false);
});

test("initials from name, else from email", () => {
  expect(initialsFor({ name: "Mehrosh Mehboob", email: "x@y.com" })).toBe("MM");
  expect(initialsFor({ name: "Cher", email: "x@y.com" })).toBe("C");
  expect(initialsFor({ name: null, email: "jane.doe@example.com" })).toBe("JD");
  expect(initialsFor({ email: "admin@example.com" })).toBe("A");
});

test("five roles with labels", () => {
  expect(ROLES).toEqual(["admin", "management", "coordinator", "reviewer", "project_manager"]);
  expect(ROLE_LABELS.project_manager).toBe("Project Manager");
});
```

Replace `frontend/src/components/RouteGuards.test.jsx` with:

```jsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import { RequireAuth, RequirePermission, DashboardOrHome } from "./RouteGuards";
import { userWithRole } from "../testUtils/authUsers";

function renderAt(path, user, element) {
  return render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/my-reviews" element={<div>my reviews page</div>} />
          <Route path="/projects" element={<div>projects page</div>} />
          <Route path="/guarded" element={element} />
          <Route path="/" element={<RequireAuth><DashboardOrHome><div>dashboard</div></DashboardOrHome></RequireAuth>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

test("RequireAuth sends anonymous users to login", () => {
  renderAt("/", null);
  expect(screen.getByText("login page")).toBeInTheDocument();
});

test("RequirePermission renders children when allowed", () => {
  renderAt("/guarded", userWithRole("admin"), <RequirePermission anyOf={["users.manage"]}><div>secret</div></RequirePermission>);
  expect(screen.getByText("secret")).toBeInTheDocument();
});

test("RequirePermission redirects to the user's home when not allowed", () => {
  renderAt("/guarded", userWithRole("reviewer"), <RequirePermission anyOf={["users.manage"]}><div>secret</div></RequirePermission>);
  expect(screen.getByText("my reviews page")).toBeInTheDocument();
});

test.each([
  ["admin", "dashboard"],
  ["management", "dashboard"],
  ["project_manager", "dashboard"],
  ["reviewer", "my reviews page"],
  ["coordinator", "projects page"],
])("%s lands on %s from /", (role, expected) => {
  renderAt("/", userWithRole(role));
  expect(screen.getByText(expected)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify they fail**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/permissions.test.js src/components/RouteGuards.test.jsx`
Expected: FAIL (the modules don't exist)

- [ ] **Step 3: Implement**

```js
// frontend/src/permissions.js
export const ROLES = ["admin", "management", "coordinator", "reviewer", "project_manager"];

export const ROLE_LABELS = {
  admin: "Admin",
  management: "Management",
  coordinator: "Coordinator",
  reviewer: "Reviewer",
  project_manager: "Project Manager",
};

export function hasPermission(user, permission) {
  return !!user?.permissions?.includes(permission);
}

export function hasAny(user, permissions) {
  return permissions.some((permission) => hasPermission(user, permission));
}

export function initialsFor(user) {
  const source = user?.name?.trim()
    ? user.name.trim().split(/\s+/)
    : (user?.email || "").split("@")[0].split(/[._-]+/);
  return source.filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}
```

```js
// frontend/src/testUtils/authUsers.js
// Test-only mirror of backend/app/auth/permissions.py PERMISSIONS/HOME_PATHS,
// so component tests can build realistic users. Production code reads
// permissions from GET /api/auth/me instead.
const ROLE_PERMISSIONS = {
  admin: [
    "chat.use", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.rename", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.delete", "reviews.edit", "reviews.finalize_own", "settings.manage", "users.manage",
  ],
  management: [
    "chat.use", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.rename", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.edit", "reviews.finalize_own", "settings.manage",
  ],
  coordinator: ["projects.assign_pm", "projects.create", "projects.rename", "projects.view", "reviews.assign_reviewer"],
  reviewer: ["my_reviews.view", "reviews.finalize_own"],
  project_manager: ["chat.use", "dashboard.view_assigned"],
};

const HOME_PATHS = { admin: "/", management: "/", project_manager: "/", reviewer: "/my-reviews", coordinator: "/projects" };

export function userWithRole(role, overrides = {}) {
  return {
    id: `${role}-id`, email: `${role}@example.com`, name: null, role,
    permissions: ROLE_PERMISSIONS[role], home_path: HOME_PATHS[role], ...overrides,
  };
}

export const ADMIN_PERMISSIONS = ROLE_PERMISSIONS.admin;
```

`AuthContext.jsx`: give the default context user the admin permissions and home path, inline (production code must not import from `testUtils`), and add `useCan`:

```jsx
import { hasPermission } from "../permissions";

const DEFAULT_CONTEXT = {
  user: {
    id: "test-admin", email: "test-admin@example.com", name: null, role: "admin", home_path: "/",
    permissions: [
      "chat.use", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
      "projects.delete", "projects.rename", "projects.view", "reviews.assign_reviewer", "reviews.create",
      "reviews.delete", "reviews.edit", "reviews.finalize_own", "settings.manage", "users.manage",
    ],
  },
  loading: false,
  login: async () => {},
  logout: async () => {},
};

// ...AuthProvider unchanged...

export function useCan() {
  const { user } = useAuth();
  return (permission) => hasPermission(user, permission);
}
```

`RouteGuards.jsx`:

```jsx
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasAny } from "../permissions";

export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export function RequirePermission({ anyOf, children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!hasAny(user, anyOf)) return <Navigate to={user.home_path || "/"} replace />;
  return children;
}

// "/" is the dashboard for roles that have one; everyone else goes to their own home.
export function DashboardOrHome({ children }) {
  const { user } = useAuth();
  if (!hasAny(user, ["dashboard.view_all", "dashboard.view_assigned"])) {
    return <Navigate to={user?.home_path && user.home_path !== "/" ? user.home_path : "/login"} replace />;
  }
  return children;
}
```

`api.js`: replace `createUser` and `updateUser`, and add the new functions:

```js
export async function createUser(email, password, role, name) {
  const response = await axios.post(`${API_BASE_URL}/users`, { email, password, role, name: name || null });
  return response.data;
}

export async function updateUser(userId, { role, isActive, password, name } = {}) {
  const body = {};
  if (role !== undefined) body.role = role;
  if (isActive !== undefined) body.is_active = isActive;
  if (password !== undefined) body.password = password;
  if (name !== undefined) body.name = name;
  const response = await axios.patch(`${API_BASE_URL}/users/${userId}`, body);
  return response.data;
}

export async function getMyReviews() {
  const response = await axios.get(`${API_BASE_URL}/my/reviews`);
  return response.data.reviews;
}

export async function getProjectManagers() {
  const response = await axios.get(`${API_BASE_URL}/project-managers`);
  return response.data.managers;
}

export async function setProjectManagers(projectId, userIds) {
  const response = await axios.put(`${API_BASE_URL}/projects/${projectId}/managers`, { user_ids: userIds });
  return response.data;
}

export async function deleteProject(projectId) {
  await axios.delete(`${API_BASE_URL}/projects/${projectId}`);
}
```

Change `AppRoutes.jsx` to stop importing `RequireRole`. The route rewrite comes in Task 9; for now swap the two `RequireRole` usages so the app compiles:

```jsx
<Route path="/settings" element={<RequirePermission anyOf={["settings.manage"]}><SettingsPage /></RequirePermission>} />
<Route path="/users" element={<RequirePermission anyOf={["users.manage"]}><UsersPage /></RequirePermission>} />
```

- [ ] **Step 4: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS (the whole suite)

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: frontend permission helpers, permission-based route guards, new API client calls"
```

---

### Task 8: Shared `AppNav`

**Files:**
- Create: `frontend/src/components/AppNav.jsx`, `frontend/src/components/AppNav.test.jsx`
- Modify: `frontend/src/design-system.css`; `pages/ProjectDashboardPage.jsx`, `pages/ReviewReportPage.jsx`, `pages/UsersPage.jsx`, `pages/SettingsPage.jsx`, `pages/AndroidReviewFlow.jsx`, `pages/PlaceholderReviewFlow.jsx` (replace `TopNav` / inline nav with `<AppNav />`)
- Delete: `components/TopNav.jsx`, `components/TopNav.test.jsx`, `components/NavActions.jsx`, `components/NavActions.test.jsx`

**Interfaces:**
- Consumes: `useAuth`, `hasAny`, `hasPermission`, `initialsFor`, `ROLE_LABELS`.
- Produces: `<AppNav />`, with no props.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/AppNav.test.jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AppNav from "./AppNav";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";

function renderNav(user, path = "/", logout = jest.fn()) {
  render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout }}>
      <MemoryRouter initialEntries={[path]}><AppNav /></MemoryRouter>
    </AuthContext.Provider>
  );
  return { logout };
}

function linkNames() {
  return screen.getAllByRole("link").map((link) => link.textContent);
}

test("brand links to the user's home", () => {
  renderNav(userWithRole("reviewer"));
  expect(screen.getByRole("link", { name: /codeassure/i })).toHaveAttribute("href", "/my-reviews");
});

test.each([
  ["admin", ["Dashboard", "My reviews", "Projects", "Users"]],
  ["management", ["Dashboard", "My reviews", "Projects"]],
  ["coordinator", ["Projects"]],
  ["reviewer", ["My reviews"]],
  ["project_manager", ["Dashboard"]],
])("%s sees the right links", (role, expected) => {
  renderNav(userWithRole(role));
  expect(linkNames().filter((name) => !/codeassure/i.test(name))).toEqual(expected);
});

test("marks the active link", () => {
  renderNav(userWithRole("admin"), "/projects");
  expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
});

test("avatar shows initials, name and role", () => {
  renderNav(userWithRole("management", { name: "Mehrosh Mehboob" }));
  expect(screen.getByText("MM")).toBeInTheDocument();
  expect(screen.getByText("Mehrosh Mehboob")).toBeInTheDocument();
  expect(screen.getByText("Management")).toBeInTheDocument();
});

test("account menu opens, shows permitted items, closes on Escape and returns focus", async () => {
  const user = userEvent.setup();
  renderNav(userWithRole("admin"));
  const trigger = screen.getByRole("button", { name: /account menu/i });
  expect(trigger).toHaveAttribute("aria-expanded", "false");

  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Users" })).toBeInTheDocument();

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("reviewer menu has no Settings or Users, and log out works", async () => {
  const user = userEvent.setup();
  const { logout } = renderNav(userWithRole("reviewer"));
  await user.click(screen.getByRole("button", { name: /account menu/i }));
  expect(screen.queryByRole("menuitem", { name: "Settings" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Log out" }));
  expect(logout).toHaveBeenCalled();
});

test("renders nothing when signed out", () => {
  const { container } = render(
    <AuthContext.Provider value={{ user: null, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><AppNav /></MemoryRouter>
    </AuthContext.Provider>
  );
  expect(container).toBeEmptyDOMElement();
});
```

- [ ] **Step 2: Run and verify it fails**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/components/AppNav.test.jsx`
Expected: FAIL (the module doesn't exist)

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/AppNav.jsx
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasAny, hasPermission, initialsFor, ROLE_LABELS } from "../permissions";

const LINKS = [
  { to: "/", label: "Dashboard", anyOf: ["dashboard.view_all", "dashboard.view_assigned"], end: true },
  { to: "/my-reviews", label: "My reviews", anyOf: ["my_reviews.view"] },
  { to: "/projects", label: "Projects", anyOf: ["projects.view"] },
  { to: "/users", label: "Users", anyOf: ["users.manage"] },
];

export default function AppNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  if (!user) return null;

  const displayName = user.name || user.email;
  const menuItems = [
    hasPermission(user, "settings.manage") && { label: "Settings", to: "/settings" },
    hasPermission(user, "users.manage") && { label: "Users", to: "/users" },
  ].filter(Boolean);

  function go(to) {
    setOpen(false);
    navigate(to);
  }

  return (
    <nav className="app-nav" aria-label="Main">
      <Link to={user.home_path || "/"} className="app-nav-brand">
        <span className="logo-mark" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">CodeAssure</span>
      </Link>

      <div className="app-nav-links">
        {LINKS.filter((link) => hasAny(user, link.anyOf)).map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end} className="app-nav-link">
            {link.label}
          </NavLink>
        ))}
      </div>

      <div ref={containerRef} className="app-nav-account">
        <button
          ref={triggerRef}
          type="button"
          className="app-nav-account-trigger"
          aria-label="Account menu"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <span className="avatar" aria-hidden="true">{initialsFor(user)}</span>
          <span className="app-nav-account-text">
            <span className="app-nav-account-name">{displayName}</span>
            <span className="app-nav-account-role">{ROLE_LABELS[user.role] || user.role}</span>
          </span>
          <span aria-hidden="true" className="app-nav-caret">▾</span>
        </button>
        {open && (
          <div role="menu" className="card elev-md app-nav-menu">
            <div className="app-nav-menu-header">
              <div className="app-nav-account-name">{displayName}</div>
              <div className="app-nav-account-role">{user.email}</div>
            </div>
            {menuItems.map((item) => (
              <button key={item.to} type="button" role="menuitem" className="app-nav-menu-item" onClick={() => go(item.to)}>
                {item.label}
              </button>
            ))}
            <div className="app-nav-menu-divider" role="separator" />
            <button type="button" role="menuitem" className="app-nav-menu-item" onClick={() => { setOpen(false); logout(); }}>
              Log out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
```

Append to `frontend/src/design-system.css`:

```css
/* — app navigation — */
.app-nav {
  position: sticky; top: 0; z-index: 40;
  display: flex; align-items: center; gap: var(--space-5);
  height: 56px; padding: 0 24px;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-divider);
}
.app-nav-brand { display: flex; align-items: center; gap: var(--space-2); text-decoration: none; color: inherit; flex-shrink: 0; }
.app-nav-brand .logo-mark { width: 28px; height: 28px; border-radius: 7px; }
.app-nav-links { display: flex; align-items: stretch; gap: var(--space-1); height: 100%; overflow-x: auto; }
.app-nav-link {
  display: flex; align-items: center; padding: 0 12px;
  font-size: 14px; font-weight: 500; color: var(--color-text-muted); text-decoration: none;
  border-bottom: 2px solid transparent; white-space: nowrap;
}
.app-nav-link:hover { color: var(--color-text); }
.app-nav-link.active { color: var(--color-text); border-bottom-color: var(--color-brand-coral); }
.app-nav-account { position: relative; margin-left: auto; }
.app-nav-account-trigger {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 8px 4px 4px; border-radius: 999px;
  background: none; border: 1px solid transparent; cursor: pointer; color: inherit; font: inherit;
}
.app-nav-account-trigger:hover, .app-nav-account-trigger[aria-expanded="true"] { border-color: var(--color-divider); background: var(--color-surface); }
.app-nav-account-trigger:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
.avatar {
  width: 32px; height: 32px; border-radius: 999px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--color-accent); color: #fff; font-size: 12px; font-weight: 600; letter-spacing: 0.02em;
}
.app-nav-account-text { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.2; text-align: left; }
.app-nav-account-name { font-size: 13px; font-weight: 600; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.app-nav-account-role { font-size: 12px; color: var(--color-text-muted); }
.app-nav-caret { font-size: 11px; color: var(--color-text-muted); }
.app-nav-menu { position: absolute; top: calc(100% + 6px); right: 0; min-width: 240px; padding: 6px; z-index: 50; }
.app-nav-menu-header { padding: 8px 10px 10px; border-bottom: 1px solid var(--color-divider); margin-bottom: 4px; }
.app-nav-menu-item {
  display: block; width: 100%; text-align: left; padding: 8px 10px; border-radius: 6px;
  background: none; border: none; font: inherit; font-size: 14px; color: inherit; cursor: pointer;
}
.app-nav-menu-item:hover, .app-nav-menu-item:focus-visible { background: var(--color-surface); outline: none; }
.app-nav-menu-divider { height: 1px; background: var(--color-divider); margin: 4px 0; }
@media (max-width: 640px) {
  .app-nav { padding: 0 16px; gap: var(--space-3); }
  .app-nav-account-text, .app-nav-caret { display: none; }
}
```

(If `--space-1` or `--space-5` aren't defined in `design-system.css`, check its `:root` and use the nearest tokens that exist.)

Replace the nav in each page:
- `ProjectDashboardPage.jsx`: delete the whole inline `<nav className="nav">…</nav>` block and the `NavActions` import, and put `<AppNav />` in its place.
- `ReviewReportPage.jsx`, `UsersPage.jsx`, `SettingsPage.jsx`, `AndroidReviewFlow.jsx`, `PlaceholderReviewFlow.jsx`: change `import TopNav from "../components/TopNav"` → `import AppNav from "../components/AppNav"`, and `<TopNav />` → `<AppNav />`.

Delete the old components:

```bash
git rm frontend/src/components/TopNav.jsx frontend/src/components/TopNav.test.jsx \
  frontend/src/components/NavActions.jsx frontend/src/components/NavActions.test.jsx
```

- [ ] **Step 4: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS. Any page test that looked up the old nav's "← Home" link or "Users" button must now look up the AppNav link instead.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src
git commit -m "feat: replace TopNav/NavActions with a shared, role-aware AppNav"
```

---

### Task 9: Routes and the My reviews page

**Files:**
- Create: `frontend/src/pages/MyReviewsPage.jsx`, `frontend/src/pages/MyReviewsPage.test.jsx`
- Modify: `frontend/src/AppRoutes.jsx`

**Interfaces:**
- Consumes: `getMyReviews()`, `RequirePermission`, `DashboardOrHome`, `AppNav`.
- Produces: the `/my-reviews` route. `/projects` is wired here to `ProjectsPage`, which Task 10 creates. Create a stub `export default function ProjectsPage() { return null; }` in this task so the routes compile; Task 10 replaces it.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/pages/MyReviewsPage.test.jsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MyReviewsPage from "./MyReviewsPage";
import { getMyReviews } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getMyReviews: jest.fn() }));

const rows = [
  { id: "r1", project_name: "Alpha", platform: "Android", status: "pending_approval", created_at: "2026-05-01T00:00:00Z", total_score_pct: 72.5 },
  { id: "r2", project_name: "Beta", platform: "iOS", status: "approved", created_at: "2026-04-01T00:00:00Z", total_score_pct: 90 },
];

function renderPage() {
  return render(<MemoryRouter><MyReviewsPage /></MemoryRouter>);
}

test("defaults to pending reviews and links to the report", async () => {
  getMyReviews.mockResolvedValue(rows);
  renderPage();
  const table = await screen.findByRole("table");
  expect(within(table).getByText("Alpha")).toBeInTheDocument();
  expect(within(table).queryByText("Beta")).not.toBeInTheDocument();
  expect(within(table).getByRole("link", { name: /open/i })).toHaveAttribute("href", "/reports/r1");
});

test("All shows approved reviews too", async () => {
  const user = userEvent.setup();
  getMyReviews.mockResolvedValue(rows);
  renderPage();
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "All" }));
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("empty state", async () => {
  getMyReviews.mockResolvedValue([]);
  renderPage();
  expect(await screen.findByText("No reviews assigned to you.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify it fails**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/pages/MyReviewsPage.test.jsx`
Expected: FAIL

- [ ] **Step 3: Implement**

```jsx
// frontend/src/pages/MyReviewsPage.jsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import { getMyReviews } from "../services/api";

const STATUS_LABELS = { pending_approval: "Pending approval", approved: "Approved", completed: "Completed", error: "Error" };

export default function MyReviewsPage() {
  const [reviews, setReviews] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("pending");

  useEffect(() => {
    let cancelled = false;
    getMyReviews()
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setError("Failed to load your reviews."); });
    return () => { cancelled = true; };
  }, []);

  const visible = (reviews || []).filter((review) => filter === "all" || review.status !== "approved");

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">My reviews</h1>
            <p className="page-subtitle">Reviews assigned to you for finalization.</p>
          </div>
          <div className="segmented" role="group" aria-label="Filter">
            <button type="button" className={`btn ${filter === "pending" ? "btn-primary" : ""}`} onClick={() => setFilter("pending")}>Pending</button>
            <button type="button" className={`btn ${filter === "all" ? "btn-primary" : ""}`} onClick={() => setFilter("all")}>All</button>
          </div>
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {reviews !== null && visible.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No reviews assigned to you.</p></div>
        )}

        {visible.length > 0 && (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr><th>Project</th><th>Platform</th><th>Date</th><th>AI score</th><th>Status</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {visible.map((review) => (
                  <tr key={review.id}>
                    <td>{review.project_name}</td>
                    <td>{review.platform}</td>
                    <td>{new Date(review.created_at).toLocaleDateString()}</td>
                    <td>{review.total_score_pct ?? "—"}{review.total_score_pct != null && "%"}</td>
                    <td><span className="tag tag-outline">{STATUS_LABELS[review.status] || review.status}</span></td>
                    <td style={{ textAlign: "right" }}><Link className="btn btn-ghost" to={`/reports/${review.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
```

Append shared page-layout classes to `design-system.css`. ProjectsPage and the Users page use these too:

```css
/* — page layout — */
.page { min-height: 100vh; background: var(--color-bg); font-family: var(--font-body); color: var(--color-text); }
.page-main { max-width: 1200px; margin: 0 auto; padding: 32px 24px 96px; display: grid; gap: var(--space-4); }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.page-title { font-family: var(--font-heading); font-weight: var(--font-heading-weight); font-size: 28px; letter-spacing: -0.02em; margin: 0; }
.page-subtitle { margin: 4px 0 0; color: var(--color-text-muted); font-size: 14px; }
.segmented { display: inline-flex; gap: var(--space-2); }
@media (max-width: 640px) { .page-main { padding: 24px 16px 64px; } }
```

Rewrite `frontend/src/AppRoutes.jsx`:

```jsx
import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";
import SettingsPage from "./pages/SettingsPage";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import MyReviewsPage from "./pages/MyReviewsPage";
import ProjectsPage from "./pages/ProjectsPage";
import { DashboardOrHome, RequireAuth, RequirePermission } from "./components/RouteGuards";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><DashboardOrHome><ProjectDashboardPage /></DashboardOrHome></RequireAuth>} />
      <Route path="/review/:platform" element={<RequirePermission anyOf={["reviews.create"]}><ReviewPage /></RequirePermission>} />
      <Route path="/reports/:reviewId" element={<RequireAuth><ReviewReportPage /></RequireAuth>} />
      <Route path="/my-reviews" element={<RequirePermission anyOf={["my_reviews.view"]}><MyReviewsPage /></RequirePermission>} />
      <Route path="/projects" element={<RequirePermission anyOf={["projects.view"]}><ProjectsPage /></RequirePermission>} />
      <Route path="/settings" element={<RequirePermission anyOf={["settings.manage"]}><SettingsPage /></RequirePermission>} />
      <Route path="/users" element={<RequirePermission anyOf={["users.manage"]}><UsersPage /></RequirePermission>} />
    </Routes>
  );
}
```

Create the temporary stub `frontend/src/pages/ProjectsPage.jsx` with `export default function ProjectsPage() { return null; }`.

- [ ] **Step 4: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: add My reviews page and permission-guarded routes"
```

---

### Task 10: Projects page (create, rename, assign PMs, guarded delete)

**Files:**
- Create: `frontend/src/components/MultiSelect.jsx` and test, `frontend/src/components/AssignManagersDialog.jsx` and test, `frontend/src/pages/ProjectsPage.jsx` (replacing the stub) and test
- Modify: `frontend/src/components/ProjectDialog.jsx` only if needed (it already takes `title`, `initialName`, `submitLabel`, `onSubmit`, `onClose`, so no change is expected)

**Interfaces:**
- Consumes:
  - `getProjects()`, which returns rows with `manager_ids` and `review_count`
  - `createProject(name)`, `updateProject(id, name)`, `getProjectManagers()`
  - `setProjectManagers(id, userIds)`, `deleteProject(id)`, `useCan()`
- Produces:
  - `<MultiSelect ariaLabel options={[{value,label}]} values={[...]} onChange={(values)=>...} placeholder />`
  - `<AssignManagersDialog project managers onSaved onClose />`

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/components/MultiSelect.test.jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import MultiSelect from "./MultiSelect";

const options = [{ value: "a", label: "Alice" }, { value: "b", label: "Bob" }, { value: "c", label: "Cara" }];

function Harness({ initial = [] }) {
  const [values, setValues] = useState(initial);
  return <MultiSelect ariaLabel="Managers" options={options} values={values} onChange={setValues} />;
}

test("shows chips for selected values and removes them", async () => {
  const user = userEvent.setup();
  render(<Harness initial={["a"]} />);
  expect(screen.getByText("Alice")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remove Alice" }));
  expect(screen.queryByRole("button", { name: "Remove Alice" })).not.toBeInTheDocument();
});

test("filters and toggles options with checkboxes", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Managers" }));
  await user.type(screen.getByRole("textbox", { name: "Search Managers" }), "bo");
  expect(screen.queryByRole("checkbox", { name: "Alice" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", { name: "Bob" }));
  expect(screen.getByRole("button", { name: "Remove Bob" })).toBeInTheDocument();
});
```

```jsx
// frontend/src/pages/ProjectsPage.test.jsx
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectsPage from "./ProjectsPage";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getProjects, createProject, updateProject, getProjectManagers, setProjectManagers, deleteProject } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getProjects: jest.fn(), createProject: jest.fn(), updateProject: jest.fn(),
  getProjectManagers: jest.fn(), setProjectManagers: jest.fn(), deleteProject: jest.fn(),
}));

const projects = [
  { id: "p1", name: "Alpha", created_at: "2026-01-01T00:00:00Z", review_count: 3, manager_ids: ["pm1"] },
  { id: "p2", name: "Beta", created_at: "2026-02-01T00:00:00Z", review_count: 0, manager_ids: [] },
];
const managers = [{ id: "pm1", email: "pat@example.com", name: "Pat" }, { id: "pm2", email: "sam@example.com", name: null }];

beforeEach(() => {
  jest.resetAllMocks();
  getProjects.mockResolvedValue(projects);
  getProjectManagers.mockResolvedValue(managers);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><ProjectsPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

function row(name) {
  return screen.getByRole("row", { name: new RegExp(name) });
}

test("lists projects with PM chips and review counts", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByText("Pat")).toBeInTheDocument();
  expect(within(row("Alpha")).getByText("3")).toBeInTheDocument();
});

test("coordinator does not see Delete", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
});

test("delete is disabled when a project has reviews", async () => {
  renderAs("management");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByRole("button", { name: "Delete Alpha" })).toBeDisabled();
  expect(within(row("Alpha")).getByRole("button", { name: "Delete Alpha" })).toHaveAttribute("title", "Has 3 reviews — can't be deleted");
});

test("deleting an empty project after confirmation", async () => {
  const user = userEvent.setup();
  deleteProject.mockResolvedValue();
  renderAs("admin");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Delete Beta" }));
  await user.click(screen.getByRole("button", { name: "Delete project" }));
  await waitFor(() => expect(deleteProject).toHaveBeenCalledWith("p2"));
  await waitFor(() => expect(screen.queryByText("Beta")).not.toBeInTheDocument());
});

test("creating a project", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, manager_ids: [] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(screen.getByRole("button", { name: "New project" }));
  await user.type(screen.getByLabelText("Project name"), "Gamma");
  await user.click(screen.getByRole("button", { name: "Create" }));
  expect(await screen.findByText("Gamma")).toBeInTheDocument();
});

test("renaming a project", async () => {
  const user = userEvent.setup();
  updateProject.mockResolvedValue({ ...projects[1], name: "Beta 2" });
  renderAs("coordinator");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Rename Beta" }));
  const input = screen.getByLabelText("Project name");
  await user.clear(input);
  await user.type(input, "Beta 2");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Beta 2")).toBeInTheDocument();
});

test("assigning PMs saves the selected ids", async () => {
  const user = userEvent.setup();
  setProjectManagers.mockResolvedValue({ ...projects[1], manager_ids: ["pm2"] });
  renderAs("coordinator");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Assign PMs for Beta" }));
  await user.click(screen.getByRole("button", { name: "Project managers" }));
  await user.click(screen.getByRole("checkbox", { name: "sam@example.com" }));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setProjectManagers).toHaveBeenCalledWith("p2", ["pm2"]));
  expect(await within(row("Beta")).findByText("sam@example.com")).toBeInTheDocument();
});

test("search filters the table", async () => {
  const user = userEvent.setup();
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.type(screen.getByRole("searchbox", { name: "Search projects" }), "bet");
  expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify they fail**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/components/MultiSelect.test.jsx src/pages/ProjectsPage.test.jsx`
Expected: FAIL

- [ ] **Step 3: Implement `MultiSelect`**

```jsx
// frontend/src/components/MultiSelect.jsx
import { useEffect, useRef, useState } from "react";

export default function MultiSelect({ ariaLabel, options, values, onChange, placeholder = "Select…" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = options.filter((option) => values.includes(option.value));
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));

  function toggle(value) {
    onChange(values.includes(value) ? values.filter((v) => v !== value) : [...values, value]);
  }

  return (
    <div ref={containerRef} style={{ position: "relative", display: "grid", gap: 8 }}>
      {selected.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {selected.map((option) => (
            <span key={option.value} className="tag tag-outline" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {option.label}
              <button
                type="button" aria-label={`Remove ${option.label}`} onClick={() => toggle(option.value)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, lineHeight: 1, color: "inherit" }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <button
        type="button" className="input" aria-label={ariaLabel} aria-expanded={open}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer", width: "100%" }}
        onClick={() => { setOpen((current) => !current); setQuery(""); }}
      >
        <span style={{ color: "var(--color-text-muted)" }}>{selected.length ? `${selected.length} selected` : placeholder}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="card elev-md" style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 60, padding: 8, marginTop: 4, maxHeight: 280, display: "flex", flexDirection: "column" }}>
          <input
            type="text" className="input" aria-label={`Search ${ariaLabel}`} placeholder="Search…"
            value={query} autoFocus onChange={(event) => setQuery(event.target.value)}
          />
          <div style={{ overflowY: "auto", marginTop: 8 }}>
            {filtered.length === 0 && <p className="card-body" style={{ padding: "8px 4px" }}>No matches</p>}
            {filtered.map((option) => (
              <label key={option.value} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px", cursor: "pointer", fontSize: 14 }}>
                <input type="checkbox" checked={values.includes(option.value)} onChange={() => toggle(option.value)} />
                {option.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Implement `AssignManagersDialog`**

```jsx
// frontend/src/components/AssignManagersDialog.jsx
import { useState } from "react";
import MultiSelect from "./MultiSelect";
import { setProjectManagers } from "../services/api";

export function managerLabel(manager) {
  return manager.name || manager.email;
}

export default function AssignManagersDialog({ project, managers, onSaved, onClose }) {
  const [values, setValues] = useState(project.manager_ids || []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onSaved(await setProjectManagers(project.id, values));
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save project managers");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Assign project managers — {project.name}</div>
        <div className="dialog-body">
          {managers.length === 0 ? (
            <p className="card-body">No Project Manager accounts exist yet. An admin can create them on the Users page.</p>
          ) : (
            <div className="field">
              <label>Project managers</label>
              <MultiSelect
                ariaLabel="Project managers"
                options={managers.map((manager) => ({ value: manager.id, label: managerLabel(manager) }))}
                values={values}
                onChange={setValues}
                placeholder="Choose project managers…"
              />
            </div>
          )}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}
```

(Check `ProjectDialog.jsx` for the actual class name of the footer container. If it isn't `dialog-actions`, use the class it uses.)

- [ ] **Step 5: Implement `ProjectsPage`**

```jsx
// frontend/src/pages/ProjectsPage.jsx
import { useEffect, useMemo, useState } from "react";
import AppNav from "../components/AppNav";
import ProjectDialog from "../components/ProjectDialog";
import AssignManagersDialog, { managerLabel } from "../components/AssignManagersDialog";
import { useCan } from "../context/AuthContext";
import { createProject, deleteProject, getProjectManagers, getProjects, updateProject } from "../services/api";

export default function ProjectsPage() {
  const can = useCan();
  const [projects, setProjects] = useState(null);
  const [managers, setManagers] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getProjects()
      .then((result) => { if (!cancelled) setProjects(result); })
      .catch(() => { if (!cancelled) setError("Failed to load projects."); });
    if (can("projects.assign_pm")) {
      getProjectManagers().then((result) => { if (!cancelled) setManagers(result); }).catch(() => {});
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const managersById = useMemo(() => Object.fromEntries(managers.map((m) => [m.id, m])), [managers]);
  const visible = (projects || []).filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));

  function replaceProject(updated) {
    setProjects((current) => current.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
  }

  async function handleDelete() {
    setDeleteError("");
    try {
      await deleteProject(deleting.id);
      setProjects((current) => current.filter((p) => p.id !== deleting.id));
      setDeleting(null);
    } catch (err) {
      setDeleteError(err.response?.data?.detail || "Failed to delete project");
    }
  }

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Projects</h1>
            <p className="page-subtitle">Create projects and assign the project managers who can see their scores.</p>
          </div>
          {can("projects.create") && (
            <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>New project</button>
          )}
        </header>

        <input
          type="search" className="input" aria-label="Search projects" placeholder="Search projects…"
          value={query} onChange={(event) => setQuery(event.target.value)} style={{ maxWidth: 360 }}
        />

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {projects !== null && visible.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No projects found.</p></div>
        )}

        {visible.length > 0 && (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr><th>Project</th><th>Project managers</th><th>Reviews</th><th>Created</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {visible.map((project) => (
                  <tr key={project.id}>
                    <td style={{ fontWeight: 600 }}>{project.name}</td>
                    <td>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(project.manager_ids || []).length === 0 && <span style={{ color: "var(--color-text-muted)" }}>—</span>}
                        {(project.manager_ids || []).map((id) => (
                          <span key={id} className="tag tag-outline">{managersById[id] ? managerLabel(managersById[id]) : id}</span>
                        ))}
                      </div>
                    </td>
                    <td>{project.review_count}</td>
                    <td>{new Date(project.created_at).toLocaleDateString()}</td>
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      {can("projects.rename") && (
                        <button type="button" className="btn btn-ghost" aria-label={`Rename ${project.name}`} onClick={() => setRenaming(project)}>Rename</button>
                      )}
                      {can("projects.assign_pm") && (
                        <button type="button" className="btn btn-ghost" aria-label={`Assign PMs for ${project.name}`} onClick={() => setAssigning(project)}>Assign PMs</button>
                      )}
                      {can("projects.delete") && (
                        <button
                          type="button" className="btn btn-ghost" style={{ color: "var(--color-brand-coral)" }}
                          aria-label={`Delete ${project.name}`}
                          disabled={project.review_count > 0}
                          title={project.review_count > 0 ? `Has ${project.review_count} reviews — can't be deleted` : undefined}
                          onClick={() => { setDeleteError(""); setDeleting(project); }}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {creating && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create"
          onSubmit={async (name) => { const project = await createProject(name); setProjects((current) => [project, ...(current || [])]); }}
          onClose={() => setCreating(false)}
        />
      )}
      {renaming && (
        <ProjectDialog
          title="Rename project" initialName={renaming.name} submitLabel="Save"
          onSubmit={async (name) => replaceProject(await updateProject(renaming.id, name))}
          onClose={() => setRenaming(null)}
        />
      )}
      {assigning && (
        <AssignManagersDialog project={assigning} managers={managers} onSaved={replaceProject} onClose={() => setAssigning(null)} />
      )}
      {deleting && (
        <div className="dialog-backdrop" onClick={() => setDeleting(null)}>
          <div className="dialog" role="dialog" aria-label="Delete project" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Delete {deleting.name}?</div>
            <div className="dialog-body">
              <p className="card-body">This permanently removes the project and its PM assignments.</p>
              {deleteError && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{deleteError}</p>}
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setDeleting(null)}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={handleDelete}>Delete project</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

Note: `replaceProject` merges into the existing row, because the rename response doesn't include `manager_ids`.

- [ ] **Step 6: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: add Projects page with PM assignment and guarded delete"
```

---

### Task 11: Gate the dashboard, report page and upload form by permission

**Files:**
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx`, `frontend/src/components/DashboardFilters.jsx`, `frontend/src/pages/ReviewReportPage.jsx`, `frontend/src/components/UploadForm.jsx`
- Test: extend `ProjectDashboardPage.test.jsx`, `DashboardFilters.test.jsx` and `ReviewReportPage.test.jsx`

**Interfaces:**
- Consumes: `useCan()`, `useAuth()`, `userWithRole()`.

- [ ] **Step 1: Write the failing tests**

Add to `ProjectDashboardPage.test.jsx`. Keep its existing api mocks, and add `AuthContext` and `userWithRole` imports:

```jsx
function renderAsPm(projects) {
  getProjects.mockResolvedValue(projects);
  return render(
    <AuthContext.Provider value={{ user: userWithRole("project_manager"), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><ProjectDashboardPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

test("PM does not see start/upload actions", async () => {
  renderAsPm([{ id: "p1", name: "Alpha", created_at: "2026-01-01T00:00:00Z", review_count: 0 }]);
  await screen.findByText(/filter review history/i);
  expect(screen.queryByRole("button", { name: "Start review" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Upload review" })).not.toBeInTheDocument();
});

test("shows the unassigned message for a PM with no projects", async () => {
  renderAsPm([]);
  expect(await screen.findByText("No projects assigned yet — contact your admin.")).toBeInTheDocument();
});
```

(Match the existing mock names for `getProjects`, `getReviews` and `getReviewYears` in that test file. `getReviewYears` should resolve `[]` for the PM tests.)

Add to `DashboardFilters.test.jsx`:

```jsx
test("PM sees no rename or add-project controls", async () => {
  const user = userEvent.setup();
  render(
    <AuthContext.Provider value={{ user: userWithRole("project_manager"), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <DashboardFilters {...baseProps} projectId="p1" projects={[{ id: "p1", name: "Alpha" }]} />
    </AuthContext.Provider>
  );
  expect(screen.queryByRole("button", { name: /rename alpha/i })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Project" }));
  expect(screen.queryByText("+ Add new project")).not.toBeInTheDocument();
});
```

(Use the file's existing default-props object. If it has none, pass the same props its other tests pass.)

Add to `ReviewReportPage.test.jsx`, reusing its existing review fixture and `getReview` mock:

```jsx
function renderReportAs(user, review) {
  getReview.mockResolvedValue(review);
  return render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter initialEntries={[`/reports/${review.id}`]}>
        <Routes><Route path="/reports/:reviewId" element={<ReviewReportPage />} /></Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

test("assigned reviewer can edit but cannot reassign or delete", async () => {
  const reviewer = userWithRole("reviewer", { id: "rev" });
  renderReportAs(reviewer, { ...baseReview, reviewer_id: "rev" });
  await screen.findByText(baseReview.project_name);
  expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  expect(screen.queryByLabelText("Reviewer")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /delete review/i })).not.toBeInTheDocument();
  expect(getReviewers).not.toHaveBeenCalled();
});

test("PM sees the report read-only", async () => {
  renderReportAs(userWithRole("project_manager"), { ...baseReview, reviewer_id: "someone" });
  await screen.findByText(baseReview.project_name);
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
});
```

(Replace `baseReview` with the completed-review fixture the file already uses. Replace `/approve/i` with the accessible name of the approve/edit control that `canApprove` currently shows.)

- [ ] **Step 2: Run and verify they fail**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/pages/ProjectDashboardPage.test.jsx src/components/DashboardFilters.test.jsx src/pages/ReviewReportPage.test.jsx`
Expected: FAIL

- [ ] **Step 3: Implement**

`ProjectDashboardPage.jsx`:
- Add `import { useCan } from "../context/AuthContext";`, and `const can = useCan();` inside the component.
- Wrap the action buttons:

```jsx
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            {can("reviews.create") && (
              <>
                <button type="button" className="btn" onClick={() => setUploadReviewOpen(true)}>Upload review</button>
                <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
              </>
            )}
          </div>
```

- Directly after the `<header>`, before `<DashboardFilters …/>`, add the unassigned message. Then render the filters and results only when it isn't shown:

```jsx
        {can("dashboard.view_assigned") && projects.length === 0 && projectsLoaded ? (
          <div className="card" style={{ padding: 20 }}>
            <p className="card-body">No projects assigned yet — contact your admin.</p>
          </div>
        ) : (
          <>
            {/* existing <DashboardFilters …/> and the reviews block, unchanged */}
          </>
        )}
```

- Add a `projectsLoaded` boolean state. Set it to `true` in the existing `getProjects()` `.then`, next to where `setProjects` is called.
- Render `{can("chat.use") && <ChatWidget />}` in place of `<ChatWidget />`.
- Render the start and upload dialogs only when `can("reviews.create")`.

`DashboardFilters.jsx`:
- Replace `const isAdmin = user?.role === "admin";` with:

```jsx
  const canRename = hasPermission(user, "projects.rename");
  const canCreate = hasPermission(user, "projects.create");
```

- Import `hasPermission` from `"../permissions"`.
- Change `selectedProject && isAdmin` to `selectedProject && canRename`.
- On the Project `SearchableSelect`, pass `onAddNew={canCreate ? () => setShowCreateDialog(true) : undefined}` and `addNewLabel` as before.

`ReviewReportPage.jsx`:
- Import `hasPermission` from `"../permissions"`.
- Replace the `canApprove` logic:

```jsx
  const { user } = useAuth();
  const isAssignedReviewer = !!review && !!user && review.reviewer_id === user.id;
  const canEditReview = hasPermission(user, "reviews.edit") || (hasPermission(user, "reviews.finalize_own") && isAssignedReviewer);
  const canAssignReviewer = hasPermission(user, "reviews.assign_reviewer");
  const canApprove = review && review.status !== "error" && review.category_scores.length > 0 && canEditReview;
```

- Wrap the `getReviewers()` effect body in `if (!canAssignReviewer) return undefined;`. Add `canAssignReviewer` to its dependency list. Because `user` comes from context and `useAuth()` is called before the effect, move the `const { user } = useAuth();` line, and the `canAssignReviewer` line that depends on it, above the effects.
- Render the "Reviewer" card (the `card-kicker` "Reviewer" block) only when `canAssignReviewer`.
- Change `user && user.role === "admin"` on Delete to `hasPermission(user, "reviews.delete")`.

`UploadForm.jsx`:
- `const canAdjustClauses = hasPermission(user, "reviews.create");`, importing `hasPermission`.

- [ ] **Step 4: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: gate dashboard, report and upload actions by permission; PM empty state"
```

---

### Task 12: Users page (five roles, names, PM project chips)

**Files:**
- Modify: `frontend/src/pages/UsersPage.jsx`, `frontend/src/pages/UsersPage.test.jsx`

**Interfaces:**
- Consumes:
  - `ROLES`, `ROLE_LABELS`
  - `listUsers()`, which returns rows with `name` and `project_ids`
  - `createUser(email, password, role, name)`, `updateUser(id, { name })`, `getProjects()`

- [ ] **Step 1: Write the failing tests**

Add to `UsersPage.test.jsx`. Also add `getProjects: jest.fn()` to the mock, and in `beforeEach` add `getProjects.mockResolvedValue([{ id: "p1", name: "Alpha" }])`. Replace the `users` fixture with:

```jsx
const users = [
  { id: "u1", email: "admin@example.com", name: "Ada Admin", role: "admin", is_active: true },
  { id: "u2", email: "reviewer@example.com", name: null, role: "reviewer", is_active: true },
  { id: "u3", email: "pm@example.com", name: null, role: "project_manager", is_active: true, project_ids: ["p1"] },
];
```

```jsx
test("role dropdown offers all five roles with labels", async () => {
  renderPage();
  await screen.findByText("reviewer@example.com");
  const select = screen.getByLabelText(/role for reviewer@example\.com/i);
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(
    ["Admin", "Management", "Coordinator", "Reviewer", "Project Manager"],
  );
});

test("PM rows show assigned projects as links to the Projects page", async () => {
  renderPage();
  const chip = await screen.findByRole("link", { name: "Alpha" });
  expect(chip).toHaveAttribute("href", "/projects");
});

test("creating a user sends the name", async () => {
  const user = userEvent.setup();
  createUser.mockResolvedValue({ id: "u9", email: "new@example.com", name: "Nia", role: "coordinator", is_active: true });
  renderPage();
  await screen.findByText("admin@example.com");
  await user.type(screen.getByLabelText(/^name$/i), "Nia");
  await user.type(screen.getByLabelText(/^email$/i), "new@example.com");
  await user.type(screen.getByLabelText(/^password$/i), "longenough");
  await user.selectOptions(screen.getByLabelText(/^role$/i), "coordinator");
  await user.click(screen.getByRole("button", { name: /create user/i }));
  await waitFor(() => expect(createUser).toHaveBeenCalledWith("new@example.com", "longenough", "coordinator", "Nia"));
});

test("editing a name saves on blur", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], name: "Rae" });
  renderPage();
  const input = await screen.findByLabelText(/name for reviewer@example\.com/i);
  await user.type(input, "Rae");
  await user.tab();
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { name: "Rae" }));
});
```

(Change the accessible label text above to match the create form's existing labels: look up the email, password and role fields' `htmlFor` and label text in `UsersPage.jsx`, and keep the submit button's existing name. Update any existing test that expected a `"user"` role option or default.)

- [ ] **Step 2: Run and verify they fail**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false src/pages/UsersPage.test.jsx`
Expected: FAIL

- [ ] **Step 3: Implement in `UsersPage.jsx`**

- Import `ROLES` and `ROLE_LABELS` from `"../permissions"`, `getProjects` from the api, and `Link` from `react-router-dom`.
- Create form:
  - The default role becomes `useState("reviewer")`.
  - Add a Name field before Email: `<label htmlFor="newUserName">Name</label><input id="newUserName" className="input" value={name} onChange={(e) => setName(e.target.value)} />`.
  - `onSubmit(email, password, role, name)` replaces the existing three-argument call.
  - The role `<select>` options become `{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}`.
- `handleCreate(email, password, role, name)` calls `createUser(email, password, role, name)`.
- Table:
  - Add a **Name** column first, with an input: `aria-label={\`Name for ${u.email}\`}`, `defaultValue={u.name || ""}`, `onBlur={(e) => { if ((e.target.value.trim() || null) !== (u.name || null)) handleNameChange(u.id, e.target.value); }}`.
  - `handleNameChange` calls `updateUser(id, { name })` and replaces the row with the result. On failure it shows the existing error banner.
  - The role select per row uses the same `ROLES` / `ROLE_LABELS` options.
  - Add a **Projects** column. For `u.role === "project_manager"`, render `(u.project_ids || []).map((id) => <Link key={id} to="/projects" className="tag tag-outline">{projectNames[id] || id}</Link>)`, or `—` when empty. For other roles, render `—`.
- Load project names once: `getProjects().then((ps) => setProjectNames(Object.fromEntries(ps.map((p) => [p.id, p.name])))).catch(() => {})`.
- Layout: wrap the page in `<div className="page"><AppNav /><main className="page-main">…`, using `page-header` / `page-title` for the heading. Wrap the table in `<div className="card" style={{ padding: 0, overflowX: "auto" }}>`, so the columns line up and scroll on narrow screens instead of overflowing.

- [ ] **Step 4: Run and verify they pass**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: users page supports five roles, names, and shows PM project assignments"
```

---

### Task 13: Docker smoke test, rollout notes, progress log

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: Run both suites in full**

Run: `cd backend && python -m pytest -q`, then `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all pass. Record the counts.

- [ ] **Step 2: Rebuild and migrate**

```bash
docker compose up -d --build backend frontend
docker compose logs backend --tail 30   # expect "Running upgrade a1b2c3d4e5f6 -> b7c8d9e0f1a2"
```

- [ ] **Step 3: Read the current data before writing anything**

```bash
docker compose exec postgres psql -U postgres -d code_reviews -c "select email, role, name from users order by created_at;"
docker compose exec postgres psql -U postgres -d code_reviews -c "select count(*) from project_managers;"
```

(Check the actual DB user and name in `docker-compose.yml` before running these.) Confirm that former `user` accounts now show `project_manager`, and that no other rows changed.

- [ ] **Step 4: Check each role by hand in the browser**

- Using an admin login, create one test account per new role, named `smoke-<role>@example.com`. Create a project `Smoke Project` and assign `smoke-project_manager` to it.
- Sign in as each role and confirm:

| Role | Lands on | Expected |
|---|---|---|
| admin | Dashboard | All links shown |
| management | Dashboard | No Users link |
| coordinator | Projects | No Delete button |
| reviewer | My reviews | — |
| project_manager | Dashboard | Only Smoke Project's data, no Start/Upload |

- Confirm the navbar is aligned at full width and at ~400px (Chrome device toolbar).

- [ ] **Step 5: Clean up the smoke data**

Delete the `smoke-*` users and `Smoke Project` through the UI.

- [ ] **Step 6: Update `progress.md`**

Under Phase 7, or a new "Phase 8: Roles & access (2026-10-07)", add:
- The five roles.
- The Projects page.
- PM scoping.
- My reviews.
- The shared navbar.
- The rollout note: **"Existing reviewer accounts lose the dashboard and Settings — move anyone who needs them to Management before deploying."**

Update "Last updated".

- [ ] **Step 7: Commit**

```bash
git add progress.md
git commit -m "docs: log roles & access work and rollout note in progress.md"
```
