# Automated Cycle Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- PMs submit a DevOps URL for each platform of a started cycle.
- A single database-backed worker runs those reviews with the org PAT and org defaults.
- Failures are recorded and admins notified (via an outbox).
- Coordinators can change reviewers, retry and re-run.

**Architecture:**
- **Queue and progress:** run state lives on `review_cycle_assignments`. A lifespan-started worker (`app/automation/worker.py`, enabled by `REVIEW_WORKER_ENABLED=true`) claims the oldest `queued` row and awaits the existing `_run_review` pipeline in the same process, copying its in-memory progress back to the row.
- **Endpoints:** new endpoints live in `app/api/cycles.py`.
- **Notifications:** go through `app/automation/notify.py` into `notification_outbox`.
- **PAT:** encrypted with Fernet (`app/secrets.py`).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, `cryptography` (Fernet), pytest; React 18, Jest + RTL.

**Spec:** `docs/superpowers/specs/2026-10-07-automated-cycle-reviews-design.md`

## Global Constraints

- **`run_status` values:** exactly `waiting_for_url`, `queued`, `running`, `completed`, `failed`.
- **`failure_kind` values:** exactly `url` or `system`.
  - **`url`:** fetch `invalid_url` / `not_found`, and analyzer `fatal_error`.
  - **`system`:** everything else, including fetch `unauthorized`, a missing PAT and a missing template.
- **Capabilities:**
  - `cycles.submit_urls`: admin, management, coordinator, project_manager.
  - `settings.devops_pat`: admin.
- **Default compile modes:** `{"Android": "compiler", ".NET": "compiler", "iOS": "static"}`.
- **Allowed compile modes:** Android `compiler|local|static`; .NET `compiler|static`; iOS `compiler|static`.
- **Outbox events:** `cycle_initiated`, `reviewer_assigned`, `reviewer_unassigned`, `review_ready`, `review_failed`, `review_finalized`. Inactive recipients are skipped.
- **The PAT is never returned or logged.** `SETTINGS_ENCRYPTION_KEY` takes priority. Otherwise the key is derived from `AUTH_SECRET_KEY` (default `dev-insecure-secret-key`).
- **The worker never starts in tests.** It is only started when `REVIEW_WORKER_ENABLED == "true"`.
- **Error copy:**
  - 409 on URL save: `This platform's review is already queued, running or completed.`
  - 409 on re-run: `Only a completed review that isn't approved yet can be re-run.`
  - 409 on retry: `Only a failed review can be retried.`
  - 409 on reviewer change once approved: `This review is already approved; its reviewer can't change.`
  - Missing PAT: `No usable Azure DevOps PAT is configured in Settings.`
- **Commands:**
  - Backend: `cd backend && venv/bin/python -m pytest -q`.
  - Frontend: `cd frontend && CI=true npx react-scripts test --watchAll=false`.
- **Commits:** every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Backend restart mid-run:** the assignment left `running` is re-queued on worker start, not stuck forever. *Task 6 `test_recover_requeues_running_and_system_failures_only`.*
2. **Failed run:** must never count as coverage, and must notify every active admin, but not inactive ones. *Task 6 `test_url_failure_records_error_and_notifies_admins`.*
3. **A PM tries to submit a URL** for a project they aren't assigned to: 404. *Task 5 `test_pm_cannot_touch_other_projects_cycles`.*
4. **Reviewer changed after the automatic review finished:** the review moves to the new reviewer's My reviews. Once approved, the reviewer can't change. *Task 5 `test_reviewer_change_moves_finished_review_and_notifies` and `test_reviewer_change_blocked_after_approval`.*
5. **PAT mistakes:** a corrupted or rotated encryption key fails as `system` with a clear message, not a crash. The PAT never appears in any API response. *Task 1 `test_decrypt_with_wrong_key_returns_none` and Task 4 `test_pat_is_never_returned`.*

---

### Task 1: Capabilities and secret encryption

**Files:**
- Modify: `backend/app/auth/permissions.py`, `backend/tests/test_permissions.py`, `backend/requirements.txt`
- Create: `backend/app/secrets.py`, `backend/tests/test_secrets.py`

**Interfaces:**
- Produces: `encrypt(plaintext: str) -> str`, `decrypt(token: str | None) -> str | None`, plus the capabilities `cycles.submit_urls` and `settings.devops_pat`.

- [ ] **Step 1: Write the failing tests.**
  - In `test_permissions.py`, add to `EXPECTED`: `"cycles.submit_urls": {A, M, C, P},` and `"settings.devops_pat": {A},`.
  - Create:

```python
# backend/tests/test_secrets.py
from cryptography.fernet import Fernet

from app.secrets import decrypt, encrypt


def test_roundtrip_with_explicit_key(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt("my-pat-value")
    assert token != "my-pat-value"
    assert decrypt(token) == "my-pat-value"


def test_roundtrip_with_key_derived_from_auth_secret(monkeypatch):
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("AUTH_SECRET_KEY", "some-secret")
    assert decrypt(encrypt("abc")) == "abc"


def test_decrypt_with_wrong_key_returns_none(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt("abc")
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert decrypt(token) is None


def test_decrypt_none_or_garbage_returns_none():
    assert decrypt(None) is None
    assert decrypt("not-a-token") is None
```

- [ ] **Step 2: Run and verify they fail.** `venv/bin/python -m pytest tests/test_secrets.py tests/test_permissions.py -q` should FAIL.
- [ ] **Step 3: Implement.**
  - In `permissions.py`, add `"cycles.submit_urls": frozenset({ADMIN, MANAGEMENT, COORDINATOR, PROJECT_MANAGER}),` and `"settings.devops_pat": frozenset({ADMIN}),`.
  - Add the line `cryptography==50.0.1` to `requirements.txt`.

```python
# backend/app/secrets.py
"""Symmetric encryption for secrets stored in the database (e.g. the org DevOps PAT).

Uses SETTINGS_ENCRYPTION_KEY (a Fernet key) when set, otherwise a key derived
from AUTH_SECRET_KEY -- changing either makes previously stored secrets
unreadable, which decrypt() reports as None rather than raising.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if not key:
        secret = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-key")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
```

- [ ] **Step 4: Run and verify they pass.** Run the same command; expected PASS.
- [ ] **Step 5: Commit** with the message `feat: add cycle URL and DevOps PAT capabilities and secret encryption`.

---

### Task 2: Data model, migration, crud, notifications helper

**Files:**
- Modify: `backend/app/db/models.py`, `backend/app/db/crud.py`
- Create:
  - `backend/alembic/versions/d4e5f6a7b8c9_automated_cycle_reviews.py`
  - `backend/app/automation/__init__.py` (empty), `backend/app/automation/notify.py`, `backend/app/automation/config.py`, `backend/app/automation/assignments.py`
  - `backend/tests/test_db_automation.py`

**Interfaces:**
- Produces, crud:
  - `get_cycle_by_id`, `get_assignment(session, cycle_id, platform)`
  - `update_assignment(session, assignment, **fields)`
  - `list_queued_keys(session) -> list[tuple[str, str]]`
  - `claim_next_queued(session)`
  - `requeue_assignments(session, include_running: bool) -> int`
  - `get_review_statuses(session, review_ids) -> dict`
  - `list_open_cycles(session, project_ids: set | None)`
  - `get_assignment_by_review_id(session, review_id)`
  - `add_notifications(session, event, recipient_ids, payload)`
  - `list_notifications(session, event=None)`
  - `list_active_user_ids_with_roles(session, roles)`
  - `update_devops_pat(session, encrypted, last4, user_id)`
  - `update_auto_compile_modes(session, modes)`
- Produces, helper modules:
  - `notify.notify(session, event, user_ids, payload)`, `notify.project_manager_ids(session, project_id)`, `notify.admin_ids(session)`, `notify.cycle_payload(...)`
  - `config.DEFAULT_COMPILE_MODES`, `config.ALLOWED_COMPILE_MODES`, `config.effective_compile_modes(stored)`
  - `assignments.assignment_dicts(session, assignments) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db_automation.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.automation.config import effective_compile_modes
from app.automation.notify import admin_ids, notify, project_manager_ids
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def s():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await crud.create_project(session, "p1", "Alpha")
        await crud.create_user(session, "rev", "rev@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(session, "adm", "adm@example.com", "h", "admin")
        await crud.create_user(session, "adm2", "adm2@example.com", "h", "admin")
        await crud.update_user(session, "adm2", is_active=False)
        await crud.create_user(session, "pm", "pm@example.com", "h", "project_manager")
        await crud.set_managers_for_project(session, "p1", ["pm"])
        await crud.create_cycle(session, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        yield session
    await engine.dispose()


async def test_new_assignments_wait_for_url(s):
    a = await crud.get_assignment(s, "c1", "Android")
    assert a.run_status == "waiting_for_url" and a.attempts == 0


async def test_queue_order_claim_and_requeue(s):
    now = datetime.now(timezone.utc)
    android = await crud.get_assignment(s, "c1", "Android")
    ios = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, ios, run_status="queued", queued_at=now)
    await crud.update_assignment(s, android, run_status="queued", queued_at=now + timedelta(seconds=1))
    assert await crud.list_queued_keys(s) == [("c1", "iOS"), ("c1", "Android")]
    claimed = await crud.claim_next_queued(s)
    assert (claimed.platform, claimed.run_status, claimed.attempts) == ("iOS", "running", 1)
    await crud.update_assignment(s, android, run_status="failed", failure_kind="url")
    assert await crud.requeue_assignments(s, include_running=True) == 1
    assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "queued"
    assert (await crud.get_assignment(s, "c1", "Android")).run_status == "failed"
    await crud.update_assignment(s, android, run_status="failed", failure_kind="system")
    assert await crud.requeue_assignments(s, include_running=False) == 1
    assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"


async def test_open_cycles_and_scope(s):
    assert [c.id for c in await crud.list_open_cycles(s, None)] == ["c1"]
    assert [c.id for c in await crud.list_open_cycles(s, {"p1"})] == ["c1"]
    assert await crud.list_open_cycles(s, set()) == []
    for platform in ("Android", "iOS"):
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", platform), run_status="completed")
    assert await crud.list_open_cycles(s, None) == []


async def test_notify_skips_inactive_and_duplicates(s):
    await notify(s, "review_failed", await admin_ids(s) + ["adm2", "adm", None], {"x": 1})
    rows = await crud.list_notifications(s, "review_failed")
    assert [(r.recipient_user_id, r.payload) for r in rows] == [("adm", {"x": 1})]
    assert await project_manager_ids(s, "p1") == ["pm"]


async def test_assignment_dicts(s):
    a = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, a, run_status="queued", queued_at=datetime.now(timezone.utc), devops_url="https://dev.azure.com/o/p/_git/r")
    rows = await assignment_dicts(s, [await crud.get_assignment(s, "c1", "iOS"), await crud.get_assignment(s, "c1", "Android")])
    assert [r["platform"] for r in rows] == ["Android", "iOS"]
    ios = rows[1]
    assert ios["queue_position"] == 1 and ios["reviewer_name"] == "Rae" and ios["devops_url"].endswith("/r")
    assert rows[0]["queue_position"] is None and rows[0]["review_status"] is None


async def test_org_automation_settings(s):
    settings = await crud.update_devops_pat(s, "enc", "abcd", "adm")
    assert (settings.devops_pat_encrypted, settings.devops_pat_last4, settings.devops_pat_updated_by) == ("enc", "abcd", "adm")
    settings = await crud.update_auto_compile_modes(s, {"iOS": "compiler"})
    assert effective_compile_modes(settings.auto_compile_modes) == {"Android": "compiler", ".NET": "compiler", "iOS": "compiler"}
    assert effective_compile_modes(None) == {"Android": "compiler", ".NET": "compiler", "iOS": "static"}
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.automation`.

- [ ] **Step 3: Models.**
  - In `models.py`, add `Text` to the sqlalchemy import.
  - Extend `ReviewCycleAssignment` (below `reviewer_id`):

