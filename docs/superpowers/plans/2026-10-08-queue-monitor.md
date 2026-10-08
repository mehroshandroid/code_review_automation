# Admin Queue Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only live Queue page that can pause and resume the automated review queue (pausing stops the running review), act on items (stop, remove, move to front, retry), and set per-run LLM/compile overrides.

**Architecture:**
- **Pause state:** a singleton table `review_queue_state`.
- **Per-row data:** cancellation requests and overrides live on `review_cycle_assignments`.
- **Worker:** runs the pipeline as a cancellable task. The existing progress-sync loop sees `cancel_requested` and cancels it, and `_run_review` skips persisting cancelled runs.
- **API:** `app/api/queue.py` serves a snapshot and the actions.
- **Frontend:** `QueuePage` polls every 5 seconds.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest; React 18, Jest + RTL.

**Spec:** `docs/superpowers/specs/2026-10-08-queue-monitor-design.md`

## Global Constraints

- **Capability:** `queue.manage` belongs to `admin` only.
- **Queue state:**
  - `cancel_requested` is exactly `pause` or `stop`.
  - `failure_kind` gains `stopped`, which is never re-queued automatically.
  - The stop message is exactly `Stopped by an admin.`
- **LLM providers:** exactly `azure`, `ollama`, `claude`.
- **Compile modes:** `ALLOWED_COMPILE_MODES` from `app/automation/config.py`.
- **Overrides are editable** only when the status is `waiting_for_url`, `queued` or `failed`.
- **Snapshot limits:** 50 failed and 20 completed, each newest by `finished_at`.
- **409 messages:**
  - stop: `Only a running review can be stopped.`
  - remove: `Only a queued review can be removed from the queue.`
  - front: `Only a queued review can be moved.`
  - settings: `A running or completed review's settings can't change.`
- **Outbox event** for remove: `review_removed_from_queue`, sent to the project's PMs.
- **Polling:** the frontend refreshes every 5 seconds.
- **Commands:**
  - Backend: `cd backend && venv/bin/python -m pytest -q`.
  - Frontend: `cd frontend && CI=true npx react-scripts test --watchAll=false`.
- **Commits:** every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Pause while a review runs:** the run is cancelled within one sync interval, goes back to the **front** of the queue, and leaves **no** review row. *Task 2 `test_pause_cancels_the_running_review_and_requeues_it_first`.*
2. **Worker shutdown:** cancelling the worker itself (not a pause/stop request) must still propagate, rather than being swallowed as a pause. *Task 2 `test_worker_cancellation_is_not_mistaken_for_a_pause`.*
3. **A stopped run** must not be resurrected by `recover()` on restart or by saving the PAT. *Task 2 `test_stopped_runs_are_not_requeued`.*
4. **Moving the first item to the front** keeps it first, and the order stays stable. *Task 3 `test_front_moves_item_first`.*
5. **Non-admins** (Management, coordinator) get 403 on every queue endpoint. *Task 3 `test_queue_is_admin_only`.*

---

### Task 1: Queue state, overrides, crud

**Files:**
- Modify:
  - `backend/app/auth/permissions.py`, `backend/tests/test_permissions.py`
  - `backend/app/db/models.py`, `backend/app/db/crud.py`
  - `backend/app/automation/assignments.py`
- Create:
  - `backend/alembic/versions/f6a7b8c9d0e1_review_queue_monitor.py`
  - `backend/tests/test_db_queue.py`

**Interfaces:**
- Produces:
  - `ReviewQueueState` model
  - `crud.get_queue_state(session)`, `crud.set_queue_paused(session, paused, user_id)`
  - `crud.list_assignments_with_status(session, status, newest_finished_first=False, limit=None)`
  - `crud.count_assignments_with_status(session, status)`
  - `crud.front_of_queue_time(session) -> datetime`
  - `assignment_dicts(session, assignments, keep_order=False)`, which gains the fields `cycle_id`, `cancel_requested`, `override_llm_provider`, `override_llm_model`, `override_compile_mode`
  - `requeue_assignments` also clears `cancel_requested`

- [ ] **Step 1: Write the failing test.** In `test_permissions.py`, add `"queue.manage": {A},` to `EXPECTED`. Then create:

```python
# backend/tests/test_db_queue.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.db import crud
from app.db.models import Base


@pytest.fixture
async def s():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await crud.create_user(session, "adm", "adm@example.com", "h", "admin")
        await crud.create_project(session, "p1", "Alpha")
        await crud.create_cycle(session, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None), (".NET", None)])
        yield session
    await engine.dispose()


async def test_queue_state_defaults_and_pause(s):
    state = await crud.get_queue_state(s)
    assert state.paused is False and state.paused_by is None
    state = await crud.set_queue_paused(s, True, "adm")
    assert state.paused is True and state.paused_by == "adm" and state.paused_at is not None
    state = await crud.set_queue_paused(s, False, "adm")
    assert state.paused is False and state.paused_by is None and state.paused_at is None


async def test_list_count_and_front(s):
    now = datetime.now(timezone.utc)
    for platform, offset in (("Android", 2), ("iOS", 1)):
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="queued", queued_at=now + timedelta(minutes=offset))
    queued = await crud.list_assignments_with_status(s, "queued")
    assert [a.platform for a in queued] == ["iOS", "Android"]
    assert await crud.count_assignments_with_status(s, "waiting_for_url") == 1
    front = await crud.front_of_queue_time(s)
    android = await crud.get_assignment(s, "c1", "Android")
    await crud.update_assignment(s, android, queued_at=front)
    assert [a.platform for a in await crud.list_assignments_with_status(s, "queued")] == ["Android", "iOS"]


async def test_failed_newest_first_with_limit(s):
    now = datetime.now(timezone.utc)
    for platform, offset in (("Android", 1), ("iOS", 3), (".NET", 2)):
        a = await crud.get_assignment(s, "c1", platform)
        await crud.update_assignment(s, a, run_status="failed", finished_at=now + timedelta(minutes=offset))
    rows = await crud.list_assignments_with_status(s, "failed", newest_finished_first=True, limit=2)
    assert [a.platform for a in rows] == ["iOS", ".NET"]


async def test_requeue_clears_cancel_requested_and_skips_stopped(s):
    android = await crud.get_assignment(s, "c1", "Android")
    ios = await crud.get_assignment(s, "c1", "iOS")
    await crud.update_assignment(s, android, run_status="running", cancel_requested="stop")
    await crud.update_assignment(s, ios, run_status="failed", failure_kind="stopped")
    assert await crud.requeue_assignments(s, include_running=True) == 1
    android = await crud.get_assignment(s, "c1", "Android")
    assert android.run_status == "queued" and android.cancel_requested is None
    assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"


async def test_assignment_dicts_keep_order_and_new_fields(s):
    android = await crud.get_assignment(s, "c1", "Android")
    await crud.update_assignment(s, android, override_llm_provider="claude", override_compile_mode="static")
    ios = await crud.get_assignment(s, "c1", "iOS")
    rows = await assignment_dicts(s, [ios, android], keep_order=True)
    assert [r["platform"] for r in rows] == ["iOS", "Android"]
    assert rows[1]["override_llm_provider"] == "claude" and rows[1]["override_compile_mode"] == "static"
    assert rows[0]["cycle_id"] == "c1" and rows[0]["cancel_requested"] is None
    assert [r["platform"] for r in await assignment_dicts(s, [ios, android])] == ["Android", "iOS"]
```