```python
    devops_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    devops_branch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url_submitted_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # waiting_for_url -> queued -> running -> completed | failed (see app.automation.worker)
    run_status: Mapped[str] = mapped_column(String, nullable=False, default="waiting_for_url", server_default="waiting_for_url")
    run_phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    run_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "url" | "system"
    review_id: Mapped[Optional[str]] = mapped_column(ForeignKey("platform_reviews.id", ondelete="SET NULL"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_assigned_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

  Extend `OrgSettings`:

```python
    devops_pat_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    devops_pat_last4: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    devops_pat_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    devops_pat_updated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    auto_compile_modes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

  Append:

```python
class NotificationOutbox(Base):
    """Workflow emails waiting to be sent (Part 3's mailer marks sent_at)."""

    __tablename__ = "notification_outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Migration**

```python
# backend/alembic/versions/d4e5f6a7b8c9_automated_cycle_reviews.py
"""automated cycle reviews: assignment run state, org PAT/compile modes, notification outbox

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ASSIGNMENT_COLUMNS = [
    sa.Column("devops_url", sa.String(), nullable=True),
    sa.Column("devops_branch", sa.String(), nullable=True),
    sa.Column("url_submitted_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("url_submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("run_status", sa.String(), nullable=False, server_default="waiting_for_url"),
    sa.Column("run_phase", sa.String(), nullable=True),
    sa.Column("run_progress", sa.Integer(), nullable=True),
    sa.Column("run_error", sa.Text(), nullable=True),
    sa.Column("failure_kind", sa.String(), nullable=True),
    sa.Column("review_id", sa.String(), sa.ForeignKey("platform_reviews.id", ondelete="SET NULL"), nullable=True),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("reviewer_assigned_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("reviewer_assigned_at", sa.DateTime(timezone=True), nullable=True),
]
_ORG_COLUMNS = [
    sa.Column("devops_pat_encrypted", sa.Text(), nullable=True),
    sa.Column("devops_pat_last4", sa.String(), nullable=True),
    sa.Column("devops_pat_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("devops_pat_updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("auto_compile_modes", sa.JSON(), nullable=True),
]


def upgrade() -> None:
    for column in _ASSIGNMENT_COLUMNS:
        op.add_column("review_cycle_assignments", column)
    for column in _ORG_COLUMNS:
        op.add_column("org_settings", column)
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("recipient_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("notification_outbox")
    for column in reversed(_ORG_COLUMNS):
        op.drop_column("org_settings", column.name)
    for column in reversed(_ASSIGNMENT_COLUMNS):
        op.drop_column("review_cycle_assignments", column.name)
```

- [ ] **Step 5: crud.**
  - Add `update`, `or_` and `and_` to the sqlalchemy import, and `NotificationOutbox` to the models import.
  - Append:

```python
# --- automated cycle reviews ---

async def get_cycle_by_id(session: AsyncSession, cycle_id: str) -> Optional[ReviewCycle]:
    return await session.get(ReviewCycle, cycle_id)


async def get_assignment(session: AsyncSession, cycle_id: str, platform: str) -> Optional[ReviewCycleAssignment]:
    return await session.get(ReviewCycleAssignment, (cycle_id, platform))


async def update_assignment(session: AsyncSession, assignment: ReviewCycleAssignment, **fields) -> ReviewCycleAssignment:
    for name, value in fields.items():
        setattr(assignment, name, value)
    await session.commit()
    await session.refresh(assignment)
    return assignment


_QUEUE_ORDER = (ReviewCycleAssignment.queued_at, ReviewCycleAssignment.cycle_id, ReviewCycleAssignment.platform)


async def list_queued_keys(session: AsyncSession) -> list[tuple[str, str]]:
    result = await session.execute(
        select(ReviewCycleAssignment.cycle_id, ReviewCycleAssignment.platform)
        .where(ReviewCycleAssignment.run_status == "queued")
        .order_by(*_QUEUE_ORDER)
    )
    return [(cycle_id, platform) for cycle_id, platform in result.all()]


async def claim_next_queued(session: AsyncSession) -> Optional[ReviewCycleAssignment]:
    result = await session.execute(
        select(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == "queued").order_by(*_QUEUE_ORDER).limit(1)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        return None
    return await update_assignment(
        session, assignment, run_status="running", started_at=datetime.now(timezone.utc),
        attempts=(assignment.attempts or 0) + 1, run_phase=None, run_progress=0, run_error=None, failure_kind=None,
    )


async def requeue_assignments(session: AsyncSession, include_running: bool) -> int:
    condition = and_(ReviewCycleAssignment.run_status == "failed", ReviewCycleAssignment.failure_kind == "system")
    if include_running:
        condition = or_(condition, ReviewCycleAssignment.run_status == "running")
    result = await session.execute(
        update(ReviewCycleAssignment).where(condition).values(
            run_status="queued", queued_at=datetime.now(timezone.utc),
            run_error=None, failure_kind=None, run_phase=None, run_progress=None,
        )
    )
    await session.commit()
    return result.rowcount


async def get_review_statuses(session: AsyncSession, review_ids: list[str]) -> dict[str, str]:
    ids = [review_id for review_id in set(review_ids) if review_id]
    if not ids:
        return {}
    result = await session.execute(select(PlatformReview.id, PlatformReview.status).where(PlatformReview.id.in_(ids)))
    return {review_id: status for review_id, status in result.all()}


async def list_open_cycles(session: AsyncSession, project_ids: Optional[set[str]]) -> list[ReviewCycle]:
    if project_ids is not None and not project_ids:
        return []
    open_cycle_ids = select(ReviewCycleAssignment.cycle_id).where(ReviewCycleAssignment.run_status != "completed")
    query = select(ReviewCycle).where(ReviewCycle.id.in_(open_cycle_ids))
    if project_ids is not None:
        query = query.where(ReviewCycle.project_id.in_(project_ids))
    result = await session.execute(query.order_by(ReviewCycle.initiated_at.desc()))
    return list(result.scalars().all())


async def get_assignment_by_review_id(session: AsyncSession, review_id: str) -> Optional[ReviewCycleAssignment]:
    result = await session.execute(select(ReviewCycleAssignment).where(ReviewCycleAssignment.review_id == review_id))
    return result.scalars().first()


async def add_notifications(session: AsyncSession, event: str, recipient_ids: list[str], payload: dict) -> None:
    now = datetime.now(timezone.utc)
    for recipient_id in recipient_ids:
        session.add(NotificationOutbox(
            id=str(uuid.uuid4()), event=event, recipient_user_id=recipient_id, payload=payload, created_at=now,
        ))
    await session.commit()


async def list_notifications(session: AsyncSession, event: Optional[str] = None) -> list[NotificationOutbox]:
    query = select(NotificationOutbox).order_by(NotificationOutbox.created_at, NotificationOutbox.recipient_user_id)
    if event:
        query = query.where(NotificationOutbox.event == event)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_active_user_ids_with_roles(session: AsyncSession, roles: frozenset[str]) -> list[str]:
    result = await session.execute(
        select(User.id).where(User.role.in_(roles), User.is_active.is_(True)).order_by(User.email)
    )
    return [user_id for (user_id,) in result.all()]


async def _org_settings_row(session: AsyncSession) -> OrgSettings:
    settings = await session.get(OrgSettings, _ORG_SETTINGS_ID)
    if settings is None:
        settings = OrgSettings(id=_ORG_SETTINGS_ID, default_llm_provider="ollama", updated_at=datetime.now(timezone.utc))
        session.add(settings)
    return settings


async def update_devops_pat(session: AsyncSession, encrypted: str, last4: str, user_id: str) -> OrgSettings:
    settings = await _org_settings_row(session)
    settings.devops_pat_encrypted = encrypted
    settings.devops_pat_last4 = last4
    settings.devops_pat_updated_at = datetime.now(timezone.utc)
    settings.devops_pat_updated_by = user_id
    await session.commit()
    await session.refresh(settings)
    return settings


async def update_auto_compile_modes(session: AsyncSession, modes: dict) -> OrgSettings:
    settings = await _org_settings_row(session)
    settings.auto_compile_modes = dict(modes)
    await session.commit()
    await session.refresh(settings)
    return settings
```

- [ ] **Step 6: Helper modules**

```python
# backend/app/automation/config.py
DEFAULT_COMPILE_MODES = {"Android": "compiler", ".NET": "compiler", "iOS": "static"}
ALLOWED_COMPILE_MODES = {"Android": ("compiler", "local", "static"), ".NET": ("compiler", "static"), "iOS": ("compiler", "static")}


def effective_compile_modes(stored: dict | None) -> dict:
    """Org overrides on top of the defaults, ignoring unknown platforms."""
    return {**DEFAULT_COMPILE_MODES, **{k: v for k, v in (stored or {}).items() if k in DEFAULT_COMPILE_MODES}}
```

```python
# backend/app/automation/notify.py
"""Records workflow emails in notification_outbox; Part 3's mailer sends them."""
from app.db import crud


async def notify(session, event: str, user_ids, payload: dict) -> None:
    ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id]
    users = await crud.get_users_by_ids(session, ids)
    active = [user_id for user_id in ids if user_id in users and users[user_id].is_active]
    if active:
        await crud.add_notifications(session, event, active, payload)


async def project_manager_ids(session, project_id: str) -> list[str]:
    return (await crud.get_manager_ids_for_projects(session, [project_id]))[project_id]


async def admin_ids(session) -> list[str]:
    return await crud.list_active_user_ids_with_roles(session, frozenset({"admin"}))


def cycle_payload(project_name: str, platform: str | None, year: int, quarter: int, **extra) -> dict:
    return {"project_name": project_name, "platform": platform, "year": year, "quarter": quarter, **extra}
```

```python
# backend/app/automation/assignments.py
from app.db import crud
from app.quarterly import TRACKED_PLATFORMS


def _iso(value):
    return value.isoformat() if value else None


async def assignment_dicts(session, assignments) -> list[dict]:
    users = await crud.get_users_by_ids(session, [a.reviewer_id for a in assignments])
    statuses = await crud.get_review_statuses(session, [a.review_id for a in assignments])
    positions = {key: index + 1 for index, key in enumerate(await crud.list_queued_keys(session))}
    rows = []
    for a in sorted(assignments, key=lambda a: TRACKED_PLATFORMS.index(a.platform)):
        reviewer = users.get(a.reviewer_id)
        rows.append({
            "platform": a.platform,
            "reviewer_id": a.reviewer_id,
            "reviewer_name": (reviewer.name or reviewer.email) if reviewer else None,
            "devops_url": a.devops_url,
            "devops_branch": a.devops_branch,
            "run_status": a.run_status,
            "run_phase": a.run_phase,
            "run_progress": a.run_progress,
            "run_error": a.run_error,
            "failure_kind": a.failure_kind,
            "review_id": a.review_id,
            "review_status": statuses.get(a.review_id),
            "attempts": a.attempts,
            "queued_at": _iso(a.queued_at),
            "started_at": _iso(a.started_at),
            "finished_at": _iso(a.finished_at),
            "queue_position": positions.get((a.cycle_id, a.platform)) if a.run_status == "queued" else None,
        })
    return rows
```

- [ ] **Step 7: Run and verify.**
  - Run: `venv/bin/python -m pytest tests/test_db_automation.py tests/test_db_quarterly.py -q && venv/bin/alembic heads`.
  - Expected: PASS, and `d4e5f6a7b8c9 (head)`.
- [ ] **Step 8: Commit** with the message `feat: add assignment run state, org automation settings, and notification outbox`.

---

### Task 3: Pipeline marks URL-fixable failures

**Files:**
- Modify: `backend/app/api/reviews.py`, `backend/tests/test_reviews_create.py`

- [ ] **Step 1: Write the failing tests (append to `test_reviews_create.py`)**

```python
@pytest.mark.parametrize("fetch_status,expected_kind", [("not_found", "url"), ("invalid_url", "url"), ("unauthorized", None), ("error", None)])
async def test_run_review_marks_url_fixable_fetch_failures(monkeypatch, fetch_status, expected_kind):
    review_id = f"error-kind-{fetch_status}"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(_build_xlsx_bytes())
    _reviews[review_id] = _new_review_state()

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": fetch_status, "content": None, "message": "nope"}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)
    await _run_review(
        review_id, work_dir, work_dir / "android.zip", template_path, zip_valid=True, template_valid=True,
        project_name="r", devops_repo_url="https://dev.azure.com/o/p/_git/r", devops_pat="pat",
    )
    assert _reviews[review_id]["status"] == "error"
    assert _reviews[review_id]["error_kind"] == expected_kind