- [ ] **Step 2: Run and verify it fails.** Run `venv/bin/python -m pytest tests/test_db_queue.py tests/test_permissions.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`permissions.py`:** add `"queue.manage": frozenset({ADMIN}),`.
  - **`models.py`:** in `ReviewCycleAssignment`, after `reviewer_assigned_at`, add:

```python
    cancel_requested: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "pause" | "stop"
    override_llm_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    override_llm_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    override_compile_mode: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

  and append:

```python
class ReviewQueueState(Base):
    """Singleton (id 1): whether the automated review queue is paused."""

    __tablename__ = "review_queue_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

  - **Migration:**

```python
# backend/alembic/versions/f6a7b8c9d0e1_review_queue_monitor.py
"""review queue monitor: queue pause state, per-run overrides, cancellation requests

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("cancel_requested", "override_llm_provider", "override_llm_model", "override_compile_mode")


def upgrade() -> None:
    op.create_table(
        "review_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paused_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name in _COLUMNS:
        op.add_column("review_cycle_assignments", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("review_cycle_assignments", name)
    op.drop_table("review_queue_state")
```

  - **`crud.py`:**
    - Add `timedelta` to the datetime import and `ReviewQueueState` to the models import.
    - In `requeue_assignments`, add `cancel_requested=None,` to `.values(...)`.
    - Append:

```python
# --- review queue monitor ---

_QUEUE_STATE_ID = 1


async def get_queue_state(session: AsyncSession) -> ReviewQueueState:
    state = await session.get(ReviewQueueState, _QUEUE_STATE_ID)
    if state is None:
        state = ReviewQueueState(id=_QUEUE_STATE_ID, paused=False)
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state


async def set_queue_paused(session: AsyncSession, paused: bool, user_id: Optional[str]) -> ReviewQueueState:
    state = await get_queue_state(session)
    state.paused = paused
    state.paused_by = user_id if paused else None
    state.paused_at = datetime.now(timezone.utc) if paused else None
    await session.commit()
    await session.refresh(state)
    return state


async def list_assignments_with_status(
    session: AsyncSession, status: str, newest_finished_first: bool = False, limit: Optional[int] = None,
) -> list[ReviewCycleAssignment]:
    query = select(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == status)
    query = query.order_by(ReviewCycleAssignment.finished_at.desc()) if newest_finished_first else query.order_by(*_QUEUE_ORDER)
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_assignments_with_status(session: AsyncSession, status: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == status)
    )
    return result.scalar_one()


async def front_of_queue_time(session: AsyncSession) -> datetime:
    """A queued_at that sorts before every queued item."""
    result = await session.execute(
        select(func.min(ReviewCycleAssignment.queued_at)).where(ReviewCycleAssignment.run_status == "queued")
    )
    earliest = result.scalar_one_or_none()
    return (earliest or datetime.now(timezone.utc)) - timedelta(seconds=1)
```

  - **`assignments.py`:**
    - Change the signature to `async def assignment_dicts(session, assignments, keep_order=False) -> list[dict]:`.
    - Iterate `assignments if keep_order else sorted(assignments, key=lambda a: TRACKED_PLATFORMS.index(a.platform))`.
    - Add these keys to each row dict:

```python
            "cycle_id": a.cycle_id,
            "cancel_requested": a.cancel_requested,
            "override_llm_provider": a.override_llm_provider,
            "override_llm_model": a.override_llm_model,
            "override_compile_mode": a.override_compile_mode,
```

- [ ] **Step 4: Run and verify.**
  - Run: `venv/bin/python -m pytest -q && venv/bin/alembic heads`.
  - Expected: PASS, and `f6a7b8c9d0e1 (head)`.
- [ ] **Step 5: Commit** with the message `feat: add queue pause state, per-run overrides and cancellation fields`.

---

### Task 2: Worker pause gate, cancellation, overrides

**Files:**
- Modify: `backend/app/automation/worker.py`, `backend/app/api/reviews.py`, `backend/tests/test_review_worker.py`

- [ ] **Step 1: Write the failing tests (append to `test_review_worker.py`)**

```python
def _slow_pipeline(started: asyncio.Event, persisted: list):
    async def fake_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name, *args, **kwargs):
        state = reviews_module._reviews[review_id]
        state["phase"], state["progress"] = "scoring", 30
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            if not state.get("cancelled"):
                persisted.append(review_id)
    return fake_run_review


async def _wait_until_started(started):
    await asyncio.wait_for(started.wait(), 2)


async def test_paused_queue_claims_nothing(db):
    async with db() as s:
        await crud.set_queue_paused(s, True, "adm")
    assert await worker.run_one() is False
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"


async def test_pause_cancels_the_running_review_and_requeues_it_first(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    async with db() as s:
        ios = await crud.get_assignment(s, "c1", "iOS")
        await crud.update_assignment(s, ios, run_status="queued", queued_at=datetime(2020, 1, 1, tzinfo=timezone.utc), devops_url=URL)
        android = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, android, cancel_requested="pause")
    assert await asyncio.wait_for(task, 2) is True
    async with db() as s:
        android = await crud.get_assignment(s, "c1", "Android")
        keys = await crud.list_queued_keys(s)
    assert android.run_status == "queued" and android.cancel_requested is None and android.run_progress is None
    assert keys == [("c1", "Android"), ("c1", "iOS")]
    assert persisted == []


async def test_stop_fails_the_run_without_storing_a_review(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), cancel_requested="stop")
    await asyncio.wait_for(task, 2)
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
    assert (a.run_status, a.failure_kind, a.run_error, a.cancel_requested) == ("failed", "stopped", "Stopped by an admin.", None)
    assert a.finished_at is not None and persisted == [] and failed == []


async def test_stopped_runs_are_not_requeued(db):
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="stopped")
    assert await worker.recover() == 0


async def test_worker_cancellation_is_not_mistaken_for_a_pause(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "running"


async def test_overrides_reach_the_pipeline(db, monkeypatch):
    captured = {}
    async with db() as s:
        await crud.update_assignment(
            s, await crud.get_assignment(s, "c1", "Android"),
            override_llm_provider="claude", override_compile_mode="static",
        )
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed", captured=captured))
    await worker.run_one()
    assert captured["llm_provider"] == "claude" and captured["ollama_model"] is None
    assert captured["compile_check_mode"] == "static"


async def test_cancelled_pipeline_does_not_persist(monkeypatch, tmp_path):
    calls = []

    async def record(*args, **kwargs):
        calls.append(args)

    async def slow_fetch(repo_url, pat, branch=None):
        await asyncio.sleep(10)

    monkeypatch.setattr(reviews_module, "_persist_review_result", record)
    monkeypatch.setattr(reviews_module, "fetch_repo_zip", slow_fetch)
    reviews_module._reviews["cx"] = state = reviews_module._new_review_state()
    task = asyncio.create_task(reviews_module._run_review(
        "cx", tmp_path, tmp_path / "a.zip", tmp_path / "t.xlsx", True, True, "P",
        devops_repo_url=URL, devops_pat="pat",
    ))
    await asyncio.sleep(0.05)
    state["cancelled"] = "pause"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == []
```

- [ ] **Step 2: Run and verify they fail.** Run `venv/bin/python -m pytest tests/test_review_worker.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`reviews.py`:**
    - In `_new_review_state()`, add `"cancelled": None,` after `"error_kind": None,`.
    - In `_run_review`'s `finally:`, wrap the persist call:

```python
        if not state.get("cancelled"):
            await _persist_review_result(
                review_id, project_id, project_name, platform, llm_provider, ollama_model, compile_check_mode, state,
            )
```

  - **`worker.py`:**
    - Add the constant `STOPPED = "Stopped by an admin."`.
    - Replace `_sync_progress` with:

```python
async def _sync_progress(cycle_id: str, platform: str, state: dict, run_task: asyncio.Task) -> None:
    """Copies progress to the row, and cancels the run when an admin pauses the queue or stops it."""
    while True:
        await asyncio.sleep(PROGRESS_SYNC_SECONDS)
        async with new_session() as session:
            assignment = await crud.get_assignment(session, cycle_id, platform)
            if assignment is None:
                continue
            if assignment.cancel_requested:
                state["cancelled"] = assignment.cancel_requested
                run_task.cancel()
                return
            await crud.update_assignment(session, assignment, run_phase=state.get("phase"), run_progress=state.get("progress"))


async def _cancelled(cycle_id: str, platform: str, reason: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        if reason == "pause":
            await crud.update_assignment(
                session, assignment, run_status="queued", queued_at=await crud.front_of_queue_time(session),
                cancel_requested=None, run_phase=None, run_progress=None, started_at=None,
            )
        else:
            await crud.update_assignment(
                session, assignment, run_status="failed", failure_kind="stopped", run_error=STOPPED,
                finished_at=_now(), cancel_requested=None,
            )
    logger.info("Review worker: %s/%s %s by an admin", cycle_id, platform, "paused" if reason == "pause" else "stopped")
```

    - In `_process`:
      - Compute the effective settings before creating `review_id`:

```python
    provider = assignment.override_llm_provider or org.default_llm_provider
    model = assignment.override_llm_model if assignment.override_llm_provider else org.default_ollama_model
    compile_mode = assignment.override_compile_mode or effective_compile_modes(org.auto_compile_modes)[platform]
```

      - Replace the `try:` body that starts `sync` and awaits `_run_review` with:

```python
        template_path = work_dir / "template.xlsx"
        template_path.write_bytes(template_bytes)
        run_task = asyncio.create_task(reviews_module._run_review(
            review_id, work_dir, work_dir / "android.zip", template_path, True, True, project.name,
            provider, model, compile_mode, platform,
            assignment.devops_url, pat, assignment.devops_branch, project_id=project.id,
        ))
        sync = asyncio.create_task(_sync_progress(cycle_id, platform, state, run_task))
        try:
            await run_task
        except asyncio.CancelledError:
            if not state.get("cancelled"):
                raise  # the worker itself is shutting down
```

      - After the `finally:` block, and before the `completed` check, add:

```python
    if state.get("cancelled"):
        await _cancelled(cycle_id, platform, state["cancelled"])
        return
```

    - In `run_one`, at the start:

```python
    async with new_session() as session:
        if (await crud.get_queue_state(session)).paused:
            return False
```

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: worker honours queue pause, admin stop and per-run overrides`.

---

### Task 3: Queue API

**Files:**
- Create: `backend/app/api/queue.py`, `backend/tests/test_queue_api.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_queue_api.py
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.queue as queue_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"
NOW = datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(queue_module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_project(s, "p1", "Alpha")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.update_org_settings(s, "azure", None)
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", None), ("iOS", None), (".NET", None)])
        await crud.create_cycle(s, "c2", "p1", 2026, 3, None, [("Android", None)])
        rows = {
            ("c1", "Android"): dict(run_status="running", started_at=NOW, run_phase="scoring", run_progress=40),
            ("c1", "iOS"): dict(run_status="queued", queued_at=NOW, devops_url=URL),
            ("c1", ".NET"): dict(run_status="queued", queued_at=NOW + timedelta(minutes=1), devops_url=URL),
            ("c2", "Android"): dict(run_status="failed", failure_kind="url", run_error="nope", finished_at=NOW),
        }
        for (cycle_id, platform), fields in rows.items():
            await crud.update_assignment(s, await crud.get_assignment(s, cycle_id, platform), **fields)
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_snapshot(db):
    _as("admin")
    body = client.get("/api/queue").json()
    assert body["paused"] is False and body["waiting_for_url"] == 0
    assert [(i["platform"], i["queue_position"]) for i in body["queued"]] == [("iOS", 1), (".NET", 2)]
    assert body["running"][0]["project_name"] == "Alpha" and body["running"][0]["quarter"] == 4
    assert body["failed"][0]["cycle_id"] == "c2" and body["completed"] == []
    assert body["defaults"] == {"llm_provider": "azure", "llm_model": None,
                                "compile_modes": {"Android": "compiler", ".NET": "compiler", "iOS": "static"}}


async def test_pause_requests_cancel_of_running_and_resume(db):
    _as("admin")
    body = client.post("/api/queue/pause").json()
    assert body["paused"] is True and body["paused_by_name"] == "Ada"
    assert body["running"][0]["cancel_requested"] == "pause"
    assert client.post("/api/queue/resume").json()["paused"] is False


def test_stop_only_running(db):
    _as("admin")
    assert client.post("/api/queue/items/c1/Android/stop").json()["cancel_requested"] == "stop"
    response = client.post("/api/queue/items/c1/iOS/stop")
    assert response.status_code == 409 and response.json()["detail"] == "Only a running review can be stopped."


async def test_remove_notifies_pms(db):
    _as("admin")
    body = client.post("/api/queue/items/c1/iOS/remove").json()
    assert body["run_status"] == "waiting_for_url" and body["devops_url"] == URL and body["queued_at"] is None
    assert client.post("/api/queue/items/c1/Android/remove").status_code == 409
    async with db() as s:
        rows = await crud.list_notifications(s, "review_removed_from_queue")
    assert [n.recipient_user_id for n in rows] == ["pm"] and rows[0].payload["platform"] == "iOS"


def test_front_moves_item_first(db):
    _as("admin")
    client.post("/api/queue/items/c1/.NET/front")
    assert [i["platform"] for i in client.get("/api/queue").json()["queued"]] == [".NET", "iOS"]
    client.post("/api/queue/items/c1/.NET/front")
    assert [i["platform"] for i in client.get("/api/queue").json()["queued"]] == [".NET", "iOS"]
    assert client.post("/api/queue/items/c2/Android/front").status_code == 409


def test_run_settings(db):
    _as("admin")
    body = client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": "ollama", "llm_model": " qwen ", "compile_mode": "compiler"}).json()
    assert (body["override_llm_provider"], body["override_llm_model"], body["override_compile_mode"]) == ("ollama", "qwen", "compiler")
    cleared = client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": None, "llm_model": "x", "compile_mode": None}).json()
    assert (cleared["override_llm_provider"], cleared["override_llm_model"], cleared["override_compile_mode"]) == (None, None, None)
    assert client.put("/api/queue/items/c2/Android/settings", json={"compile_mode": "local"}).status_code == 200
    assert client.put("/api/queue/items/c1/Android/settings", json={}).status_code == 409
    assert client.put("/api/queue/items/c1/iOS/settings", json={"llm_provider": "gpt"}).status_code == 400
    assert client.put("/api/queue/items/c1/iOS/settings", json={"compile_mode": "local"}).status_code == 400
    assert client.put("/api/queue/items/c9/iOS/settings", json={}).status_code == 404


@pytest.mark.parametrize("role", ["management", "coordinator", "project_manager"])
def test_queue_is_admin_only(db, role):
    _as(role, "x")
    assert client.get("/api/queue").status_code == 403
    assert client.post("/api/queue/pause").status_code == 403
    assert client.post("/api/queue/items/c1/iOS/front").status_code == 403
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.api.queue`.

- [ ] **Step 3: Implement**

```python
# backend/app/api/queue.py
"""Admin queue monitor: snapshot of automated cycle reviews, pause/resume and per-item actions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.permissions import require_permission
from app.automation.assignments import assignment_dicts
from app.automation.config import ALLOWED_COMPILE_MODES, effective_compile_modes
from app.automation.notify import cycle_payload, notify, project_manager_ids
from app.db import crud
from app.db.session import new_session
from app.quarterly import canonical_platform