async def test_run_review_marks_analyzer_fatal_error_as_url_fixable(monkeypatch):
    review_id = "error-kind-fatal"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())
    _reviews[review_id] = _new_review_state()

    class _Fatal:
        fatal_error = "This doesn't look like an Android project."

    monkeypatch.setattr(reviews_module.android_analyzer, "analyze_project", lambda path: _Fatal())
    await _run_review(review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="r")
    assert _reviews[review_id]["error_kind"] == "url"
```

- [ ] **Step 2: Run and verify they fail.** Run `venv/bin/python -m pytest tests/test_reviews_create.py -q -k error_kind`. Expected: FAIL with `KeyError: 'error_kind'`.
- [ ] **Step 3: Implement.** In `reviews.py`:
  - In `_new_review_state()`, add `"error_kind": None,` after `"error": None,`.
  - In `_run_review`'s fetch-failure branch, before `return`, add:

```python
                if fetch_result["status"] in ("invalid_url", "not_found"):
                    state["error_kind"] = "url"
```

  - In the `if analysis.fatal_error:` branch, add `state["error_kind"] = "url"` before `return`.
- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: mark repo-URL-fixable review failures with error_kind`.

---

### Task 4: Automation settings API

**Files:**
- Modify: `backend/app/api/settings.py`
- Create: `backend/tests/test_settings_automation.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings_automation.py
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.settings as settings_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from app.secrets import decrypt
from main import app

client = TestClient(app)


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings_module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None)])
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="system")
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "iOS"), run_status="failed", failure_kind="url")
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_defaults_when_nothing_configured(db):
    _as("admin")
    body = client.get("/api/settings/automation").json()
    assert body == {
        "pat": {"configured": False, "last4": None, "updated_at": None, "updated_by_name": None},
        "compile_modes": {"Android": "compiler", ".NET": "compiler", "iOS": "static"},
    }


async def test_save_pat_encrypts_and_requeues_system_failures(db):
    _as("admin")
    response = client.put("/api/settings/devops-pat", json={"pat": "  secretpat1234  "})
    assert response.status_code == 200
    assert response.json()["configured"] is True and response.json()["last4"] == "1234"
    assert response.json()["updated_by_name"] == "Ada"
    async with db() as s:
        settings = await crud.get_org_settings(s)
        assert decrypt(settings.devops_pat_encrypted) == "secretpat1234"
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"
        assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"


def test_pat_is_never_returned(db):
    _as("admin")
    client.put("/api/settings/devops-pat", json={"pat": "secretpat1234"})
    assert "secretpat1234" not in client.get("/api/settings/automation").text


def test_pat_validation_and_permissions(db):
    _as("admin")
    assert client.put("/api/settings/devops-pat", json={"pat": "   "}).status_code == 400
    _as("management", "m")
    assert client.put("/api/settings/devops-pat", json={"pat": "x"}).status_code == 403
    assert client.get("/api/settings/automation").status_code == 200
    _as("coordinator", "c")
    assert client.get("/api/settings/automation").status_code == 403


def test_compile_modes(db):
    _as("management", "m")
    response = client.put("/api/settings/auto-compile-modes", json={"modes": {"iOS": "compiler", "Android": "local"}})
    assert response.json() == {"compile_modes": {"Android": "local", ".NET": "compiler", "iOS": "compiler"}}
    assert client.get("/api/settings/automation").json()["compile_modes"]["iOS"] == "compiler"
    assert client.put("/api/settings/auto-compile-modes", json={"modes": {".NET": "local"}}).status_code == 400
    assert client.put("/api/settings/auto-compile-modes", json={"modes": {"Web": "static"}}).status_code == 400
```

- [ ] **Step 2: Run and verify it fails.** Expected: FAIL (404s).
- [ ] **Step 3: Implement.** In `settings.py`, add these imports:

```python
from app.automation.config import ALLOWED_COMPILE_MODES, effective_compile_modes
from app.secrets import encrypt
```

  and append:

```python
class DevopsPatBody(BaseModel):
    pat: str


class CompileModesBody(BaseModel):
    modes: dict[str, str]


def _pat_summary(settings, users: dict) -> dict:
    if settings is None or not settings.devops_pat_encrypted:
        return {"configured": False, "last4": None, "updated_at": None, "updated_by_name": None}
    updater = users.get(settings.devops_pat_updated_by)
    return {
        "configured": True,
        "last4": settings.devops_pat_last4,
        "updated_at": settings.devops_pat_updated_at.isoformat() if settings.devops_pat_updated_at else None,
        "updated_by_name": (updater.name or updater.email) if updater else None,
    }


@router.get("/api/settings/automation")
async def get_automation_settings():
    async with new_session() as session:
        settings = await crud.get_org_settings(session)
        users = await crud.get_users_by_ids(session, [settings.devops_pat_updated_by] if settings else [])
    return {
        "pat": _pat_summary(settings, users),
        "compile_modes": effective_compile_modes(settings.auto_compile_modes if settings else None),
    }


@router.put("/api/settings/devops-pat")
async def put_devops_pat(body: DevopsPatBody, user=Depends(require_permission("settings.devops_pat"))):
    pat = body.pat.strip()
    if not pat:
        raise HTTPException(status_code=400, detail="PAT must not be empty")
    async with new_session() as session:
        settings = await crud.update_devops_pat(session, encrypt(pat), pat[-4:], user.id)
        # A new PAT is the usual fix for system failures (missing/expired PAT).
        await crud.requeue_assignments(session, include_running=False)
        users = await crud.get_users_by_ids(session, [user.id])
    return _pat_summary(settings, users)


@router.put("/api/settings/auto-compile-modes")
async def put_auto_compile_modes(body: CompileModesBody):
    for platform, mode in body.modes.items():
        if mode not in ALLOWED_COMPILE_MODES.get(platform, ()):
            raise HTTPException(status_code=400, detail=f"{mode!r} isn't a valid compile check for {platform}")
    async with new_session() as session:
        current = await crud.get_org_settings(session)
        merged = {**effective_compile_modes(current.auto_compile_modes if current else None), **body.modes}
        settings = await crud.update_auto_compile_modes(session, merged)
    return {"compile_modes": effective_compile_modes(settings.auto_compile_modes)}
```

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add automation settings API with encrypted DevOps PAT and compile modes`.

---

### Task 5: Cycle assignment API and workflow notifications

**Files:**
- Create: `backend/app/api/cycles.py`, `backend/tests/test_cycles_api.py`
- Modify:
  - `backend/main.py` (register the router)
  - `backend/app/api/quarterly.py` (full assignment dicts, initiation notifications)
  - `backend/app/api/reviews.py` (approval notification)
  - `backend/tests/test_quarterly_api.py` (the expected shape of the assignments)

**Interfaces:**
- Produces:
  - `GET /api/my/cycles` returns `{cycles: [...]}`.
  - `PUT .../url`, `POST .../retry`, `POST .../rerun` and `PUT .../reviewer` return an assignment dict.
- Consumes: `assignment_dicts`, `notify`, `parse_repo_url` from `app.analyzer.devops_client`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cycles_api.py
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.quarterly as quarterly_module
import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, quarterly_module, reviews_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        for user_id, role in (("rev", "reviewer"), ("rev2", "reviewer"), ("pm", "project_manager"), ("pm2", "project_manager"), ("adm", "admin")):
            await crud.create_user(s, user_id, f"{user_id}@example.com", "h", role)
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_project(s, "p2", "Beta")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.set_managers_for_project(s, "p2", ["pm2"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        await crud.create_cycle(s, "c2", "p2", 2026, 4, None, [("Android", "rev")])
    yield maker
    await engine.dispose()


def _as(role, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


async def _complete(maker, platform="Android", review_status="pending_approval"):
    async with maker() as s:
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform=platform, status=review_status, project_name="Alpha",
            created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=80, llm_provider="azure",
            llm_model=None, compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        await crud.set_review_reviewer(s, "r1", "rev")
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="completed", review_id="r1", devops_url=URL)


def test_my_cycles_scoped_to_pm(db):
    _as("project_manager", "pm")
    cycles = client.get("/api/my/cycles").json()["cycles"]
    assert [c["id"] for c in cycles] == ["c1"]
    assert cycles[0]["project_name"] == "Alpha" and cycles[0]["quarter"] == 4
    assert [a["platform"] for a in cycles[0]["assignments"]] == ["Android", "iOS"]
    assert cycles[0]["assignments"][0]["run_status"] == "waiting_for_url"
    _as("coordinator", "co")
    assert {c["id"] for c in client.get("/api/my/cycles").json()["cycles"]} == {"c1", "c2"}
    _as("reviewer", "rev")
    assert client.get("/api/my/cycles").status_code == 403


def test_submit_url_queues(db):
    _as("project_manager", "pm")
    response = client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL, "devops_branch": "develop"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_status"] == "queued" and body["queue_position"] == 1 and body["devops_branch"] == "develop"
    second = client.put("/api/cycles/c1/assignments/iOS/url", json={"devops_url": URL}).json()
    assert second["queue_position"] == 2 and second["devops_branch"] is None
    assert client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL}).status_code == 409


def test_submit_url_validation(db):
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": "https://github.com/x/y"}).status_code == 400
    assert client.put("/api/cycles/c1/assignments/.NET/url", json={"devops_url": URL}).status_code == 404
    assert client.put("/api/cycles/nope/assignments/Android/url", json={"devops_url": URL}).status_code == 404


def test_pm_cannot_touch_other_projects_cycles(db):
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c2/assignments/Android/url", json={"devops_url": URL}).status_code == 404
    assert client.post("/api/cycles/c2/assignments/Android/retry").status_code == 404


async def test_retry_only_when_failed(db):
    _as("project_manager", "pm")
    assert client.post("/api/cycles/c1/assignments/Android/retry").status_code == 409
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="failed", failure_kind="url", run_error="Repository or branch not found.", devops_url=URL)
    body = client.post("/api/cycles/c1/assignments/Android/retry").json()
    assert body["run_status"] == "queued" and body["run_error"] is None
    fixed = None
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="failed", failure_kind="url")
    fixed = client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL + "2"}).json()
    assert fixed["run_status"] == "queued" and fixed["devops_url"] == URL + "2"


async def test_rerun_rules(db):
    _as("project_manager", "pm")
    await _complete(db)
    assert client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL}).status_code == 403
    _as("coordinator", "co")
    body = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL + "-fixed"}).json()
    assert body["run_status"] == "queued" and body["devops_url"] == URL + "-fixed"
    assert client.post("/api/cycles/c1/assignments/iOS/rerun", json={"devops_url": URL}).status_code == 409


async def test_rerun_blocked_after_approval(db):
    await _complete(db, review_status="approved")
    _as("coordinator", "co")
    response = client.post("/api/cycles/c1/assignments/Android/rerun", json={"devops_url": URL})
    assert response.status_code == 409


async def test_reviewer_change_moves_finished_review_and_notifies(db):
    await _complete(db)
    _as("coordinator", "co")
    body = client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev2"}).json()
    assert body["reviewer_id"] == "rev2"
    async with db() as s:
        assert (await crud.get_review_by_id(s, "r1")).reviewer_id == "rev2"
        assigned = await crud.list_notifications(s, "reviewer_assigned")
        unassigned = await crud.list_notifications(s, "reviewer_unassigned")
        a = await crud.get_assignment(s, "c1", "Android")
    assert [n.recipient_user_id for n in assigned] == ["rev2"] and assigned[0].payload["link"] == "/reports/r1"
    assert [n.recipient_user_id for n in unassigned] == ["rev"]
    assert a.reviewer_assigned_by == "co" and a.reviewer_assigned_at is not None


async def test_reviewer_change_to_same_reviewer_is_a_noop(db):
    _as("coordinator", "co")
    client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev"})
    async with db() as s:
        assert await crud.list_notifications(s) == []


async def test_reviewer_change_blocked_after_approval(db):
    await _complete(db, review_status="approved")
    _as("coordinator", "co")
    response = client.put("/api/cycles/c1/assignments/Android/reviewer", json={"reviewer_id": "rev2"})
    assert response.status_code == 409
    assert client.put("/api/cycles/c1/assignments/iOS/reviewer", json={"reviewer_id": "pm"}).status_code == 400
    _as("project_manager", "pm")
    assert client.put("/api/cycles/c1/assignments/iOS/reviewer", json={"reviewer_id": "rev2"}).status_code == 403


async def test_initiation_records_notifications(db, monkeypatch):
    from datetime import date
    monkeypatch.setattr(quarterly_module, "_today", lambda: date(2026, 10, 7))
    async with db() as s:
        project = await crud.get_project(s, "p2")
        project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        await s.commit()
        await crud.set_platforms_for_project(s, "p2", ["Android"])
    _as("coordinator", "co")
    response = client.post("/api/projects/p2/cycles", json={"year": 2026, "quarter": 3, "assignments": [{"platform": "Android", "reviewer_id": "rev2"}]})
    assert response.status_code == 200
    assert response.json()["cycle"]["assignments"][0]["run_status"] == "waiting_for_url"
    async with db() as s:
        initiated = await crud.list_notifications(s, "cycle_initiated")
        assigned = await crud.list_notifications(s, "reviewer_assigned")
    assert [n.recipient_user_id for n in initiated] == ["pm2"]
    assert initiated[0].payload == {"project_name": "Beta", "platform": None, "year": 2026, "quarter": 3, "link": "/"}
    assert [n.recipient_user_id for n in assigned] == ["rev2"]


async def test_approving_a_cycle_review_notifies_pms(db):
    await _complete(db)
    _as("reviewer", "rev")
    assert client.patch("/api/reviews/r1", json={"status": "approved"}).status_code == 200
    async with db() as s:
        finalized = await crud.list_notifications(s, "review_finalized")
    assert [n.recipient_user_id for n in finalized] == ["pm"]
    assert finalized[0].payload["review_id"] == "r1" and finalized[0].payload["link"] == "/reports/r1"
```

  In `test_quarterly_api.py::test_initiate_cycle`, replace the exact `assignments` assertion with:

```python
    assert [(a["platform"], a["reviewer_id"], a["reviewer_name"], a["run_status"]) for a in entry["cycle"]["assignments"]] == [
        ("Android", "rev", "Rae", "waiting_for_url"), ("iOS", "rev", "Rae", "waiting_for_url"),
    ]
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.api.cycles`.

- [ ] **Step 3: Implement `app/api/cycles.py`**

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.analyzer.devops_client import parse_repo_url
from app.auth.permissions import PERMISSIONS, can, require_permission, visible_project_ids
from app.automation.assignments import assignment_dicts
from app.automation.notify import cycle_payload, notify
from app.db import crud
from app.db.session import new_session
from app.quarterly import canonical_platform

router = APIRouter()


class UrlBody(BaseModel):
    devops_url: str
    devops_branch: str | None = None


class ReviewerBody(BaseModel):
    reviewer_id: str


def _now():
    return datetime.now(timezone.utc)


async def _scope(session, user):
    return None if can(user, "cycles.view") else await visible_project_ids(session, user)


async def _load(session, user, cycle_id: str, platform: str):
    cycle = await crud.get_cycle_by_id(session, cycle_id)
    scope = await _scope(session, user)
    if cycle is None or (scope is not None and cycle.project_id not in scope):
        raise HTTPException(status_code=404, detail="Review cycle not found")
    assignment = await crud.get_assignment(session, cycle_id, canonical_platform(platform) or platform)
    if assignment is None:
        raise HTTPException(status_code=404, detail="This platform isn't part of the cycle")
    project = await crud.get_project(session, cycle.project_id)
    return cycle, project, assignment


def _validate_url(body: UrlBody):
    if parse_repo_url(body.devops_url.strip()) is None:
        raise HTTPException(status_code=400, detail="Not a recognized Azure DevOps repo URL.")


def _queue_fields(body: UrlBody, user) -> dict:
    return {
        "devops_url": body.devops_url.strip(),
        "devops_branch": (body.devops_branch or "").strip() or None,
        "url_submitted_by": user.id, "url_submitted_at": _now(),
        "run_status": "queued", "queued_at": _now(),
        "run_error": None, "failure_kind": None, "run_phase": None, "run_progress": None,
    }


async def _one(session, assignment) -> dict:
    return (await assignment_dicts(session, [assignment]))[0]


@router.get("/api/my/cycles")
async def list_my_cycles(user=Depends(require_permission("cycles.submit_urls"))):
    async with new_session() as session:
        cycles = await crud.list_open_cycles(session, await _scope(session, user))
        projects = {p.id: p for p in await crud.list_projects(session, project_ids={c.project_id for c in cycles} or None)} if cycles else {}
        by_cycle = await crud.get_cycle_assignments(session, [c.id for c in cycles])
        result = []
        for cycle in cycles:
            result.append({
                "id": cycle.id, "project_id": cycle.project_id, "project_name": projects[cycle.project_id].name,
                "year": cycle.year, "quarter": cycle.quarter, "initiated_at": cycle.initiated_at.isoformat(),
                "assignments": await assignment_dicts(session, by_cycle[cycle.id]),
            })
    return {"cycles": result}


@router.put("/api/cycles/{cycle_id}/assignments/{platform}/url")
async def submit_url(cycle_id: str, platform: str, body: UrlBody, user=Depends(require_permission("cycles.submit_urls"))):
    _validate_url(body)
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        if assignment.run_status not in ("waiting_for_url", "failed"):
            raise HTTPException(status_code=409, detail="This platform's review is already queued, running or completed.")
        await crud.update_assignment(session, assignment, **_queue_fields(body, user))
        return await _one(session, assignment)


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/retry")
async def retry(cycle_id: str, platform: str, user=Depends(require_permission("cycles.submit_urls"))):
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        if assignment.run_status != "failed":
            raise HTTPException(status_code=409, detail="Only a failed review can be retried.")
        await crud.update_assignment(
            session, assignment, run_status="queued", queued_at=_now(),
            run_error=None, failure_kind=None, run_phase=None, run_progress=None,
        )
        return await _one(session, assignment)


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/rerun")
async def rerun(cycle_id: str, platform: str, body: UrlBody, user=Depends(require_permission("cycles.initiate"))):
    _validate_url(body)
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        statuses = await crud.get_review_statuses(session, [assignment.review_id])
        if assignment.run_status != "completed" or statuses.get(assignment.review_id) == "approved":
            raise HTTPException(status_code=409, detail="Only a completed review that isn't approved yet can be re-run.")
        await crud.update_assignment(session, assignment, **_queue_fields(body, user))
        return await _one(session, assignment)


@router.put("/api/cycles/{cycle_id}/assignments/{platform}/reviewer")
async def change_reviewer(cycle_id: str, platform: str, body: ReviewerBody, user=Depends(require_permission("reviews.assign_reviewer"))):
    async with new_session() as session:
        cycle, project, assignment = await _load(session, user, cycle_id, platform)
        statuses = await crud.get_review_statuses(session, [assignment.review_id])
        if statuses.get(assignment.review_id) == "approved":
            raise HTTPException(status_code=409, detail="This review is already approved; its reviewer can't change.")
        reviewer = (await crud.get_users_by_ids(session, [body.reviewer_id])).get(body.reviewer_id)
        if reviewer is None or not reviewer.is_active or reviewer.role not in PERMISSIONS["reviews.finalize_own"]:
            raise HTTPException(status_code=400, detail="The reviewer must be an active reviewer, management or admin account.")
        previous = assignment.reviewer_id
        if previous == body.reviewer_id:
            return await _one(session, assignment)
        await crud.update_assignment(
            session, assignment, reviewer_id=body.reviewer_id, reviewer_assigned_by=user.id, reviewer_assigned_at=_now(),
        )
        if assignment.review_id:
            await crud.set_review_reviewer(session, assignment.review_id, body.reviewer_id)
        link = {"link": f"/reports/{assignment.review_id}"} if assignment.review_id else {}
        payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, **link)
        await notify(session, "reviewer_assigned", [body.reviewer_id], payload)
        await notify(session, "reviewer_unassigned", [previous], cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter))
        return await _one(session, assignment)
```

- [ ] **Step 4: Wire it up.**
  - **`main.py`:** add `from app.api.cycles import router as cycles_router` and `app.include_router(cycles_router)`.
  - **`quarterly.py`:**
    - Import `from app.automation.assignments import assignment_dicts` and `from app.automation.notify import cycle_payload, notify, project_manager_ids`.
    - In `_quarter_entries`, replace the `"assignments": [...]` list comprehension with `"assignments": await assignment_dicts(session, assignments[cycle.id]),`.
    - In `initiate_cycle`, after `create_cycle` succeeds and before the final `return`, add:

```python
        for_pms = cycle_payload(project.name, None, body.year, body.quarter, link="/")
        await notify(session, "cycle_initiated", await project_manager_ids(session, project_id), for_pms)
        for assignment in body.assignments:
            await notify(
                session, "reviewer_assigned", [assignment.reviewer_id],
                cycle_payload(project.name, canonical_platform(assignment.platform), body.year, body.quarter),
            )
```

  - **`reviews.py`:** in `update_review`, after the `crud.update_review` call and the `None` check, add:

```python
    if body.status == "approved" and existing.status != "approved":
        await _notify_review_finalized(review)
```

    and define this above `update_review`:

```python
async def _notify_review_finalized(review) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment_by_review_id(session, review.id)
        if assignment is None:
            return
        cycle = await crud.get_cycle_by_id(session, assignment.cycle_id)
        payload = cycle_payload(
            review.project_name, assignment.platform, cycle.year, cycle.quarter,
            review_id=review.id, total_score_pct=float(review.total_score_pct) if review.total_score_pct is not None else None,
            link=f"/reports/{review.id}",
        )
        await notify(session, "review_finalized", await project_manager_ids(session, cycle.project_id), payload)