router = APIRouter(dependencies=[Depends(require_permission("queue.manage"))])

LLM_PROVIDERS = ("azure", "ollama", "claude")
FAILED_LIMIT = 50
COMPLETED_LIMIT = 20


class RunSettingsBody(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    compile_mode: str | None = None


async def _items(session, assignments) -> list[dict]:
    if not assignments:
        return []
    rows = await assignment_dicts(session, assignments, keep_order=True)
    cycles = {cycle_id: await crud.get_cycle_by_id(session, cycle_id) for cycle_id in {a.cycle_id for a in assignments}}
    projects = {p.id: p for p in await crud.list_projects(session, project_ids={c.project_id for c in cycles.values()})}
    for row in rows:
        cycle = cycles[row["cycle_id"]]
        row.update(project_id=cycle.project_id, project_name=projects[cycle.project_id].name, year=cycle.year, quarter=cycle.quarter)
    return rows


async def _snapshot(session) -> dict:
    state = await crud.get_queue_state(session)
    pauser = (await crud.get_users_by_ids(session, [state.paused_by])).get(state.paused_by)
    org = await crud.get_org_settings(session)
    return {
        "paused": state.paused,
        "paused_by_name": (pauser.name or pauser.email) if pauser else None,
        "paused_at": state.paused_at.isoformat() if state.paused_at else None,
        "running": await _items(session, await crud.list_assignments_with_status(session, "running")),
        "queued": await _items(session, await crud.list_assignments_with_status(session, "queued")),
        "failed": await _items(session, await crud.list_assignments_with_status(session, "failed", True, FAILED_LIMIT)),
        "completed": await _items(session, await crud.list_assignments_with_status(session, "completed", True, COMPLETED_LIMIT)),
        "waiting_for_url": await crud.count_assignments_with_status(session, "waiting_for_url"),
        "defaults": {
            "llm_provider": org.default_llm_provider if org else "ollama",
            "llm_model": org.default_ollama_model if org else None,
            "compile_modes": effective_compile_modes(org.auto_compile_modes if org else None),
        },
    }


async def _load(session, cycle_id: str, platform: str):
    assignment = await crud.get_assignment(session, cycle_id, canonical_platform(platform) or platform)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return assignment


async def _one(session, assignment) -> dict:
    return (await _items(session, [assignment]))[0]


@router.get("/api/queue")
async def get_queue():
    async with new_session() as session:
        return await _snapshot(session)


@router.post("/api/queue/pause")
async def pause_queue(user=Depends(require_permission("queue.manage"))):
    async with new_session() as session:
        await crud.set_queue_paused(session, True, user.id)
        for assignment in await crud.list_assignments_with_status(session, "running"):
            await crud.update_assignment(session, assignment, cancel_requested="pause")
        return await _snapshot(session)


@router.post("/api/queue/resume")
async def resume_queue():
    async with new_session() as session:
        await crud.set_queue_paused(session, False, None)
        return await _snapshot(session)


@router.post("/api/queue/items/{cycle_id}/{platform}/stop")
async def stop_item(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "running":
            raise HTTPException(status_code=409, detail="Only a running review can be stopped.")
        await crud.update_assignment(session, assignment, cancel_requested="stop")
        return await _one(session, assignment)


@router.post("/api/queue/items/{cycle_id}/{platform}/remove")
async def remove_item(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "queued":
            raise HTTPException(status_code=409, detail="Only a queued review can be removed from the queue.")
        await crud.update_assignment(session, assignment, run_status="waiting_for_url", queued_at=None)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, devops_url=assignment.devops_url, link="/")
        await notify(session, "review_removed_from_queue", await project_manager_ids(session, cycle.project_id), payload)
        return await _one(session, assignment)


@router.post("/api/queue/items/{cycle_id}/{platform}/front")
async def move_to_front(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "queued":
            raise HTTPException(status_code=409, detail="Only a queued review can be moved.")
        await crud.update_assignment(session, assignment, queued_at=await crud.front_of_queue_time(session))
        return await _one(session, assignment)


@router.put("/api/queue/items/{cycle_id}/{platform}/settings")
async def set_run_settings(cycle_id: str, platform: str, body: RunSettingsBody):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status not in ("waiting_for_url", "queued", "failed"):
            raise HTTPException(status_code=409, detail="A running or completed review's settings can't change.")
        if body.llm_provider is not None and body.llm_provider not in LLM_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"llm_provider must be one of {list(LLM_PROVIDERS)}")
        if body.compile_mode is not None and body.compile_mode not in ALLOWED_COMPILE_MODES[assignment.platform]:
            raise HTTPException(status_code=400, detail=f"{body.compile_mode!r} isn't a valid compile check for {assignment.platform}")
        model = ((body.llm_model or "").strip() or None) if body.llm_provider else None
        await crud.update_assignment(
            session, assignment, override_llm_provider=body.llm_provider, override_llm_model=model,
            override_compile_mode=body.compile_mode,
        )
        return await _one(session, assignment)
```

  In `main.py`, add `from app.api.queue import router as queue_router` and `app.include_router(queue_router)`.

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add admin queue API (snapshot, pause/resume, stop/remove/front, run settings)`.

---

### Task 4: Queue page, run settings dialog, nav and route

**Files:**
- Create:
  - `frontend/src/pages/QueuePage.jsx` and its test
  - `frontend/src/components/RunSettingsDialog.jsx` and its test
- Modify:
  - `frontend/src/services/api.js`
  - `frontend/src/components/AutomationSettingsSection.jsx` (export `COMPILE_OPTIONS`)
  - `frontend/src/components/AppNav.jsx` and its test
  - `frontend/src/AppRoutes.jsx`
  - `frontend/src/testUtils/authUsers.js`, `frontend/src/context/AuthContext.jsx`
  - `frontend/src/design-system.css`

**Interfaces:**
- Produces:
  - `getQueue()`, `pauseQueue()`, `resumeQueue()`
  - `stopQueueItem(cycleId, platform)`, `removeQueueItem(cycleId, platform)`, `moveQueueItemToFront(cycleId, platform)`
  - `saveQueueItemSettings(cycleId, platform, { llmProvider, llmModel, compileMode })`
  - `PROVIDER_LABELS`, exported from `RunSettingsDialog.jsx`

- [ ] **Step 1: Write the failing tests.**
  - **Permissions:** add `"queue.manage"` to admin in `authUsers.js` and in the `AuthContext.jsx` default list.
  - **`AppNav.test.jsx`:** change the admin expectation to `["Dashboard", "Quarterly", "My reviews", "Projects", "Users", "Queue"]`. The management expectation is unchanged.

```jsx
// frontend/src/components/RunSettingsDialog.test.jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RunSettingsDialog from "./RunSettingsDialog";
import { getOllamaModels, saveQueueItemSettings } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getOllamaModels: jest.fn(), saveQueueItemSettings: jest.fn() }));

const defaults = { llm_provider: "azure", llm_model: null, compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" } };
const item = { cycle_id: "c1", platform: "Android", project_name: "Alpha", quarter: 4, year: 2026,
  override_llm_provider: null, override_llm_model: null, override_compile_mode: null };

beforeEach(() => {
  jest.resetAllMocks();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b", "llama3"]);
});

test("labels the org defaults", () => {
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByRole("option", { name: "Org default (Azure OpenAI)" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Org default (Docker lint)" })).toBeInTheDocument();
});

test("choosing Ollama shows installed models and saves overrides", async () => {
  const user = userEvent.setup();
  const onSaved = jest.fn();
  saveQueueItemSettings.mockResolvedValue({});
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={onSaved} onClose={jest.fn()} />);
  await user.selectOptions(screen.getByLabelText("LLM provider"), "ollama");
  await user.selectOptions(await screen.findByLabelText("Ollama model"), "llama3");
  await user.selectOptions(screen.getByLabelText("Compile check"), "static");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(saveQueueItemSettings).toHaveBeenCalledWith("c1", "Android", { llmProvider: "ollama", llmModel: "llama3", compileMode: "static" }));
  expect(onSaved).toHaveBeenCalled();
});

test("clear overrides sends nulls", async () => {
  const user = userEvent.setup();
  saveQueueItemSettings.mockResolvedValue({});
  render(<RunSettingsDialog item={{ ...item, override_llm_provider: "claude", override_compile_mode: "static" }} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByLabelText("LLM provider")).toHaveValue("claude");
  await user.click(screen.getByRole("button", { name: "Clear overrides" }));
  await waitFor(() => expect(saveQueueItemSettings).toHaveBeenCalledWith("c1", "Android", { llmProvider: null, llmModel: null, compileMode: null }));
});

test("shows API errors", async () => {
  const user = userEvent.setup();
  saveQueueItemSettings.mockRejectedValue({ response: { data: { detail: "A running or completed review's settings can't change." } } });
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("A running or completed review's settings can't change.")).toBeInTheDocument();
});
```

```jsx
// frontend/src/pages/QueuePage.test.jsx
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import QueuePage from "./QueuePage";
import {
  getQueue, pauseQueue, resumeQueue, stopQueueItem, removeQueueItem, moveQueueItemToFront, retryAssignment,
} from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getQueue: jest.fn(), pauseQueue: jest.fn(), resumeQueue: jest.fn(), stopQueueItem: jest.fn(),
  removeQueueItem: jest.fn(), moveQueueItemToFront: jest.fn(), retryAssignment: jest.fn(),
}));

const base = { reviewer_name: "Rae", devops_url: "https://dev.azure.com/o/p/_git/r", devops_branch: null, run_phase: null,
  run_progress: null, run_error: null, failure_kind: null, review_id: null, review_status: null, attempts: 1,
  queue_position: null, cancel_requested: null, override_llm_provider: null, override_llm_model: null,
  override_compile_mode: null, project_name: "Alpha", project_id: "p1", year: 2026, quarter: 4,
  queued_at: "2026-10-08T08:00:00Z", started_at: null, finished_at: null };
const snapshot = (extra = {}) => ({
  paused: false, paused_by_name: null, paused_at: null, waiting_for_url: 2,
  defaults: { llm_provider: "azure", llm_model: null, compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" } },
  running: [{ ...base, cycle_id: "c1", platform: "Android", run_status: "running", run_phase: "scoring", run_progress: 40, started_at: "2026-10-08T08:01:00Z" }],
  queued: [
    { ...base, cycle_id: "c1", platform: "iOS", run_status: "queued", queue_position: 1 },
    { ...base, cycle_id: "c1", platform: ".NET", run_status: "queued", queue_position: 2, override_llm_provider: "claude" },
  ],
  failed: [{ ...base, cycle_id: "c2", platform: "Android", run_status: "failed", failure_kind: "url", run_error: "Repository or branch not found.", finished_at: "2026-10-08T07:00:00Z" }],
  completed: [{ ...base, cycle_id: "c3", platform: "iOS", run_status: "completed", review_id: "rv1", started_at: "2026-10-08T06:00:00Z", finished_at: "2026-10-08T06:12:00Z" }],
  ...extra,
});

beforeEach(() => {
  jest.resetAllMocks();
  getQueue.mockResolvedValue(snapshot());
});

function renderPage() {
  return render(<MemoryRouter><QueuePage /></MemoryRouter>);
}

test("shows status, panels and items", async () => {
  renderPage();
  expect(await screen.findByText("Running")).toBeInTheDocument();
  const running = screen.getByRole("region", { name: "Running now" });
  expect(within(running).getByText("Alpha · Android · Q4 2026")).toBeInTheDocument();
  expect(within(running).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  const queued = screen.getByRole("region", { name: "Queued" });
  expect(within(queued).getAllByRole("listitem")).toHaveLength(2);
  expect(within(queued).getByText("LLM: Claude CLI (local)")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Failed" })).getByText("Repository or branch not found.")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Recently completed" })).getByRole("link", { name: "View" })).toHaveAttribute("href", "/reports/rv1");
  expect(screen.getByText(/2 waiting for a URL/)).toBeInTheDocument();
});

test("polls every 5 seconds", async () => {
  jest.useFakeTimers();
  renderPage();
  await act(async () => {});
  expect(getQueue).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(getQueue).toHaveBeenCalledTimes(2);
  jest.useRealTimers();
});

test("pause asks for confirmation, resume does not", async () => {
  const user = userEvent.setup();
  pauseQueue.mockResolvedValue(snapshot({ paused: true, paused_by_name: "Ada", paused_at: "2026-10-08T08:05:00Z" }));
  renderPage();
  await user.click(await screen.findByRole("button", { name: "Pause queue" }));
  expect(screen.getByText(/stopped and restarted from the beginning/)).toBeInTheDocument();
  getQueue.mockResolvedValue(snapshot({ paused: true, paused_by_name: "Ada", paused_at: "2026-10-08T08:05:00Z" }));
  await user.click(screen.getByRole("button", { name: "Pause" }));
  await waitFor(() => expect(pauseQueue).toHaveBeenCalled());
  expect(await screen.findByText(/Paused by Ada/)).toBeInTheDocument();
  resumeQueue.mockResolvedValue(snapshot());
  await user.click(screen.getByRole("button", { name: "Resume queue" }));
  await waitFor(() => expect(resumeQueue).toHaveBeenCalled());
});

test("item actions call the API", async () => {
  const user = userEvent.setup();
  [stopQueueItem, removeQueueItem, moveQueueItemToFront, retryAssignment].forEach((fn) => fn.mockResolvedValue({}));
  renderPage();
  const queued = await screen.findByRole("region", { name: "Queued" });
  const dotnet = within(queued).getAllByRole("listitem")[1];
  await user.click(within(dotnet).getByRole("button", { name: "Move to front" }));
  await waitFor(() => expect(moveQueueItemToFront).toHaveBeenCalledWith("c1", ".NET"));
  expect(within(within(queued).getAllByRole("listitem")[0]).queryByRole("button", { name: "Move to front" })).not.toBeInTheDocument();
  await user.click(within(dotnet).getByRole("button", { name: "Remove" }));
  await user.click(screen.getByRole("button", { name: "Remove from queue" }));
  await waitFor(() => expect(removeQueueItem).toHaveBeenCalledWith("c1", ".NET"));
  await user.click(within(screen.getByRole("region", { name: "Running now" })).getByRole("button", { name: "Stop" }));
  await user.click(screen.getByRole("button", { name: "Stop review" }));
  await waitFor(() => expect(stopQueueItem).toHaveBeenCalledWith("c1", "Android"));
  await user.click(within(screen.getByRole("region", { name: "Failed" })).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryAssignment).toHaveBeenCalledWith("c2", "Android"));
});

test("a stop in progress shows Stopping…", async () => {
  getQueue.mockResolvedValue(snapshot({ running: [{ ...snapshot().running[0], cancel_requested: "stop" }] }));
  renderPage();
  expect(await screen.findByText("Stopping…")).toBeInTheDocument();
});

test("empty states", async () => {
  getQueue.mockResolvedValue(snapshot({ running: [], queued: [], failed: [], completed: [], waiting_for_url: 0 }));
  renderPage();
  expect(await screen.findByText("Idle")).toBeInTheDocument();
  expect(screen.getByText("Nothing is running.")).toBeInTheDocument();
  expect(screen.getByText("The queue is empty.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement.** Append to `api.js`:

```js
export async function getQueue() {
  const response = await axios.get(`${API_BASE_URL}/queue`);
  return response.data;
}

export async function pauseQueue() {
  const response = await axios.post(`${API_BASE_URL}/queue/pause`);
  return response.data;
}

export async function resumeQueue() {
  const response = await axios.post(`${API_BASE_URL}/queue/resume`);
  return response.data;
}

function queueItemPath(cycleId, platform) {
  return `${API_BASE_URL}/queue/items/${cycleId}/${encodeURIComponent(platform)}`;
}

export async function stopQueueItem(cycleId, platform) {
  const response = await axios.post(`${queueItemPath(cycleId, platform)}/stop`);
  return response.data;
}

export async function removeQueueItem(cycleId, platform) {
  const response = await axios.post(`${queueItemPath(cycleId, platform)}/remove`);
  return response.data;
}

export async function moveQueueItemToFront(cycleId, platform) {
  const response = await axios.post(`${queueItemPath(cycleId, platform)}/front`);
  return response.data;
}

export async function saveQueueItemSettings(cycleId, platform, { llmProvider, llmModel, compileMode }) {
  const response = await axios.put(`${queueItemPath(cycleId, platform)}/settings`, {
    llm_provider: llmProvider, llm_model: llmModel, compile_mode: compileMode,
  });
  return response.data;
}
```

  In `AutomationSettingsSection.jsx`, change `const COMPILE_OPTIONS = {` to `export const COMPILE_OPTIONS = {`.

```jsx
// frontend/src/components/RunSettingsDialog.jsx
import { useEffect, useState } from "react";
import { COMPILE_OPTIONS } from "./AutomationSettingsSection";
import { getOllamaModels, saveQueueItemSettings } from "../services/api";

export const PROVIDER_LABELS = { azure: "Azure OpenAI", ollama: "Ollama (local)", claude: "Claude CLI (local)" };

function compileLabel(platform, mode) {
  return (COMPILE_OPTIONS[platform] || []).find(([value]) => value === mode)?.[1] || mode;
}

export default function RunSettingsDialog({ item, defaults, onSaved, onClose }) {
  const [provider, setProvider] = useState(item.override_llm_provider || "");
  const [model, setModel] = useState(item.override_llm_model || "");
  const [compile, setCompile] = useState(item.override_compile_mode || "");
  const [models, setModels] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (provider !== "ollama" || models !== null) return undefined;
    let cancelled = false;
    getOllamaModels().then((result) => { if (!cancelled) setModels(result); }).catch(() => { if (!cancelled) setModels([]); });
    return () => { cancelled = true; };
  }, [provider, models]);

  async function save(settings) {
    setSaving(true);
    setError("");
    try {
      await saveQueueItemSettings(item.cycle_id, item.platform, settings);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save run settings.");
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    save({ llmProvider: provider || null, llmModel: provider === "ollama" ? (model.trim() || null) : null, compileMode: compile || null });
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" role="dialog" aria-label="Run settings" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Run settings — {item.project_name} · {item.platform} · Q{item.quarter} {item.year}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>Applies to this review only, including retries. Leave a field on the org default to use Settings.</p>
          <div className="field">
            <label htmlFor="runProvider">LLM provider</label>
            <select id="runProvider" className="input" value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="">Org default ({PROVIDER_LABELS[defaults.llm_provider] || defaults.llm_provider})</option>
              {Object.entries(PROVIDER_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {provider === "ollama" && (
            <div className="field">
              <label htmlFor="runModel">Ollama model</label>
              {models && models.length > 0 ? (
                <select id="runModel" className="input" value={model} onChange={(event) => setModel(event.target.value)}>
                  <option value="">Choose a model…</option>
                  {models.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              ) : (
                <input id="runModel" className="input" value={model} onChange={(event) => setModel(event.target.value)} placeholder="qwen2.5-coder:7b" />
              )}
            </div>
          )}
          <div className="field">
            <label htmlFor="runCompile">Compile check</label>
            <select id="runCompile" className="input" value={compile} onChange={(event) => setCompile(event.target.value)}>
              <option value="">Org default ({compileLabel(item.platform, defaults.compile_modes[item.platform])})</option>
              {(COMPILE_OPTIONS[item.platform] || []).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => save({ llmProvider: null, llmModel: null, compileMode: null })}>Clear overrides</button>
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}
```

```jsx
// frontend/src/pages/QueuePage.jsx
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import AssignmentStatusBadge from "../components/AssignmentStatusBadge";
import { COMPILE_OPTIONS } from "../components/AutomationSettingsSection";
import RunSettingsDialog, { PROVIDER_LABELS } from "../components/RunSettingsDialog";
import {
  getQueue, moveQueueItemToFront, pauseQueue, removeQueueItem, resumeQueue, retryAssignment, stopQueueItem,
} from "../services/api";

const REFRESH_MS = 5000;
const FAILURE_KIND_LABELS = { url: "URL", system: "System", stopped: "Stopped" };

function minutesBetween(fromIso, toMs) {
  const seconds = Math.max(0, Math.round((toMs - new Date(fromIso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes}m ${seconds % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function label(item) {
  return `${item.project_name} · ${item.platform} · Q${item.quarter} ${item.year}`;
}

function OverrideChips({ item }) {
  const compile = (COMPILE_OPTIONS[item.platform] || []).find(([value]) => value === item.override_compile_mode)?.[1];
  return (
    <>
      {item.override_llm_provider && (
        <span className="tag tag-outline">
          LLM: {PROVIDER_LABELS[item.override_llm_provider]}{item.override_llm_model ? ` (${item.override_llm_model})` : ""}
        </span>
      )}
      {compile && <span className="tag tag-outline">Compile: {compile}</span>}
    </>
  );
}

function Panel({ title, empty, items, children }) {
  return (
    <section className="card queue-panel" aria-label={title}>
      <div className="queue-panel-title">{title} <span className="queue-panel-count">{items.length}</span></div>
      {items.length === 0 ? <p className="card-body" style={{ margin: 0 }}>{empty}</p> : <ul className="queue-list">{children}</ul>}
    </section>
  );
}

function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose }) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">{title}</div>
        <div className="dialog-body"><p className="card-body" style={{ margin: 0 }}>{body}</p></div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => { onClose(); onConfirm(); }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export default function QueuePage() {
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [confirm, setConfirm] = useState(null);
  const [settingsFor, setSettingsFor] = useState(null);

  const load = useCallback(() => getQueue()
    .then((result) => { setQueue(result); setUpdatedAt(Date.now()); })
    .catch(() => setError("Couldn't load the queue.")), []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  async function act(request) {
    setError("");
    try {
      await request();
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong.");
    }
  }

  const status = !queue ? null : queue.paused ? "Paused" : queue.running.length ? "Running" : "Idle";
  const defaults = queue?.defaults;

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Review queue</h1>
            <p className="page-subtitle">
              Automated quarterly reviews run one at a time, oldest first.
              {updatedAt && <> Updated {minutesBetween(new Date(updatedAt).toISOString(), now)} ago.</>}
            </p>
          </div>
          {queue && (
            <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
              <span className={`queue-status queue-status--${status.toLowerCase()}`}>{status}</span>
              {queue.paused && queue.paused_by_name && (
                <span className="quarter-card-meta">Paused by {queue.paused_by_name} · {new Date(queue.paused_at).toLocaleString()}</span>
              )}
              {queue.paused ? (
                <button type="button" className="btn btn-primary" onClick={() => act(resumeQueue)}>Resume queue</button>
              ) : (
                <button
                  type="button" className="btn"
                  onClick={() => setConfirm({
                    title: "Pause the queue?",
                    body: "No new reviews will start. The running review will be stopped and restarted from the beginning when you resume.",
                    confirmLabel: "Pause", action: pauseQueue,
                  })}
                >
                  Pause queue
                </button>
              )}
            </div>
          )}
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {defaults && (
          <p className="quarter-card-meta" style={{ margin: 0 }}>
            Defaults: {PROVIDER_LABELS[defaults.llm_provider] || defaults.llm_provider}
            {Object.entries(defaults.compile_modes).map(([platform, mode]) => ` · ${platform} ${(COMPILE_OPTIONS[platform] || []).find(([v]) => v === mode)?.[1] || mode}`).join("")}
            {" "}(change in <Link to="/settings">Settings</Link>) · {queue.waiting_for_url} waiting for a URL
          </p>
        )}

        {queue && (
          <div className="queue-grid">
            <Panel title="Running now" empty="Nothing is running." items={queue.running}>
              {queue.running.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    <AssignmentStatusBadge assignment={item} />
                    <OverrideChips item={item} />
                  </div>
                  <div className="progress-track" role="progressbar" aria-valuenow={item.run_progress ?? 0} aria-valuemin={0} aria-valuemax={100}>
                    <div className="progress-fill" style={{ width: `${item.run_progress ?? 0}%` }} />
                  </div>
                  <div className="queue-item-meta">
                    {item.started_at && <span>Running {minutesBetween(item.started_at, now)}</span>}
                    <span>Attempt {item.attempts}</span>
                    <span>Reviewer {item.reviewer_name || "—"}</span>
                  </div>
                  <div className="queue-item-actions">
                    {item.cancel_requested ? <span className="quarter-card-meta">Stopping…</span> : (
                      <button type="button" className="btn btn-ghost" onClick={() => setConfirm({
                        title: "Stop this review?",
                        body: `${label(item)} will be marked failed (stopped). You can retry it later.`,
                        confirmLabel: "Stop review", action: () => stopQueueItem(item.cycle_id, item.platform),
                      })}>Stop</button>
                    )}
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Queued" empty="The queue is empty." items={queue.queued}>
              {queue.queued.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-position">#{item.queue_position}</span>
                    <span className="queue-item-title">{label(item)}</span>
                    <OverrideChips item={item} />
                  </div>
                  <div className="queue-item-meta">
                    {item.queued_at && <span>Waiting {minutesBetween(item.queued_at, now)}</span>}
                    <span>Reviewer {item.reviewer_name || "—"}</span>
                  </div>
                  <div className="queue-item-actions">
                    {item.queue_position !== 1 && (
                      <button type="button" className="btn btn-ghost" onClick={() => act(() => moveQueueItemToFront(item.cycle_id, item.platform))}>Move to front</button>
                    )}
                    <button type="button" className="btn btn-ghost" onClick={() => setSettingsFor(item)}>Run settings</button>
                    <button type="button" className="btn btn-ghost" onClick={() => setConfirm({
                      title: "Remove from the queue?",
                      body: `${label(item)} goes back to "Waiting for URL" and the project's PMs are notified.`,
                      confirmLabel: "Remove from queue", action: () => removeQueueItem(item.cycle_id, item.platform),
                    })}>Remove</button>
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Failed" empty="No failed reviews." items={queue.failed}>
              {queue.failed.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    {item.failure_kind && <span className={`tag tag-outline failure-kind failure-kind--${item.failure_kind}`}>{FAILURE_KIND_LABELS[item.failure_kind] || item.failure_kind}</span>}
                    <OverrideChips item={item} />
                  </div>
                  <div className="run-error">{item.run_error}</div>
                  <div className="queue-item-meta">{item.finished_at && <span>Failed {new Date(item.finished_at).toLocaleString()}</span>}</div>
                  <div className="queue-item-actions">
                    <button type="button" className="btn btn-ghost" onClick={() => act(() => retryAssignment(item.cycle_id, item.platform))}>Retry</button>
                    <button type="button" className="btn btn-ghost" onClick={() => setSettingsFor(item)}>Run settings</button>
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Recently completed" empty="No completed reviews yet." items={queue.completed}>
              {queue.completed.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    <AssignmentStatusBadge assignment={item} />
                  </div>
                  <div className="queue-item-meta">
                    {item.finished_at && <span>Finished {new Date(item.finished_at).toLocaleString()}</span>}
                    {item.started_at && item.finished_at && <span>Took {minutesBetween(item.started_at, new Date(item.finished_at).getTime())}</span>}
                  </div>
                  <div className="queue-item-actions">
                    {item.review_id && <Link to={`/reports/${item.review_id}`} className="btn btn-ghost">View</Link>}
                  </div>
                </li>
              ))}
            </Panel>
          </div>
        )}
      </main>

      {confirm && (
        <ConfirmDialog
          title={confirm.title} body={confirm.body} confirmLabel={confirm.confirmLabel}
          onConfirm={() => act(confirm.action)} onClose={() => setConfirm(null)}
        />
      )}
      {settingsFor && defaults && (
        <RunSettingsDialog item={settingsFor} defaults={defaults} onSaved={load} onClose={() => setSettingsFor(null)} />
      )}
    </div>
  );
}
```

  - **`AppNav.jsx`:** add after the Users link: `{ to: "/queue", label: "Queue", show: (user) => hasAny(user, ["queue.manage"]) },`.
  - **`AppRoutes.jsx`:** import `QueuePage`, and after the `/users` route add `<Route path="/queue" element={<RequirePermission anyOf={["queue.manage"]}><QueuePage /></RequirePermission>} />`.
  - **`design-system.css`:** append:

```css
/* — review queue monitor — */
.queue-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); align-items: start; }
@media (max-width: 1000px) { .queue-grid { grid-template-columns: 1fr; } }
.queue-panel { padding: 20px; display: grid; gap: var(--space-3); }
.queue-panel-title { font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.queue-panel-count { font-size: 12px; font-weight: 600; color: var(--color-text-muted); background: var(--color-surface); border-radius: 999px; padding: 1px 8px; }
.queue-list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
.queue-item { border: 1px solid var(--color-divider); border-radius: 10px; padding: 12px 14px; display: grid; gap: 6px; }
.queue-item-main { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.queue-item-title { font-weight: 600; font-size: 14px; }
.queue-item-meta { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--color-text-muted); }
.queue-item-actions { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
.queue-position { font-weight: 700; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.queue-status { font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
.queue-status--running { background: color-mix(in srgb, #2e9e5b 15%, var(--color-bg)); color: #1f6e3f; }
.queue-status--idle { background: var(--color-surface); color: var(--color-text-muted); }
.queue-status--paused { background: color-mix(in srgb, #e0b400 20%, var(--color-bg)); color: #6b5300; }
.progress-track { height: 6px; border-radius: 999px; background: var(--color-surface); overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-accent); transition: width 0.4s ease; }
.failure-kind--url { color: var(--color-brand-coral); border-color: var(--color-brand-coral); }
.failure-kind--stopped { color: var(--color-text-muted); }
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add admin Queue page with live status, pause/resume, item actions and run settings`.

---

### Task 5: Docker smoke test and progress log

- [ ] **Step 1: Run both suites in full.**
- [ ] **Step 2: Back up the database and rebuild.**
  - `pg_dump` to `<scratchpad>/codereviews-before-queue-monitor.sql`.
  - Rebuild the backend and frontend.
  - Confirm `Running upgrade e5f6a7b8c9d0 -> f6a7b8c9d0e1` and "Review worker started".
- [ ] **Step 3: Run the API smoke test with temporary data only. No PAT is saved and no real run happens.**
  1. As admin, `GET /api/queue` returns 200 with the real counts.
  2. Pause, then confirm `paused` is true.
  3. Create `Smoke Project` with Android and a smoke PM, and start a cycle.
  4. Submit a URL as the smoke PM, and confirm it stays `queued` for 10 seconds because the queue is paused.
  5. Run settings: set claude/static and check that it round-trips. Move to front, then Remove, and confirm `waiting_for_url` plus an outbox row for the PM.
  6. Resubmit the URL, then resume the queue. Within about 10 seconds the run fails with "No usable Azure DevOps PAT…" (a system failure), which proves the resume.
  7. Clean up as before: the project, the smoke users and the `Smoke Project` outbox rows. Confirm the counts match the start, and that the queue is left **resumed**.
- [ ] **Step 4: Update `progress.md`** with Phase 11 (queue monitor and the status/padding fixes), then commit with the message `docs: log admin queue monitor in progress.md`.