```

    with `from app.automation.notify import cycle_payload, notify, project_manager_ids` added to the imports.

- [ ] **Step 5: Run the full backend suite.** Expected: PASS.
- [ ] **Step 6: Commit** with the message `feat: add cycle URL submission, retry, re-run and reviewer change with outbox notifications`.

---

### Task 6: Review worker

**Files:**
- Create: `backend/app/automation/worker.py`, `backend/tests/test_review_worker.py`
- Modify: `backend/main.py` (lifespan), `docker-compose.yml`

**Interfaces:**
- Produces:
  - `recover() -> int`
  - `run_one() -> bool` (True if something was processed)
  - `worker_loop()`
  - `start_worker() -> asyncio.Task`
  - Module constants `POLL_SECONDS = 5` and `PROGRESS_SYNC_SECONDS = 3`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_review_worker.py
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
import app.automation.worker as worker
from app.db import crud
from app.db.models import Base
from app.secrets import encrypt

URL = "https://dev.azure.com/org/Proj/_git/repo"


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "new_session", lambda: maker())
    monkeypatch.setattr(worker, "PROGRESS_SYNC_SECONDS", 0.01)

    async def fake_template(file, platform):
        return b"xlsx", "template.xlsx"

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_template)
    async with maker() as s:
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer")
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin")
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        await crud.update_devops_pat(s, encrypt("the-pat"), "-pat", "adm")
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="queued", queued_at=datetime.now(timezone.utc), devops_url=URL, devops_branch="main")
    yield maker
    await engine.dispose()


def _fake_pipeline(maker, outcome, error=None, error_kind=None, captured=None):
    async def fake_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
                              llm_provider="azure", ollama_model=None, compile_check_mode="compiler", platform="Android",
                              devops_repo_url=None, devops_pat=None, devops_branch=None, project_id=None, clause_overrides=None):
        if captured is not None:
            captured.update(locals())
        state = reviews_module._reviews[review_id]
        state["phase"], state["progress"] = "scoring", 60
        import asyncio
        await asyncio.sleep(0.05)
        state["status"] = outcome
        state["error"], state["error_kind"] = error, error_kind
        async with maker() as s:
            await crud.persist_review_result(
                s, review_id=review_id, project_id=project_id, platform=platform,
                status="pending_approval" if outcome == "completed" else "error", project_name=project_name,
                created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=70, llm_provider=llm_provider,
                llm_model=ollama_model, compile_check_mode=compile_check_mode, source="devops", workbook_path=None, result_data={},
            )
    return fake_run_review


async def test_success_links_review_sets_reviewer_and_notifies(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed", captured=captured))
    assert await worker.run_one() is True
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        review = await crud.get_review_by_id(s, a.review_id)
        ready = await crud.list_notifications(s, "review_ready")
    assert a.run_status == "completed" and a.run_progress == 100 and a.finished_at is not None and a.attempts == 1
    assert review.reviewer_id == "rev" and review.project_name == "Alpha"
    assert [n.recipient_user_id for n in ready] == ["rev"] and ready[0].payload["link"] == f"/reports/{a.review_id}"
    assert captured["devops_pat"] == "the-pat" and captured["devops_repo_url"] == URL and captured["devops_branch"] == "main"
    assert captured["compile_check_mode"] == "compiler" and captured["platform"] == "Android" and captured["project_id"] == "p1"
    assert await worker.run_one() is False


async def test_url_failure_records_error_and_notifies_admins(db, monkeypatch):
    async with db() as s:
        await crud.create_user(s, "adm-off", "off@example.com", "h", "admin")
        await crud.update_user(s, "adm-off", is_active=False)
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "error", "Repository or branch not found.", "url"))
    await worker.run_one()
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
        review = await crud.get_review_by_id(s, a.review_id)
    assert (a.run_status, a.failure_kind, a.run_error) == ("failed", "url", "Repository or branch not found.")
    assert review.status == "error"
    assert [n.recipient_user_id for n in failed] == ["adm"]
    assert failed[0].payload["error"] == "Repository or branch not found." and failed[0].payload["failure_kind"] == "url"


async def test_unclassified_failure_is_system(db, monkeypatch):
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "error", "LLM unreachable"))
    await worker.run_one()
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).failure_kind == "system"


async def test_missing_pat_is_a_system_failure(db, monkeypatch):
    async with db() as s:
        settings = await crud.get_org_settings(s)
        settings.devops_pat_encrypted = None
        await s.commit()

    async def must_not_run(*args, **kwargs):
        raise AssertionError("pipeline must not run without a PAT")

    monkeypatch.setattr(reviews_module, "_run_review", must_not_run)
    await worker.run_one()
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
    assert (a.run_status, a.failure_kind, a.run_error) == ("failed", "system", "No usable Azure DevOps PAT is configured in Settings.")
    assert len(failed) == 1


async def test_progress_is_synced_while_running(db, monkeypatch):
    seen = []
    real_update = crud.update_assignment

    async def spy(session, assignment, **fields):
        if "run_phase" in fields and fields.get("run_phase") == "scoring":
            seen.append(fields.get("run_progress"))
        return await real_update(session, assignment, **fields)

    monkeypatch.setattr(worker.crud, "update_assignment", spy)
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed"))
    await worker.run_one()
    assert 60 in seen


async def test_recover_requeues_running_and_system_failures_only(db):
    async with db() as s:
        android = await crud.get_assignment(s, "c1", "Android")
        ios = await crud.get_assignment(s, "c1", "iOS")
        await crud.update_assignment(s, android, run_status="running")
        await crud.update_assignment(s, ios, run_status="failed", failure_kind="url")
    assert await worker.recover() == 1
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"
        assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.automation.worker`.

- [ ] **Step 3: Implement**

```python
# backend/app/automation/worker.py
"""Runs queued cycle reviews one at a time (oldest first), in-process.

Queue and progress live on review_cycle_assignments, so a restart loses
nothing: recover() re-queues runs that were interrupted, plus runs that
failed for system reasons (an admin fix + restart is the retry).
"""
import asyncio
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import app.api.reviews as reviews_module
from app.automation.config import effective_compile_modes
from app.automation.notify import admin_ids, cycle_payload, notify
from app.db import crud
from app.db.session import new_session
from app.secrets import decrypt

logger = logging.getLogger(__name__)

POLL_SECONDS = 5
PROGRESS_SYNC_SECONDS = 3
NO_PAT = "No usable Azure DevOps PAT is configured in Settings."


def _now():
    return datetime.now(timezone.utc)


async def recover() -> int:
    async with new_session() as session:
        count = await crud.requeue_assignments(session, include_running=True)
    if count:
        logger.info("Review worker: re-queued %d interrupted or system-failed review(s)", count)
    return count


async def _sync_progress(cycle_id: str, platform: str, state: dict) -> None:
    while True:
        await asyncio.sleep(PROGRESS_SYNC_SECONDS)
        async with new_session() as session:
            assignment = await crud.get_assignment(session, cycle_id, platform)
            if assignment is not None:
                await crud.update_assignment(session, assignment, run_phase=state.get("phase"), run_progress=state.get("progress"))


async def _fail(cycle_id: str, platform: str, error: str, kind: str, review_id: str | None) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        await crud.update_assignment(
            session, assignment, run_status="failed", run_error=error, failure_kind=kind,
            review_id=review_id or assignment.review_id, finished_at=_now(),
        )
        payload = cycle_payload(
            project.name, platform, cycle.year, cycle.quarter, error=error, failure_kind=kind,
            review_id=review_id, devops_url=assignment.devops_url,
        )
        await notify(session, "review_failed", await admin_ids(session), payload)
    logger.warning("Review worker: %s %s failed (%s): %s", project.name, platform, kind, error)


async def _succeed(cycle_id: str, platform: str, review_id: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        if await crud.set_review_reviewer(session, review_id, assignment.reviewer_id) is None:
            raise RuntimeError("The finished review wasn't saved to the database.")
        await crud.update_assignment(
            session, assignment, run_status="completed", review_id=review_id, run_progress=100,
            run_phase="completed", finished_at=_now(),
        )
        payload = cycle_payload(project.name, platform, cycle.year, cycle.quarter, review_id=review_id, link=f"/reports/{review_id}")
        await notify(session, "review_ready", [assignment.reviewer_id], payload)


async def _process(cycle_id: str, platform: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        org = await crud.get_org_settings(session)
    pat = decrypt(org.devops_pat_encrypted) if org else None
    if not pat:
        await _fail(cycle_id, platform, NO_PAT, "system", None)
        return
    template_bytes, _ = await reviews_module._resolve_excel_template(None, platform)
    if template_bytes is None:
        await _fail(cycle_id, platform, f"No sample template is configured for {platform} in Settings.", "system", None)
        return

    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(template_bytes)
    state = reviews_module._new_review_state()
    state["project_name"] = project.name
    state["source"] = "devops"
    reviews_module._reviews[review_id] = state

    sync = asyncio.create_task(_sync_progress(cycle_id, platform, state))
    try:
        await reviews_module._run_review(
            review_id, work_dir, work_dir / "android.zip", template_path, True, True, project.name,
            org.default_llm_provider, org.default_ollama_model,
            effective_compile_modes(org.auto_compile_modes)[platform], platform,
            assignment.devops_url, pat, assignment.devops_branch, project_id=project.id,
        )
    finally:
        sync.cancel()

    if state["status"] == "completed":
        await _succeed(cycle_id, platform, review_id)
    else:
        await _fail(cycle_id, platform, state.get("error") or "Review failed", state.get("error_kind") or "system", review_id)


async def run_one() -> bool:
    async with new_session() as session:
        assignment = await crud.claim_next_queued(session)
    if assignment is None:
        return False
    try:
        await _process(assignment.cycle_id, assignment.platform)
    except Exception as exc:
        logger.exception("Review worker: unexpected error on %s/%s", assignment.cycle_id, assignment.platform)
        await _fail(assignment.cycle_id, assignment.platform, f"Unexpected error: {exc}", "system", None)
    return True


async def worker_loop() -> None:
    await recover()
    while True:
        try:
            if not await run_one():
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Review worker loop error")
            await asyncio.sleep(POLL_SECONDS)


def start_worker() -> asyncio.Task:
    return asyncio.create_task(worker_loop())
```

- [ ] **Step 4: Wire into the lifespan and docker-compose.**
  - In `main.py`, add `import os` if it's missing and `from app.automation.worker import start_worker`, then change `lifespan` to:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await _seed_admin_if_needed()
    # Exactly one backend instance should run the review worker (docker-compose sets this).
    worker_task = start_worker() if os.environ.get("REVIEW_WORKER_ENABLED", "").lower() == "true" else None
    yield
    if worker_task is not None:
        worker_task.cancel()
```

    Keep the existing decorator and signature, and change only the body.
  - In `docker-compose.yml`, add these lines under the backend `environment:` (after `SAMPLE_TEMPLATES_DIR`):

```yaml
      # Runs queued quarterly-cycle reviews; enable on exactly one backend instance.
      - REVIEW_WORKER_ENABLED=true
      # Fernet key for the stored DevOps PAT. Unset = derived from AUTH_SECRET_KEY.
      # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
      - SETTINGS_ENCRYPTION_KEY=${SETTINGS_ENCRYPTION_KEY:-}
```

    Because an empty `SETTINGS_ENCRYPTION_KEY` must fall back to the derived key, `_fernet()` uses `if not key` (an empty string counts as unset). That is already the case in Task 1's code.
- [ ] **Step 5: Run the full backend suite.** Expected: PASS.
- [ ] **Step 6: Commit** with the message `feat: add database-backed review worker for queued cycle reviews`.

---

### Task 7: Frontend API client and Settings "Automatic reviews"

**Files:**
- Modify: `frontend/src/services/api.js`, `frontend/src/pages/SettingsPage.jsx`, `frontend/src/testUtils/authUsers.js`, `frontend/src/context/AuthContext.jsx`
- Create: `frontend/src/components/AutomationSettingsSection.jsx` and its test

**Interfaces:**
- Produces:
  - `getMyCycles()`, `submitAssignmentUrl(cycleId, platform, { devopsUrl, devopsBranch })`
  - `retryAssignment(cycleId, platform)`, `rerunAssignment(cycleId, platform, { devopsUrl, devopsBranch })`
  - `changeAssignmentReviewer(cycleId, platform, reviewerId)`
  - `getAutomationSettings()`, `saveDevopsPat(pat)`, `saveAutoCompileModes(modes)`

- [ ] **Step 1: Update permissions and write the test.**
  - In `authUsers.js`, add `"cycles.submit_urls"` to admin, management, coordinator and project_manager, and `"settings.devops_pat"` to admin.
  - In `AuthContext.jsx`, add both to the default admin list.

```jsx
// frontend/src/components/AutomationSettingsSection.test.jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AutomationSettingsSection from "./AutomationSettingsSection";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getAutomationSettings, saveDevopsPat, saveAutoCompileModes } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getAutomationSettings: jest.fn(), saveDevopsPat: jest.fn(), saveAutoCompileModes: jest.fn(),
}));

const settings = {
  pat: { configured: true, last4: "1234", updated_at: "2026-10-01T00:00:00Z", updated_by_name: "Ada" },
  compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" },
};

beforeEach(() => {
  jest.resetAllMocks();
  getAutomationSettings.mockResolvedValue(settings);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <AutomationSettingsSection />
    </AuthContext.Provider>
  );
}

test("shows the PAT summary without the secret", async () => {
  renderAs("admin");
  expect(await screen.findByText(/Configured · ••••1234/)).toBeInTheDocument();
  expect(screen.getByText(/by Ada/)).toBeInTheDocument();
});

test("admin can save a new PAT", async () => {
  const user = userEvent.setup();
  saveDevopsPat.mockResolvedValue({ ...settings.pat, last4: "9999" });
  renderAs("admin");
  await screen.findByText(/••••1234/);
  await user.type(screen.getByLabelText("New Azure DevOps PAT"), "newpat9999");
  await user.click(screen.getByRole("button", { name: "Save PAT" }));
  await waitFor(() => expect(saveDevopsPat).toHaveBeenCalledWith("newpat9999"));
  expect(await screen.findByText(/••••9999/)).toBeInTheDocument();
  expect(screen.getByLabelText("New Azure DevOps PAT")).toHaveValue("");
});

test("management cannot edit the PAT but can save compile checks", async () => {
  const user = userEvent.setup();
  saveAutoCompileModes.mockResolvedValue({ Android: "compiler", ".NET": "compiler", iOS: "compiler" });
  renderAs("management");
  await screen.findByText(/••••1234/);
  expect(screen.queryByLabelText("New Azure DevOps PAT")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Compile check for iOS"), "compiler");
  await user.click(screen.getByRole("button", { name: "Save compile checks" }));
  await waitFor(() => expect(saveAutoCompileModes).toHaveBeenCalledWith({ Android: "compiler", ".NET": "compiler", iOS: "compiler" }));
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
});

test("not configured state", async () => {
  getAutomationSettings.mockResolvedValue({ ...settings, pat: { configured: false, last4: null, updated_at: null, updated_by_name: null } });
  renderAs("admin");
  expect(await screen.findByText(/Not configured/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify it fails.** Expected: FAIL (the module is missing).
- [ ] **Step 3: Implement.** Append to `api.js`:

```js
export async function getMyCycles() {
  const response = await axios.get(`${API_BASE_URL}/my/cycles`);
  return response.data.cycles;
}

function assignmentPath(cycleId, platform) {
  return `${API_BASE_URL}/cycles/${cycleId}/assignments/${encodeURIComponent(platform)}`;
}

export async function submitAssignmentUrl(cycleId, platform, { devopsUrl, devopsBranch }) {
  const response = await axios.put(`${assignmentPath(cycleId, platform)}/url`, { devops_url: devopsUrl, devops_branch: devopsBranch || null });
  return response.data;
}

export async function retryAssignment(cycleId, platform) {
  const response = await axios.post(`${assignmentPath(cycleId, platform)}/retry`);
  return response.data;
}

export async function rerunAssignment(cycleId, platform, { devopsUrl, devopsBranch }) {
  const response = await axios.post(`${assignmentPath(cycleId, platform)}/rerun`, { devops_url: devopsUrl, devops_branch: devopsBranch || null });
  return response.data;
}

export async function changeAssignmentReviewer(cycleId, platform, reviewerId) {
  const response = await axios.put(`${assignmentPath(cycleId, platform)}/reviewer`, { reviewer_id: reviewerId });
  return response.data;
}

export async function getAutomationSettings() {
  const response = await axios.get(`${API_BASE_URL}/settings/automation`);
  return response.data;
}

export async function saveDevopsPat(pat) {
  const response = await axios.put(`${API_BASE_URL}/settings/devops-pat`, { pat });
  return response.data;
}

export async function saveAutoCompileModes(modes) {
  const response = await axios.put(`${API_BASE_URL}/settings/auto-compile-modes`, { modes });
  return response.data.compile_modes;
}
```

```jsx
// frontend/src/components/AutomationSettingsSection.jsx
import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { hasPermission } from "../permissions";
import { getAutomationSettings, saveAutoCompileModes, saveDevopsPat } from "../services/api";

const COMPILE_OPTIONS = {
  Android: [["compiler", "Docker lint"], ["local", "Local lint (Mac agent)"], ["static", "Static analysis"]],
  ".NET": [["compiler", "Docker build"], ["static", "Static analysis"]],
  iOS: [["compiler", "Mac build agent"], ["static", "Static analysis"]],
};

function patSummary(pat) {
  if (!pat?.configured) return "Not configured — automatic reviews can't fetch repositories until an admin adds one.";
  const when = pat.updated_at ? ` · updated ${new Date(pat.updated_at).toLocaleDateString()}` : "";
  const by = pat.updated_by_name ? ` by ${pat.updated_by_name}` : "";
  return `Configured · ••••${pat.last4}${when}${by}`;
}

export default function AutomationSettingsSection() {
  const { user } = useAuth();
  const canSetPat = hasPermission(user, "settings.devops_pat");
  const [pat, setPat] = useState(null);
  const [newPat, setNewPat] = useState("");
  const [modes, setModes] = useState(null);
  const [error, setError] = useState("");
  const [patMessage, setPatMessage] = useState("");
  const [modesMessage, setModesMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAutomationSettings()
      .then((result) => { if (!cancelled) { setPat(result.pat); setModes(result.compile_modes); } })
      .catch(() => { if (!cancelled) setError("Failed to load automatic review settings"); });
    return () => { cancelled = true; };
  }, []);

  async function handleSavePat(event) {
    event.preventDefault();
    setPatMessage("");
    try {
      setPat(await saveDevopsPat(newPat.trim()));
      setNewPat("");
      setPatMessage("Saved. Reviews that failed for system reasons were re-queued.");
    } catch (err) {
      setPatMessage(err.response?.data?.detail || "Failed to save the PAT");
    }
  }

  async function handleSaveModes() {
    setModesMessage("");
    try {
      setModes(await saveAutoCompileModes(modes));
      setModesMessage("Saved.");
    } catch (err) {
      setModesMessage(err.response?.data?.detail || "Failed to save compile checks");
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Automatic reviews</div>
      <div className="card-title" style={{ fontSize: 18 }}>Quarterly cycle runs</div>
      <p className="card-body">Reviews started from a PM's DevOps URL use these settings plus the org-wide LLM provider and sample templates.</p>
      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

      {pat && (
        <div className="field" style={{ marginTop: "var(--space-3)" }}>
          <label>Azure DevOps PAT</label>
          <p className="card-body" style={{ margin: 0 }}>{patSummary(pat)}</p>
          {canSetPat && (
            <form onSubmit={handleSavePat} style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)", flexWrap: "wrap" }}>
              <input
                type="password" className="input" aria-label="New Azure DevOps PAT" autoComplete="new-password"
                placeholder={pat.configured ? "Replace PAT…" : "Paste PAT…"} value={newPat}
                onChange={(event) => setNewPat(event.target.value)} style={{ maxWidth: 360 }}
                data-1p-ignore data-lpignore="true"
              />
              <button type="submit" className="btn btn-primary" disabled={!newPat.trim()}>Save PAT</button>
            </form>
          )}
          {patMessage && <p className="card-body" style={{ marginTop: "var(--space-2)" }}>{patMessage}</p>}
        </div>
      )}

      {modes && (
        <div className="field" style={{ marginTop: "var(--space-4)" }}>
          <label>Compile check for automatic reviews</label>
          <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginTop: "var(--space-2)" }}>
            {Object.entries(COMPILE_OPTIONS).map(([platform, options]) => (
              <div key={platform} className="field" style={{ minWidth: 180 }}>
                <label htmlFor={`compile-${platform}`} style={{ fontSize: 13 }}>{platform}</label>
                <select
                  id={`compile-${platform}`} aria-label={`Compile check for ${platform}`} className="input"
                  value={modes[platform]} onChange={(event) => setModes((current) => ({ ...current, [platform]: event.target.value }))}
                >
                  {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-primary" style={{ marginTop: "var(--space-3)", alignSelf: "flex-start" }} onClick={handleSaveModes}>
            Save compile checks
          </button>
          {modesMessage && <p className="card-body" style={{ marginTop: "var(--space-2)" }}>{modesMessage}</p>}
        </div>
      )}
    </section>
  );
}
```

  In `SettingsPage.jsx`, import `AutomationSettingsSection` and render `<AutomationSettingsSection />` after `<LlmProviderSection />`.
- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add automatic review settings (DevOps PAT, compile checks) and cycle API client`.

---

### Task 8: PM "Pending quarterly reviews" panel

**Files:**
- Create:
  - `frontend/src/components/AssignmentStatusBadge.jsx` and its test
  - `frontend/src/components/PendingCyclesPanel.jsx` and its test
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx`, `frontend/src/design-system.css`

**Interfaces:**
- Produces: `assignmentStatusLabel(assignment)` and the default `AssignmentStatusBadge({ assignment })`. `PendingCyclesPanel` takes no props.

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/components/AssignmentStatusBadge.test.jsx
import { assignmentStatusLabel } from "./AssignmentStatusBadge";

test.each([
  [{ run_status: "waiting_for_url" }, "Waiting for URL"],
  [{ run_status: "queued", queue_position: 2 }, "Queued · #2"],
  [{ run_status: "queued", queue_position: null }, "Queued"],
  [{ run_status: "running", run_phase: "scoring", run_progress: 70 }, "Running · Scoring 70%"],
  [{ run_status: "running", run_phase: null, run_progress: null }, "Running · Starting"],
  [{ run_status: "completed", review_status: "pending_approval" }, "Completed"],
  [{ run_status: "completed", review_status: "approved" }, "Approved"],
  [{ run_status: "failed" }, "Failed"],
])("%o → %s", (assignment, label) => {
  expect(assignmentStatusLabel(assignment)).toBe(label);
});
```

```jsx
// frontend/src/components/PendingCyclesPanel.test.jsx
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PendingCyclesPanel from "./PendingCyclesPanel";
import { getMyCycles, submitAssignmentUrl } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getMyCycles: jest.fn(), submitAssignmentUrl: jest.fn() }));

const base = { reviewer_id: "r", reviewer_name: "Rae", devops_url: null, devops_branch: null, run_phase: null, run_progress: null,
  run_error: null, failure_kind: null, review_id: null, review_status: null, attempts: 0, queue_position: null };
const cycle = (assignments) => [{ id: "c1", project_id: "p1", project_name: "Moove", year: 2026, quarter: 4, initiated_at: "2026-10-07T00:00:00Z", assignments }];

beforeEach(() => jest.resetAllMocks());

function renderPanel() {
  return render(<MemoryRouter><PendingCyclesPanel /></MemoryRouter>);
}

test("renders nothing when there are no pending cycles", async () => {
  getMyCycles.mockResolvedValue([]);
  const { container } = renderPanel();
  await waitFor(() => expect(getMyCycles).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("shows each platform's status and the right action", async () => {
  getMyCycles.mockResolvedValue(cycle([
    { ...base, platform: "Android", run_status: "waiting_for_url" },
    { ...base, platform: "iOS", run_status: "failed", run_error: "Repository or branch not found.", devops_url: "https://dev.azure.com/o/p/_git/bad" },
    { ...base, platform: ".NET", run_status: "completed", review_id: "r9", review_status: "pending_approval", devops_url: "https://dev.azure.com/o/p/_git/ok" },
  ]));
  renderPanel();
  const panel = await screen.findByRole("region", { name: "Pending quarterly reviews" });
  expect(within(panel).getByText("Moove · Q4 2026 review")).toBeInTheDocument();
  expect(within(panel).getByRole("button", { name: "Save & queue" })).toBeInTheDocument();
  expect(within(panel).getByText("Repository or branch not found.")).toBeInTheDocument();
  expect(within(panel).getByLabelText("DevOps URL for iOS")).toHaveValue("https://dev.azure.com/o/p/_git/bad");
  expect(within(panel).getByRole("button", { name: "Save & retry" })).toBeInTheDocument();
  expect(within(panel).getByRole("link", { name: "View" })).toHaveAttribute("href", "/reports/r9");
});

test("saving a URL queues it", async () => {
  const user = userEvent.setup();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "waiting_for_url" }]));
  submitAssignmentUrl.mockResolvedValue({ ...base, platform: "Android", run_status: "queued", queue_position: 1, devops_url: "https://dev.azure.com/o/p/_git/r" });
  renderPanel();
  await user.type(await screen.findByLabelText("DevOps URL for Android"), "https://dev.azure.com/o/p/_git/r");
  await user.type(screen.getByLabelText("Branch for Android"), "develop");
  await user.click(screen.getByRole("button", { name: "Save & queue" }));
  await waitFor(() => expect(submitAssignmentUrl).toHaveBeenCalledWith("c1", "Android", { devopsUrl: "https://dev.azure.com/o/p/_git/r", devopsBranch: "develop" }));
  expect(await screen.findByText("Queued · #1")).toBeInTheDocument();
});

test("shows the API error when saving fails", async () => {
  const user = userEvent.setup();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "waiting_for_url" }]));
  submitAssignmentUrl.mockRejectedValue({ response: { data: { detail: "Not a recognized Azure DevOps repo URL." } } });
  renderPanel();
  await user.type(await screen.findByLabelText("DevOps URL for Android"), "https://github.com/x");
  await user.click(screen.getByRole("button", { name: "Save & queue" }));
  expect(await screen.findByText("Not a recognized Azure DevOps repo URL.")).toBeInTheDocument();
});

test("refreshes every 10s while something is queued or running", async () => {
  jest.useFakeTimers();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "running", run_phase: "scoring", run_progress: 40 }]));
  renderPanel();
  expect(await screen.findByText("Running · Scoring 40%")).toBeInTheDocument();
  expect(getMyCycles).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(getMyCycles).toHaveBeenCalledTimes(2);
  jest.useRealTimers();
});
```

  Add to `ProjectDashboardPage.test.jsx`, mocking `getMyCycles` in that file's api mock:
  - Add `getMyCycles: jest.fn()` to the mock factory and import it.
  - In `beforeEach`, add `getMyCycles.mockResolvedValue([]);`.

```jsx
test("PM sees pending quarterly reviews above the filters", async () => {
  getMyCycles.mockResolvedValue([{ id: "c1", project_id: "p1", project_name: "Alpha", year: 2026, quarter: 4, initiated_at: "2026-10-07T00:00:00Z",
    assignments: [{ platform: "Android", reviewer_id: "r", reviewer_name: "Rae", run_status: "waiting_for_url", devops_url: null }] }]);
  renderAsPm([{ id: "p1", name: "Alpha" }]);
  expect(await screen.findByRole("region", { name: "Pending quarterly reviews" })).toBeInTheDocument();
});

test("admin does not get the PM pending panel", async () => {
  renderDashboard();
  await screen.findByRole("button", { name: "Project" });
  expect(getMyCycles).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run and verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/AssignmentStatusBadge.jsx
const PHASE_LABELS = {
  fetching: "Fetching", extracting: "Extracting", analyzing: "Analyzing", compiling: "Compiling",
  scoring: "Scoring", generating: "Generating", completed: "Finishing",
};

export function assignmentStatusLabel(assignment) {
  switch (assignment.run_status) {
    case "waiting_for_url": return "Waiting for URL";
    case "queued": return assignment.queue_position ? `Queued · #${assignment.queue_position}` : "Queued";
    case "running": {
      const phase = PHASE_LABELS[assignment.run_phase] || "Starting";
      return `Running · ${phase}${assignment.run_progress != null ? ` ${assignment.run_progress}%` : ""}`;
    }
    case "completed": return assignment.review_status === "approved" ? "Approved" : "Completed";
    case "failed": return "Failed";
    default: return assignment.run_status;
  }
}

export default function AssignmentStatusBadge({ assignment }) {
  return <span className={`run-badge run-badge--${assignment.run_status.replace(/_/g, "-")}`}>{assignmentStatusLabel(assignment)}</span>;
}
```

```jsx
// frontend/src/components/PendingCyclesPanel.jsx
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AssignmentStatusBadge from "./AssignmentStatusBadge";
import { getMyCycles, submitAssignmentUrl } from "../services/api";

const REFRESH_MS = 10000;

function AssignmentRow({ cycleId, assignment, onUpdated }) {
  const editable = assignment.run_status === "waiting_for_url" || assignment.run_status === "failed";
  const [url, setUrl] = useState(assignment.devops_url || "");
  const [branch, setBranch] = useState(assignment.devops_branch || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onUpdated(await submitAssignmentUrl(cycleId, assignment.platform, { devopsUrl: url.trim(), devopsBranch: branch.trim() }));
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save the URL.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{assignment.platform}</td>
      <td>{assignment.reviewer_name || "—"}</td>
      <td>
        <AssignmentStatusBadge assignment={assignment} />
        {assignment.run_status === "failed" && assignment.run_error && <div className="run-error">{assignment.run_error}</div>}
      </td>
      <td style={{ minWidth: 320 }}>
        {editable ? (
          <form onSubmit={handleSave} className="assignment-url-form">
            <input
              className="input" aria-label={`DevOps URL for ${assignment.platform}`} placeholder="https://dev.azure.com/org/project/_git/repo"
              value={url} onChange={(event) => setUrl(event.target.value)} autoComplete="off" data-1p-ignore data-lpignore="true"
            />
            <input
              className="input" aria-label={`Branch for ${assignment.platform}`} placeholder="default branch"
              value={branch} onChange={(event) => setBranch(event.target.value)} autoComplete="off" style={{ maxWidth: 160 }}
            />
            <button type="submit" className="btn btn-primary" disabled={saving || !url.trim()}>
              {assignment.run_status === "failed" ? "Save & retry" : "Save & queue"}
            </button>
            {error && <p className="run-error" style={{ flexBasis: "100%" }}>{error}</p>}
          </form>
        ) : assignment.run_status === "completed" && assignment.review_id ? (
          <Link to={`/reports/${assignment.review_id}`} className="btn btn-ghost">View</Link>
        ) : (
          <span className="quarter-card-meta" style={{ wordBreak: "break-all" }}>{assignment.devops_url}</span>
        )}
      </td>
    </tr>
  );
}

export default function PendingCyclesPanel() {
  const [cycles, setCycles] = useState(null);

  const load = useCallback(() => {
    getMyCycles().then(setCycles).catch(() => setCycles((current) => current ?? []));
  }, []);

  useEffect(() => { load(); }, [load]);

  const active = (cycles || []).some((cycle) => cycle.assignments.some((a) => a.run_status === "queued" || a.run_status === "running"));
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, load]);

  function replaceAssignment(cycleId, updated) {
    setCycles((current) => current.map((cycle) => (cycle.id !== cycleId ? cycle : {
      ...cycle, assignments: cycle.assignments.map((a) => (a.platform === updated.platform ? updated : a)),
    })));
  }

  if (!cycles || cycles.length === 0) return null;

  return (
    <section className="card pending-cycles" aria-label="Pending quarterly reviews">
      <div className="card-kicker">Action needed</div>
      <div className="card-title" style={{ fontSize: 18 }}>Pending quarterly reviews</div>
      <p className="card-body">Add the Azure DevOps repository for each platform. The review runs automatically once saved.</p>
      {cycles.map((cycle) => (
        <div key={cycle.id} className="pending-cycle">
          <div className="pending-cycle-head">
            <span className="pending-cycle-title">{cycle.project_name} · Q{cycle.quarter} {cycle.year} review</span>
            <span className="quarter-card-meta">Initiated {new Date(cycle.initiated_at).toLocaleDateString()}</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead><tr><th>Platform</th><th>Reviewer</th><th>Status</th><th>Repository</th></tr></thead>
              <tbody>
                {cycle.assignments.map((assignment) => (
                  <AssignmentRow
                    key={`${assignment.platform}-${assignment.run_status}`} cycleId={cycle.id} assignment={assignment}
                    onUpdated={(updated) => replaceAssignment(cycle.id, updated)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
```

  In `ProjectDashboardPage.jsx`, import `PendingCyclesPanel`. Directly after the `<header>…</header>` block inside `<main>`, add:

```jsx
        {can("cycles.submit_urls") && can("dashboard.view_assigned") && <PendingCyclesPanel />}
```

  Append to `design-system.css`:

```css
/* — automated cycle runs — */
.pending-cycles { padding: 20px; display: grid; gap: var(--space-3); border-color: color-mix(in srgb, #e0b400 45%, var(--color-divider)); }
.pending-cycle { display: grid; gap: var(--space-2); }
.pending-cycle-head { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
.pending-cycle-title { font-weight: 600; }
.assignment-url-form { display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center; }
.assignment-url-form .input:first-child { flex: 1; min-width: 220px; }
.run-badge { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; display: inline-block; }
.run-badge--waiting-for-url { background: var(--color-surface); color: var(--color-text-muted); border: 1px solid var(--color-divider); }
.run-badge--queued { background: color-mix(in srgb, #e0b400 18%, var(--color-bg)); color: #6b5300; }
.run-badge--running { background: color-mix(in srgb, var(--color-accent) 15%, var(--color-bg)); color: var(--color-accent); }
.run-badge--completed { background: color-mix(in srgb, #2e9e5b 15%, var(--color-bg)); color: #1f6e3f; }
.run-badge--failed { background: color-mix(in srgb, var(--color-brand-coral) 15%, var(--color-bg)); color: var(--color-brand-coral); }
.run-error { margin: 4px 0 0; font-size: 12px; color: var(--color-brand-coral); }
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add PM pending quarterly reviews panel with per-platform DevOps URL entry`.

---

### Task 9: Coordinator "Manage" dialog and run status on cards

**Files:**
- Create: `frontend/src/components/ManageCycleDialog.jsx` and its test
- Modify:
  - `frontend/src/components/QuarterCard.jsx` (+ test)
  - `frontend/src/pages/QuarterlyDashboardPage.jsx` (+ test)

**Interfaces:**
- Produces:
  - `<ManageCycleDialog project year entry onChanged onClose />`
  - `QuarterCard` gains `canManage` and `onManage` props.

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/components/ManageCycleDialog.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ManageCycleDialog from "./ManageCycleDialog";
import { getReviewers, changeAssignmentReviewer, retryAssignment, rerunAssignment } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getReviewers: jest.fn(), changeAssignmentReviewer: jest.fn(), retryAssignment: jest.fn(), rerunAssignment: jest.fn(),
}));

const a = (platform, extra) => ({ platform, reviewer_id: "r1", reviewer_name: "Rae", devops_url: "https://dev.azure.com/o/p/_git/x",
  devops_branch: null, run_phase: null, run_progress: null, run_error: null, failure_kind: null, review_id: null,
  review_status: null, attempts: 1, queue_position: null, ...extra });
const entry = { quarter: 4, cycle: { id: "c1", initiated_at: "2026-10-07T00:00:00Z", initiated_by_name: "Cora", assignments: [
  a("Android", { run_status: "completed", review_id: "rv1", review_status: "pending_approval" }),
  a("iOS", { run_status: "failed", run_error: "Could not reach Azure DevOps." }),
  a(".NET", { run_status: "completed", review_id: "rv2", review_status: "approved" }),
] } };

beforeEach(() => {
  jest.resetAllMocks();
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }, { id: "r2", email: "sam@example.com", name: "Sam" }]);
});

function renderDialog(onChanged = jest.fn()) {
  render(<ManageCycleDialog project={{ id: "p1", name: "Moove" }} year={2026} entry={entry} onChanged={onChanged} onClose={jest.fn()} />);
  return onChanged;
}

function row(platform) {
  return screen.getByRole("row", { name: new RegExp(`^${platform.replace(".", "\\.")}`) });
}

test("lists platforms with status, error and reviewer", async () => {
  renderDialog();
  expect(screen.getByText("Q4 2026 review — Moove")).toBeInTheDocument();
  await screen.findAllByRole("option", { name: "Sam" });
  expect(within(row("iOS")).getByText("Failed")).toBeInTheDocument();
  expect(within(row("iOS")).getByText("Could not reach Azure DevOps.")).toBeInTheDocument();
  expect(within(row(".NET")).getByLabelText("Reviewer for .NET")).toBeDisabled();
  expect(within(row(".NET")).queryByRole("button", { name: "Re-run" })).not.toBeInTheDocument();
});

test("changing the reviewer saves and reports the change", async () => {
  const user = userEvent.setup();
  changeAssignmentReviewer.mockResolvedValue(a("Android", { run_status: "completed", review_id: "rv1", reviewer_id: "r2", reviewer_name: "Sam" }));
  const onChanged = renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  await user.selectOptions(within(row("Android")).getByLabelText("Reviewer for Android"), "r2");
  await waitFor(() => expect(changeAssignmentReviewer).toHaveBeenCalledWith("c1", "Android", "r2"));
  expect(onChanged).toHaveBeenCalled();
});

test("retry a failed platform", async () => {
  const user = userEvent.setup();
  retryAssignment.mockResolvedValue(a("iOS", { run_status: "queued", queue_position: 1 }));
  renderDialog();
  await user.click(within(row("iOS")).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryAssignment).toHaveBeenCalledWith("c1", "iOS"));
  expect(await within(row("iOS")).findByText("Queued · #1")).toBeInTheDocument();
});

test("re-run a completed platform with a new URL", async () => {
  const user = userEvent.setup();
  rerunAssignment.mockResolvedValue(a("Android", { run_status: "queued", queue_position: 1, devops_url: "https://dev.azure.com/o/p/_git/fixed" }));
  renderDialog();
  await user.click(within(row("Android")).getByRole("button", { name: "Re-run" }));
  const input = screen.getByLabelText("New DevOps URL for Android");
  await user.clear(input);
  await user.type(input, "https://dev.azure.com/o/p/_git/fixed");
  await user.click(screen.getByRole("button", { name: "Queue re-run" }));
  await waitFor(() => expect(rerunAssignment).toHaveBeenCalledWith("c1", "Android", { devopsUrl: "https://dev.azure.com/o/p/_git/fixed" }));
  expect(screen.queryByLabelText("New DevOps URL for Android")).not.toBeInTheDocument();
});

test("shows API errors", async () => {
  const user = userEvent.setup();
  retryAssignment.mockRejectedValue({ response: { data: { detail: "Only a failed review can be retried." } } });
  renderDialog();
  await user.click(within(row("iOS")).getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Only a failed review can be retried.")).toBeInTheDocument();
});
```

  Add to `QuarterCard.test.jsx`:

```jsx
test("Manage button and run status lines for an initiated quarter", async () => {
  const user = userEvent.setup();
  const onManage = jest.fn();
  const entry = { ...base, status: "in_progress", covered: [], missing: ["Android", "iOS"], can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora", assignments: [
      { platform: "Android", reviewer_id: "r", reviewer_name: "Rae", run_status: "running", run_phase: "scoring", run_progress: 50 },
      { platform: "iOS", reviewer_id: "r", reviewer_name: "Rae", run_status: "failed" },
    ] } };
  render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate canManage onManage={onManage} onInitiate={jest.fn()} />);
  expect(screen.getByText(/Running · Scoring 50%/)).toBeInTheDocument();
  expect(screen.getByText(/Failed/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Manage" }));
  expect(onManage).toHaveBeenCalled();
});

test("no Manage button without a cycle or permission", () => {
  render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} canManage onManage={jest.fn()} onInitiate={jest.fn()} />);
  expect(screen.queryByRole("button", { name: "Manage" })).not.toBeInTheDocument();
});
```

  Add to `QuarterlyDashboardPage.test.jsx`:

```jsx
test("Manage opens the cycle dialog and changes reload the dashboard", async () => {
  const user = userEvent.setup();
  const cycleEntry = q(4, "in_progress", { cycle: { id: "c1", initiated_at: "2026-10-07T00:00:00Z", initiated_by_name: "Cora", assignments: [
    { platform: "Android", reviewer_id: "r1", reviewer_name: "Rae", run_status: "failed", run_error: "boom", devops_url: "https://dev.azure.com/o/p/_git/x", review_status: null },
  ] } });
  getQuarterly.mockResolvedValue({ ...data, projects: [{ ...data.projects[0], quarters: [q(1, "done"), q(2, "done"), q(3, "overdue"), cycleEntry] }] });
  retryAssignment.mockResolvedValue({ platform: "Android", reviewer_id: "r1", reviewer_name: "Rae", run_status: "queued", queue_position: 1 });
  renderAs();
  const row = await screen.findByRole("region", { name: "Alpha" });
  await user.click(within(row).getByRole("button", { name: "Manage" }));
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(getQuarterly).toHaveBeenCalledTimes(2));
});
```

  (Add `retryAssignment: jest.fn()` to that file's api mock and import it.)

- [ ] **Step 2: Run and verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/ManageCycleDialog.jsx
import { useEffect, useState } from "react";
import AssignmentStatusBadge from "./AssignmentStatusBadge";
import { changeAssignmentReviewer, getReviewers, rerunAssignment, retryAssignment } from "../services/api";

export default function ManageCycleDialog({ project, year, entry, onChanged, onClose }) {
  const cycleId = entry.cycle.id;
  const [assignments, setAssignments] = useState(entry.cycle.assignments);
  const [reviewers, setReviewers] = useState([]);
  const [error, setError] = useState("");
  const [rerunFor, setRerunFor] = useState(null);
  const [rerunUrl, setRerunUrl] = useState("");

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  async function act(request) {
    setError("");
    try {
      const updated = await request();
      setAssignments((current) => current.map((a) => (a.platform === updated.platform ? updated : a)));
      onChanged();
      return true;
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong.");
      return false;
    }
  }

  function reviewerOptions(assignment) {
    const known = reviewers.some((r) => r.id === assignment.reviewer_id);
    const extra = assignment.reviewer_id && !known ? [{ id: assignment.reviewer_id, name: assignment.reviewer_name || assignment.reviewer_id }] : [];
    return [...reviewers, ...extra];
  }

  async function handleRerun(event) {
    event.preventDefault();
    if (await act(() => rerunAssignment(cycleId, rerunFor, { devopsUrl: rerunUrl.trim() }))) setRerunFor(null);
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Manage review cycle" style={{ maxWidth: 760 }} onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">Q{entry.quarter} {year} review — {project.name}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead><tr><th>Platform</th><th>Status</th><th>Reviewer</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {assignments.map((assignment) => {
                  const approved = assignment.review_status === "approved";
                  return (
                    <tr key={assignment.platform}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{assignment.platform}</div>
                        <div className="quarter-card-meta" style={{ wordBreak: "break-all" }}>{assignment.devops_url || "No URL yet"}</div>
                      </td>
                      <td>
                        <AssignmentStatusBadge assignment={assignment} />
                        {assignment.run_status === "failed" && assignment.run_error && <div className="run-error">{assignment.run_error}</div>}
                      </td>
                      <td>
                        <select
                          aria-label={`Reviewer for ${assignment.platform}`} className="input" disabled={approved}
                          value={assignment.reviewer_id || ""}
                          onChange={(event) => act(() => changeAssignmentReviewer(cycleId, assignment.platform, event.target.value))}
                        >
                          {!assignment.reviewer_id && <option value="" disabled>Choose…</option>}
                          {reviewerOptions(assignment).map((reviewer) => (
                            <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>
                          ))}
                        </select>
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        {assignment.run_status === "failed" && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => retryAssignment(cycleId, assignment.platform))}>Retry</button>
                        )}
                        {assignment.run_status === "completed" && !approved && (
                          <button type="button" className="btn btn-ghost" onClick={() => { setRerunFor(assignment.platform); setRerunUrl(assignment.devops_url || ""); }}>Re-run</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {rerunFor && (
            <form onSubmit={handleRerun} className="field" style={{ display: "grid", gap: "var(--space-2)" }}>
              <label htmlFor="rerunUrl">New DevOps URL for {rerunFor}</label>
              <input id="rerunUrl" className="input" value={rerunUrl} onChange={(event) => setRerunUrl(event.target.value)} autoComplete="off" />
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button type="submit" className="btn btn-primary" disabled={!rerunUrl.trim()}>Queue re-run</button>
                <button type="button" className="btn" onClick={() => setRerunFor(null)}>Cancel</button>
              </div>
            </form>
          )}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
```

  **`QuarterCard.jsx`:**
  - Import `{ assignmentStatusLabel }` from `./AssignmentStatusBadge`.
  - Change the signature to `({ entry, platforms, canInitiate, onInitiate, canManage = false, onManage })`.
  - Build `const assignmentByPlatform = Object.fromEntries((entry.cycle?.assignments || []).map((a) => [a.platform, a]));`.
  - In each platform `<li>`, after the reviewer span, add:

```jsx
                {!covered && assignmentByPlatform[platform]?.run_status && assignmentByPlatform[platform].run_status !== "completed" && (
                  <span className="quarter-card-meta"> · {assignmentStatusLabel(assignmentByPlatform[platform])}</span>
                )}
```

  - After the Initiate button, add:

```jsx
      {canManage && entry.cycle && (
        <button type="button" className="btn btn-ghost quarter-card-action" onClick={onManage}>Manage</button>
      )}
```

  **`QuarterlyDashboardPage.jsx`:**
  - Import `ManageCycleDialog`.
  - Add the state `const [managing, setManaging] = useState(null); // { project, entry, year }`.
  - Add:

```jsx
  function reload() {
    const loadedYear = data?.year;
    if (!loadedYear) return;
    getQuarterly(loadedYear)
      .then((result) => setData((current) => (current && current.year === result.year ? result : current)))
      .catch(() => {});
  }
```

  - Pass `canManage={can("cycles.initiate")} onManage={() => setManaging({ project, entry, year: data.year })}` to `QuarterCard`.
  - Render:

```jsx
      {managing && (
        <ManageCycleDialog
          project={managing.project} year={managing.year} entry={managing.entry}
          onChanged={reload} onClose={() => setManaging(null)}
        />
      )}
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add coordinator Manage dialog for cycle runs and show run status on quarter cards`.

---

### Task 10: Docker smoke test and progress log

- [ ] **Step 1: Run both suites in full.** Expected: all pass.
- [ ] **Step 2: Back up the database, then check it.**
  - Back up: `pg_dump` to `<scratchpad>/codereviews-before-automation.sql`.
  - Record the counts of users, projects, reviews, cycles and assignments, plus the existing Moove Q3 2026 cycle.
- [ ] **Step 3: Rebuild.**
  - Run `docker compose up -d --build --no-deps backend frontend`.
  - Confirm `Running upgrade c3d4e5f6a7b8 -> d4e5f6a7b8c9`.
  - Confirm the Moove Q3 assignments read `waiting_for_url`.
  - Confirm the backend log shows the worker started, with no recovery count since nothing was queued.
- [ ] **Step 4: Run the API smoke test with temporary data only.**
  - Create `smoke-pm` (assigned to a new `Smoke Project` with platforms `Android`) and `smoke-coordinator`.
  - Have the coordinator initiate the current quarter with `reviewer@example.com`.
  - As `smoke-pm`, `GET /api/my/cycles` shows it.
  - Submit an invalid DevOps URL for the repo, `https://dev.azure.com/smoke-org/Smoke/_git/does-not-exist`. With no PAT set, expect within about 10s `failed` / `system` / "No usable Azure DevOps PAT…", and a `review_failed` outbox row per admin.
  - **Do not** save a PAT, so the user's real settings aren't overwritten. **Do not** run a real review.
  - Change the reviewer as the coordinator and check the outbox rows.
  - Clean up: delete `Smoke Project`, which needs its cycle deleted first (delete_project handles that); the smoke users, which cascade their outbox rows; and the leftover outbox rows for real admins tagged with `Smoke Project` (`DELETE FROM notification_outbox WHERE payload->>'project_name' = 'Smoke Project'`).
  - Confirm the counts match Step 2.
- [ ] **Step 5: Update `progress.md`** with Phase 10 (automated cycle reviews), including the deploy notes (`SETTINGS_ENCRYPTION_KEY`, PAT scope, one worker instance). Commit with the message `docs: log automated cycle reviews in progress.md`.
