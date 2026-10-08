# Email Delivery, Stage Tracker & Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Deliver `notification_outbox` emails through Graph, SMTP or log-only, configured by environment.
- Show a 4-stage tracker per platform.
- Let coordinators send manual reminders.
- Give admins an Email section: status, test email, recent emails, and retry.

**Architecture:**
- **Mailer:** `app/email/` holds config, templates, transport and sender. The sender loop starts in the lifespan next to the review worker. It wakes every 15 seconds, or immediately via `wake()`, which `notify()` calls after inserting rows.
- **Stage tracker:** the stage data comes from the existing assignment dict, extended with timestamps.
- **Frontend:** reuses the Manage dialog and quarter cards, and adds a Settings section.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, `smtplib`, `msal`, `httpx`, pytest; React 18, Jest + RTL.

**Spec:** `docs/superpowers/specs/2026-10-08-email-and-stage-tracker-design.md`

## Global Constraints

- **`EMAIL_MODE`:** one of `log` (default), `graph`, `smtp`.
- **Outbox `status` values:** exactly `pending`, `sent`, `failed`, `logged`, `skipped`.
- **Retries:** after a failure, `next_attempt_at = now + 2^attempts minutes`. The 5th failure sets `failed`.
- **Sender loop:** polls every 15 seconds, processing a batch of 20.
- **Capability:** `email.manage` belongs to admin only.
- **Reminders:** handled by `POST .../remind` with `{target: "pm" | "reviewer"}`, under `cycles.initiate`. The 409 message is `A reminder isn't needed at this stage.`
- **Secrets** (SMTP password, Graph secret) never appear in API responses, log lines or `last_error`.
- **Commands:**
  - Backend: `cd backend && venv/bin/python -m pytest -q`.
  - Frontend: `cd frontend && CI=true npx react-scripts test --watchAll=false`.
- **Commits:** every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Turning real email on must not blast old rows:** the migration marks every existing outbox row `skipped`. *Task 1 `test_migration_sql_skips_existing_rows`.*
2. **A broken SMTP/Graph config:** emails are retried with backoff, then `failed`, with a readable error that contains no password or secret. *Task 3 `test_failures_back_off_then_fail` and `test_smtp_error_hides_password`.*
3. **Deactivated recipients:** they never get mail (`skipped`). *Task 3 `test_inactive_recipient_is_skipped`.*
4. **A coordinator reminding at the wrong stage** gets 409, not a confusing email. *Task 4 `test_remind_rules`.*
5. **Untrusted text in templates:** a project name or error text containing HTML is escaped in the email body. *Task 2 `test_payload_is_escaped`.*

---

### Task 1: Data, capability, assignment fields

**Files:**
- Modify:
  - `backend/app/auth/permissions.py`, `backend/tests/test_permissions.py`
  - `backend/app/db/models.py`, `backend/app/db/crud.py`
  - `backend/app/automation/assignments.py`
- Create:
  - `backend/alembic/versions/a7b8c9d0e1f2_email_delivery_and_reminders.py`
  - `backend/tests/test_db_email.py`

**Interfaces:**
- Produces:
  - crud:
    - `list_due_notifications(session, now, limit)`
    - `get_notification(session, id)`
    - `list_recent_notifications(session, limit)`
    - `update_notification(session, row, **fields)`
    - `get_review_approved_times(session, ids) -> dict`
  - `add_notifications` now **returns** the created rows.
  - The assignment dict gains `url_submitted_at`, `review_approved_at`, `pm_reminded_at`, `reviewer_reminded_at`.
  - `SKIP_EXISTING_SQL`, a module constant in the migration.

- [ ] **Step 1: Write the failing test.** Add `"email.manage": {A},` to `EXPECTED` in `test_permissions.py`. Then create:

```python
# backend/tests/test_db_email.py
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation.assignments import assignment_dicts
from app.db import crud
from app.db.models import Base

NOW = datetime.now(timezone.utc)


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = async_sessionmaker(engine, expire_on_commit=False)
    m.engine = engine
    async with m() as s:
        await crud.create_user(s, "u1", "u1@example.com", "h", "reviewer")
    yield m
    await engine.dispose()


async def test_add_notifications_returns_rows_with_pending_status(maker):
    async with maker() as s:
        rows = await crud.add_notifications(s, "test_email", ["u1"], {"x": 1})
    assert len(rows) == 1 and rows[0].status == "pending" and rows[0].attempts == 0


async def test_due_and_recent_listing(maker):
    async with maker() as s:
        due, later, sent = [r for rows in [await crud.add_notifications(s, "e", ["u1"], {}) for _ in range(3)] for r in rows]
        await crud.update_notification(s, later, next_attempt_at=NOW + timedelta(minutes=5))
        await crud.update_notification(s, sent, status="sent")
        assert [r.id for r in await crud.list_due_notifications(s, NOW, 10)] == [due.id]
        assert len(await crud.list_recent_notifications(s, 2)) == 2
        assert (await crud.get_notification(s, due.id)).id == due.id


async def test_migration_sql_skips_existing_rows(maker):
    spec = importlib.util.spec_from_file_location(
        "mig", Path(__file__).parent.parent / "alembic/versions/a7b8c9d0e1f2_email_delivery_and_reminders.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with maker() as s:
        await crud.add_notifications(s, "old", ["u1"], {})
    async with maker.engine.begin() as conn:
        await conn.execute(text(module.SKIP_EXISTING_SQL))
    async with maker() as s:
        assert [r.status for r in await crud.list_recent_notifications(s, 10)] == ["skipped"]


async def test_assignment_dict_has_stage_timestamps(maker):
    async with maker() as s:
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "u1")])
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform="Android", status="approved", project_name="Alpha",
            created_at=NOW, completed_at=NOW, total_score_pct=90, llm_provider="azure", llm_model=None,
            compile_check_mode="compiler", source="devops", workbook_path=None, result_data={}, approved_at=NOW,
        )
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, url_submitted_at=NOW, review_id="r1", pm_reminded_at=NOW, run_status="completed")
        row = (await assignment_dicts(s, [a]))[0]
    assert row["url_submitted_at"] and row["review_approved_at"] and row["pm_reminded_at"]
    assert row["reviewer_reminded_at"] is None
```

- [ ] **Step 2: Run and verify it fails.** Run `venv/bin/python -m pytest tests/test_db_email.py tests/test_permissions.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`permissions.py`:** add `"email.manage": frozenset({ADMIN}),`.
  - **`models.py`:** in `NotificationOutbox`, after `sent_at`, add:

```python
    # pending -> sent | logged (log mode) | failed (after retries) | skipped (stale or inactive recipient)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

  and in `ReviewCycleAssignment`, after `override_compile_mode`:

```python
    pm_reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

  - **Migration:**

```python
# backend/alembic/versions/a7b8c9d0e1f2_email_delivery_and_reminders.py
"""email delivery state on the outbox; reminder timestamps on assignments

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Rows recorded before delivery existed are stale -- never send them.
SKIP_EXISTING_SQL = "UPDATE notification_outbox SET status = 'skipped'"


def upgrade() -> None:
    op.add_column("notification_outbox", sa.Column("status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("notification_outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notification_outbox", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("notification_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification_outbox", sa.Column("subject", sa.String(), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("pm_reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_cycle_assignments", sa.Column("reviewer_reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(SKIP_EXISTING_SQL)


def downgrade() -> None:
    op.drop_column("review_cycle_assignments", "reviewer_reminded_at")
    op.drop_column("review_cycle_assignments", "pm_reminded_at")
    for name in ("subject", "next_attempt_at", "last_error", "attempts", "status"):
        op.drop_column("notification_outbox", name)
```

  - **`crud.py`:** make `add_notifications` return the rows:

```python
async def add_notifications(session: AsyncSession, event: str, recipient_ids: list[str], payload: dict) -> list[NotificationOutbox]:
    now = datetime.now(timezone.utc)
    rows = [
        NotificationOutbox(id=str(uuid.uuid4()), event=event, recipient_user_id=recipient_id, payload=payload, created_at=now)
        for recipient_id in recipient_ids
    ]
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows
```

  and append:

```python
# --- email delivery ---

async def list_due_notifications(session: AsyncSession, now: datetime, limit: int) -> list[NotificationOutbox]:
    result = await session.execute(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status == "pending",
            or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= now),
        )
        .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_notification(session: AsyncSession, notification_id: str) -> Optional[NotificationOutbox]:
    return await session.get(NotificationOutbox, notification_id)


async def list_recent_notifications(session: AsyncSession, limit: int) -> list[NotificationOutbox]:
    result = await session.execute(
        select(NotificationOutbox).order_by(NotificationOutbox.created_at.desc(), NotificationOutbox.id).limit(limit)
    )
    return list(result.scalars().all())


async def update_notification(session: AsyncSession, row: NotificationOutbox, **fields) -> NotificationOutbox:
    for name, value in fields.items():
        setattr(row, name, value)
    await session.commit()
    await session.refresh(row)
    return row


async def get_review_approved_times(session: AsyncSession, review_ids: list[str]) -> dict:
    ids = [review_id for review_id in set(review_ids) if review_id]
    if not ids:
        return {}
    result = await session.execute(select(PlatformReview.id, PlatformReview.approved_at).where(PlatformReview.id.in_(ids)))
    return {review_id: approved_at for review_id, approved_at in result.all()}
```

  - **`assignments.py`:**
    - After `statuses = …`, add `approved_times = await crud.get_review_approved_times(session, [a.review_id for a in assignments])`.
    - Add these row keys:

```python
            "url_submitted_at": _iso(a.url_submitted_at),
            "review_approved_at": _iso(approved_times.get(a.review_id)),
            "pm_reminded_at": _iso(a.pm_reminded_at),
            "reviewer_reminded_at": _iso(a.reviewer_reminded_at),
```

- [ ] **Step 4: Run the full backend suite and check the migration head.**
  - Run: `venv/bin/python -m pytest -q && venv/bin/alembic heads`.
  - Expected: PASS, and `a7b8c9d0e1f2 (head)`.
- [ ] **Step 5: Commit** with the message `feat: add email delivery state, reminder timestamps and stage fields`.

---

### Task 2: Email config and templates

**Files:**
- Create:
  - `backend/app/email/__init__.py` (empty), `backend/app/email/config.py`, `backend/app/email/templates.py`
  - `backend/tests/test_email_config_templates.py`

**Interfaces:**
- Produces:
  - `EmailSettings` (a dataclass), `email_settings()`, `config_problems(settings) -> list[str]`, `describe(settings=None) -> dict`
  - `render(event, payload, recipient_name, base_url) -> tuple[str, str, str]`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_email_config_templates.py
import pytest

from app.email.config import config_problems, describe, email_settings
from app.email.templates import render

BASE = "https://codeassure.example.com"
PAYLOAD = {"project_name": "Moove", "platform": "iOS", "year": 2026, "quarter": 4, "link": "/reports/r1"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("EMAIL_MODE", "EMAIL_FROM", "EMAIL_FROM_NAME", "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
                 "AZURE_AD_TENANT_ID", "AZURE_AD_CLIENT_ID", "AZURE_AD_CLIENT_SECRET", "SMTP_HOST", "SMTP_PORT",
                 "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_STARTTLS", "FRONTEND_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_log_mode_and_configured():
    s = email_settings()
    assert (s.mode, s.from_name, s.base_url, s.smtp_port, s.smtp_starttls) == ("log", "CodeAssure", "http://localhost:3000", 587, True)
    assert describe() == {"mode": "log", "from_address": None, "from_name": "CodeAssure", "base_url": "http://localhost:3000",
                          "configured": True, "problems": []}


def test_graph_falls_back_to_sign_in_app(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "graph")
    monkeypatch.setenv("EMAIL_FROM", "codeassure@example.com")
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "t")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "c")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "super-secret")
    s = email_settings()
    assert (s.graph_tenant_id, s.graph_client_id, s.graph_client_secret) == ("t", "c", "super-secret")
    assert config_problems(s) == []
    assert "super-secret" not in str(describe())


def test_problems_listed_for_incomplete_modes(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    assert config_problems(email_settings()) == ["EMAIL_FROM is not set.", "SMTP_HOST is not set."]
    monkeypatch.setenv("EMAIL_MODE", "graph")
    assert len(config_problems(email_settings())) == 4
    monkeypatch.setenv("EMAIL_MODE", "carrier-pigeon")
    assert config_problems(email_settings()) == ["EMAIL_MODE must be log, graph or smtp (got 'carrier-pigeon')."]


def test_smtp_password_never_described(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    assert "hunter2" not in str(describe())


@pytest.mark.parametrize("event,subject", [
    ("cycle_initiated", "Action needed: add DevOps URLs for Moove · Q4 2026 review"),
    ("reviewer_assigned", "You're the reviewer for Moove · iOS (Q4 2026)"),
    ("reviewer_unassigned", "You're no longer reviewing Moove · iOS (Q4 2026)"),
    ("review_ready", "Ready for your review: Moove · iOS (Q4 2026)"),
    ("review_failed", "Automatic review failed: Moove · iOS (Q4 2026)"),
    ("review_finalized", "Review finalized: Moove · iOS (Q4 2026) — 87.5%"),
    ("review_removed_from_queue", "Please check the DevOps URL for Moove · iOS (Q4 2026)"),
    ("reminder_pm", "Reminder: add the DevOps URL for Moove · iOS (Q4 2026)"),
    ("reminder_reviewer", "Reminder: Moove · iOS (Q4 2026) is waiting for your review"),
    ("test_email", "CodeAssure test email"),
    ("something_new", "CodeAssure notification"),
])
def test_subjects(event, subject):
    assert render(event, {**PAYLOAD, "total_score_pct": 87.5}, "Rae", BASE)[0] == subject


def test_finalized_without_score():
    assert render("review_finalized", PAYLOAD, "Rae", BASE)[0] == "Review finalized: Moove · iOS (Q4 2026)"


def test_body_has_greeting_link_and_text_version():
    subject, html, text = render("review_ready", PAYLOAD, "Rae", BASE)
    assert "Hi Rae," in html and f'href="{BASE}/reports/r1"' in html
    assert "Hi Rae," in text and f"{BASE}/reports/r1" in text


def test_payload_is_escaped():
    evil = {**PAYLOAD, "project_name": "<script>alert(1)</script>", "error": "<b>boom</b>"}
    _, html, _ = render("review_failed", evil, "<i>Rae</i>", BASE)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>boom</b>" not in html and "<i>Rae</i>" not in html
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.email`.

- [ ] **Step 3: Implement**

```python
# backend/app/email/config.py
"""Email delivery settings from the environment (secrets stay in deployment config)."""
import os
from dataclasses import dataclass

MODES = ("log", "graph", "smtp")


@dataclass(frozen=True)
class EmailSettings:
    mode: str
    from_address: str | None
    from_name: str
    base_url: str
    graph_tenant_id: str | None
    graph_client_id: str | None
    graph_client_secret: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_starttls: bool


def _env(name: str, fallback: str | None = None) -> str | None:
    value = (os.environ.get(name) or "").strip()
    if not value and fallback:
        value = (os.environ.get(fallback) or "").strip()
    return value or None


def email_settings() -> EmailSettings:
    try:
        port = int(os.environ.get("SMTP_PORT") or "587")
    except ValueError:
        port = 0
    return EmailSettings(
        mode=(os.environ.get("EMAIL_MODE") or "log").strip().lower(),
        from_address=_env("EMAIL_FROM"),
        from_name=_env("EMAIL_FROM_NAME") or "CodeAssure",
        base_url=(os.environ.get("FRONTEND_BASE_URL") or "http://localhost:3000").rstrip("/"),
        graph_tenant_id=_env("GRAPH_TENANT_ID", "AZURE_AD_TENANT_ID"),
        graph_client_id=_env("GRAPH_CLIENT_ID", "AZURE_AD_CLIENT_ID"),
        graph_client_secret=_env("GRAPH_CLIENT_SECRET", "AZURE_AD_CLIENT_SECRET"),
        smtp_host=_env("SMTP_HOST"),
        smtp_port=port,
        smtp_username=_env("SMTP_USERNAME"),
        smtp_password=os.environ.get("SMTP_PASSWORD") or None,
        smtp_starttls=(os.environ.get("SMTP_STARTTLS") or "true").strip().lower() != "false",
    )


def config_problems(settings: EmailSettings) -> list[str]:
    if settings.mode not in MODES:
        return [f"EMAIL_MODE must be log, graph or smtp (got {settings.mode!r})."]
    if settings.mode == "log":
        return []
    problems = [] if settings.from_address else ["EMAIL_FROM is not set."]
    if settings.mode == "graph":
        for value, name, fallback in (
            (settings.graph_tenant_id, "GRAPH_TENANT_ID", "AZURE_AD_TENANT_ID"),
            (settings.graph_client_id, "GRAPH_CLIENT_ID", "AZURE_AD_CLIENT_ID"),
            (settings.graph_client_secret, "GRAPH_CLIENT_SECRET", "AZURE_AD_CLIENT_SECRET"),
        ):
            if not value:
                problems.append(f"{name} (or {fallback}) is not set.")
    else:
        if not settings.smtp_host:
            problems.append("SMTP_HOST is not set.")
        if settings.smtp_port <= 0:
            problems.append("SMTP_PORT must be a number.")
    return problems


def describe(settings: EmailSettings | None = None) -> dict:
    """A safe summary for the admin UI -- never includes secrets."""
    settings = settings or email_settings()
    problems = config_problems(settings)
    return {
        "mode": settings.mode, "from_address": settings.from_address, "from_name": settings.from_name,
        "base_url": settings.base_url, "configured": not problems, "problems": problems,
    }
```

```python
# backend/app/email/templates.py
"""Subjects and bodies for workflow emails. Payload values are untrusted: always escaped in HTML."""
from html import escape


def _where(p: dict) -> str:
    platform = f" · {p.get('platform')}" if p.get("platform") else ""
    return f"{p.get('project_name')}{platform} (Q{p.get('quarter')} {p.get('year')})"


def _score(p: dict) -> str:
    score = p.get("total_score_pct")
    return f" — {score:g}%" if isinstance(score, (int, float)) else ""


def _failure_hint(p: dict) -> str:
    if p.get("failure_kind") == "url":
        return " The project's PM may need to correct the repository URL."
    return " An admin should check the setup (DevOps PAT, compile and LLM services)."


# event -> (subject, message, button label)
_EVENTS = {
    "cycle_initiated": (
        lambda p: f"Action needed: add DevOps URLs for {p.get('project_name')} · Q{p.get('quarter')} {p.get('year')} review",
        lambda p: f"The Q{p.get('quarter')} {p.get('year')} code review for {p.get('project_name')} has started. "
                  "Please add the Azure DevOps repository URL for each platform so the automatic review can run.",
        "Add repository URLs",
    ),
    "reviewer_assigned": (
        lambda p: f"You're the reviewer for {_where(p)}",
        lambda p: f"You've been assigned to review {_where(p)}. You'll get another email when the automatic review is ready.",
        "Open CodeAssure",
    ),
    "reviewer_unassigned": (
        lambda p: f"You're no longer reviewing {_where(p)}",
        lambda p: f"{_where(p)} has been reassigned to another reviewer. No action is needed from you.",
        "Open CodeAssure",
    ),
    "review_ready": (
        lambda p: f"Ready for your review: {_where(p)}",
        lambda p: f"The automatic review of {_where(p)} has finished. Please check the scores, add remarks and approve it.",
        "Open the review",
    ),
    "review_failed": (
        lambda p: f"Automatic review failed: {_where(p)}",
        lambda p: f"The automatic review of {_where(p)} couldn't finish: {p.get('error') or 'unknown error'}." + _failure_hint(p),
        "Open the queue",
    ),
    "review_finalized": (
        lambda p: f"Review finalized: {_where(p)}{_score(p)}",
        lambda p: f"The reviewer has approved the code review of {_where(p)}{_score(p).replace(' — ', ' with a score of ')}. "
                  "The scores and feedback are ready to view.",
        "View the results",
    ),
    "review_removed_from_queue": (
        lambda p: f"Please check the DevOps URL for {_where(p)}",
        lambda p: f"An admin took {_where(p)} out of the review queue. Please check the repository URL and save it again.",
        "Check the URL",
    ),
    "reminder_pm": (
        lambda p: f"Reminder: add the DevOps URL for {_where(p)}",
        lambda p: f"The quarterly review of {_where(p)} is waiting for its Azure DevOps repository URL.",
        "Add the URL",
    ),
    "reminder_reviewer": (
        lambda p: f"Reminder: {_where(p)} is waiting for your review",
        lambda p: f"The automatic review of {_where(p)} is ready and waiting for your feedback and approval.",
        "Open the review",
    ),
    "test_email": (
        lambda p: "CodeAssure test email",
        lambda p: "This is a test email from CodeAssure. If you're reading it, email delivery is working.",
        "Open CodeAssure",
    ),
}
_GENERIC = (lambda p: "CodeAssure notification", lambda p: "There's an update for you in CodeAssure.", "Open CodeAssure")


def render(event: str, payload: dict, recipient_name: str | None, base_url: str) -> tuple[str, str, str]:
    subject_fn, message_fn, button = _EVENTS.get(event, _GENERIC)
    subject = subject_fn(payload)
    message = message_fn(payload)
    link = f"{base_url}{payload.get('link') or '/'}"
    greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"
    footer = "Sent automatically by CodeAssure. You're receiving this because of your role in a code review."
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2933;max-width:560px">'
        f'<p style="font-weight:700;font-size:16px;margin:0 0 16px">CodeAssure</p>'
        f"<p>{escape(greeting)}</p>"
        f"<p>{escape(message)}</p>"
        f'<p><a href="{escape(link)}" style="display:inline-block;background:#1B3A6B;color:#fff;padding:10px 16px;'
        f'border-radius:6px;text-decoration:none">{escape(button)}</a></p>'
        f'<p style="color:#6b7280;font-size:12px;margin-top:24px">{escape(footer)}</p>'
        "</div>"
    )
    text = f"{greeting}\n\n{message}\n\n{button}: {link}\n\n{footer}\n"
    return subject, html, text
```

- [ ] **Step 4: Run and verify it passes.** Then run the full suite.
- [ ] **Step 5: Commit** with the message `feat: add email configuration from environment and workflow email templates`.

---

### Task 3: Transport, sender loop, wake from notify, lifespan

**Files:**
- Create:
  - `backend/app/email/transport.py`, `backend/app/email/sender.py`
  - `backend/tests/test_email_sender.py`
- Modify:
  - `backend/app/automation/notify.py` (return the rows and `wake()`)
  - `backend/main.py`, `docker-compose.yml`

**Interfaces:**
- Produces:
  - `EmailError`, `async send(settings, to_address, to_name, subject, html, text)`
  - `deliver_due(limit=20) -> int`, `wake()`, `email_loop()`, `start_email_worker()`, `MAX_ATTEMPTS = 5`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_email_sender.py
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.email.sender as sender
import app.email.transport as transport
from app.automation.notify import notify
from app.db import crud
from app.db.models import Base
from app.email.config import email_settings
from app.email.transport import EmailError


@pytest.fixture
async def db(monkeypatch):
    for name in ("EMAIL_MODE", "EMAIL_FROM", "SMTP_HOST", "SMTP_PASSWORD", "SMTP_USERNAME", "SMTP_STARTTLS"):
        monkeypatch.delenv(name, raising=False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(sender, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "u1", "rae@example.com", "h", "reviewer", name="Rae")
        await crud.create_user(s, "off", "off@example.com", "h", "reviewer")
    yield maker
    await engine.dispose()


async def _queue(maker, recipient="u1", event="review_ready"):
    async with maker() as s:
        return (await crud.add_notifications(s, event, [recipient], {"project_name": "Moove", "platform": "iOS", "year": 2026, "quarter": 4, "link": "/reports/r1"}))[0]


async def _row(maker, row_id):
    async with maker() as s:
        return await crud.get_notification(s, row_id)


async def test_log_mode_marks_logged(db):
    row = await _queue(db)
    assert await sender.deliver_due() == 1
    row = await _row(db, row.id)
    assert row.status == "logged" and row.sent_at is not None and row.subject == "Ready for your review: Moove · iOS (Q4 2026)"


async def test_success_marks_sent(db, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("EMAIL_FROM", "codeassure@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    sent = []

    async def fake_send(settings, to_address, to_name, subject, html, text):
        sent.append((to_address, to_name, subject))

    monkeypatch.setattr(sender, "send", fake_send)
    row = await _queue(db)
    await sender.deliver_due()
    assert sent == [("rae@example.com", "Rae", "Ready for your review: Moove · iOS (Q4 2026)")]
    assert (await _row(db, row.id)).status == "sent"


async def test_failures_back_off_then_fail(db, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("EMAIL_FROM", "codeassure@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    async def broken(*args, **kwargs):
        raise EmailError("SMTP send failed: SMTPAuthenticationError")

    monkeypatch.setattr(sender, "send", broken)
    row = await _queue(db)
    await sender.deliver_due()
    first = await _row(db, row.id)
    assert (first.status, first.attempts, first.last_error) == ("pending", 1, "SMTP send failed: SMTPAuthenticationError")
    assert first.next_attempt_at is not None
    assert await sender.deliver_due() == 0  # not due yet
    for _ in range(4):
        async with db() as s:
            r = await crud.get_notification(s, row.id)
            await crud.update_notification(s, r, next_attempt_at=None)
        await sender.deliver_due()
    final = await _row(db, row.id)
    assert final.status == "failed" and final.attempts == 5


async def test_unconfigured_mode_counts_as_failure(db, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "graph")
    row = await _queue(db)
    await sender.deliver_due()
    assert "EMAIL_FROM is not set." in (await _row(db, row.id)).last_error


async def test_inactive_recipient_is_skipped(db):
    async with db() as s:
        await crud.update_user(s, "off", is_active=False)
    row = await _queue(db, recipient="off")
    await sender.deliver_due()
    assert (await _row(db, row.id)).status == "skipped"


async def test_wake_triggers_delivery(db, monkeypatch):
    monkeypatch.setattr(sender, "POLL_SECONDS", 60)
    task = asyncio.create_task(sender.email_loop())
    await asyncio.sleep(0.05)
    row = await _queue(db)
    sender.wake()
    for _ in range(50):
        await asyncio.sleep(0.02)
        if (await _row(db, row.id)).status == "logged":
            break
    task.cancel()
    assert (await _row(db, row.id)).status == "logged"


async def test_notify_wakes_the_sender(db, monkeypatch):
    woke = []
    monkeypatch.setattr(sender, "wake", lambda: woke.append(True))
    async with db() as s:
        rows = await notify(s, "test_email", ["u1"], {})
    assert len(rows) == 1 and woke == [True]


def test_smtp_builds_multipart_and_uses_starttls(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def starttls(self, context=None):
            calls.append(("starttls",))
        def login(self, user, password):
            calls.append(("login", user))
        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"], message.get_content_type()))

    monkeypatch.setattr(transport.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("EMAIL_FROM", "codeassure@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "codeassure@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    asyncio.run(transport.send(email_settings(), "rae@example.com", "Rae", "Hi", "<p>x</p>", "x"))
    assert calls[0] == ("connect", "smtp.example.com", 587)
    assert ("starttls",) in calls and ("login", "codeassure@example.com") in calls
    assert calls[-1] == ("send", "Rae <rae@example.com>", "Hi", "multipart/alternative")


def test_smtp_error_hides_password(monkeypatch):
    class Refusing:
        def __init__(self, *args, **kwargs):
            raise transport.smtplib.SMTPAuthenticationError(535, b"5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(transport.smtplib, "SMTP", Refusing)
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("EMAIL_FROM", "codeassure@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    with pytest.raises(EmailError) as exc:
        asyncio.run(transport.send(email_settings(), "rae@example.com", "Rae", "Hi", "<p>x</p>", "x"))
    assert "hunter2" not in str(exc.value) and "SMTPAuthenticationError" in str(exc.value)


def test_graph_posts_send_mail_with_token(monkeypatch):
    posted = {}

    class FakeApp:
        def __init__(self, client_id, authority, client_credential):
            posted["authority"] = authority
        def acquire_token_for_client(self, scopes):
            return {"access_token": "tok"}

    class FakeResponse:
        status_code = 202
        text = ""

    class FakeClient:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return False
        async def post(self, url, json, headers):
            posted.update(url=url, json=json, auth=headers["Authorization"])
            return FakeResponse()

    monkeypatch.setattr(transport.msal, "ConfidentialClientApplication", FakeApp)
    monkeypatch.setattr(transport.httpx, "AsyncClient", FakeClient)
    for name, value in (("EMAIL_MODE", "graph"), ("EMAIL_FROM", "codeassure@example.com"), ("GRAPH_TENANT_ID", "t"),
                        ("GRAPH_CLIENT_ID", "c"), ("GRAPH_CLIENT_SECRET", "s3cret")):
        monkeypatch.setenv(name, value)
    asyncio.run(transport.send(email_settings(), "rae@example.com", "Rae", "Hi", "<p>x</p>", "x"))
    assert posted["url"] == "https://graph.microsoft.com/v1.0/users/codeassure%40example.com/sendMail"
    assert posted["auth"] == "Bearer tok" and posted["authority"] == "https://login.microsoftonline.com/t"
    assert posted["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "rae@example.com"
    assert posted["json"]["saveToSentItems"] is False


def test_graph_token_failure_is_an_email_error(monkeypatch):
    class NoToken:
        def __init__(self, *args, **kwargs):
            pass
        def acquire_token_for_client(self, scopes):
            return {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret provided."}

    monkeypatch.setattr(transport.msal, "ConfidentialClientApplication", NoToken)
    for name, value in (("EMAIL_MODE", "graph"), ("EMAIL_FROM", "a@b.c"), ("GRAPH_TENANT_ID", "t"),
                        ("GRAPH_CLIENT_ID", "c"), ("GRAPH_CLIENT_SECRET", "s3cret")):
        monkeypatch.setenv(name, value)
    with pytest.raises(EmailError) as exc:
        asyncio.run(transport.send(email_settings(), "rae@example.com", None, "Hi", "<p>x</p>", "x"))
    assert "invalid_client" in str(exc.value) and "s3cret" not in str(exc.value)
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.email.transport` / `sender`.

- [ ] **Step 3: Implement**

```python
# backend/app/email/transport.py
"""Sends one email through the configured mode. Errors never include secrets."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote

import httpx
import msal

from app.email.config import EmailSettings
from app.utils.logger import get_logger

logger = get_logger(__name__)

GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"


class EmailError(Exception):
    pass


async def send(settings: EmailSettings, to_address: str, to_name: str | None, subject: str, html: str, text: str) -> None:
    if settings.mode == "log":
        logger.info("Email (log mode) to %s: %s", to_address, subject)
        return
    if settings.mode == "smtp":
        await asyncio.to_thread(_send_smtp, settings, to_address, to_name, subject, html, text)
        return
    if settings.mode == "graph":
        await _send_graph(settings, to_address, to_name, subject, html)
        return
    raise EmailError(f"Unknown EMAIL_MODE {settings.mode!r}")


def _send_smtp(settings: EmailSettings, to_address, to_name, subject, html, text) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.from_name, settings.from_address))
    message["To"] = formataddr((to_name or "", to_address))
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"SMTP send failed: {exc.__class__.__name__}: {exc}") from None


def _graph_token(settings: EmailSettings) -> str:
    app = msal.ConfidentialClientApplication(
        settings.graph_client_id,
        authority=f"https://login.microsoftonline.com/{settings.graph_tenant_id}",
        client_credential=settings.graph_client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        description = (result.get("error_description") or "")[:200]
        raise EmailError(f"Couldn't get a Microsoft Graph token: {result.get('error')}: {description}")
    return result["access_token"]


async def _send_graph(settings: EmailSettings, to_address, to_name, subject, html) -> None:
    token = await asyncio.to_thread(_graph_token, settings)
    body = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to_address, "name": to_name or to_address}}],
        },
        "saveToSentItems": False,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GRAPH_SEND_URL.format(sender=quote(settings.from_address)), json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise EmailError(f"Couldn't reach Microsoft Graph: {exc.__class__.__name__}") from None
    if response.status_code != 202:
        raise EmailError(f"Microsoft Graph sendMail returned HTTP {response.status_code}: {response.text[:300]}")
```

```python
# backend/app/email/sender.py
"""Delivers pending notification_outbox rows (oldest first), with retries and backoff."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.db import crud
from app.db.session import new_session
from app.email.config import config_problems, email_settings
from app.email.templates import render
from app.email.transport import EmailError, send
from app.utils.logger import get_logger

logger = get_logger(__name__)

POLL_SECONDS = 15
BATCH_SIZE = 20
MAX_ATTEMPTS = 5

_wake_event: asyncio.Event | None = None


def _now():
    return datetime.now(timezone.utc)


def wake() -> None:
    """Deliver soon instead of waiting for the next poll (no-op if the loop isn't running)."""
    if _wake_event is not None:
        _wake_event.set()


async def deliver_due(limit: int = BATCH_SIZE) -> int:
    settings = email_settings()
    problems = config_problems(settings)
    delivered = 0
    async with new_session() as session:
        rows = await crud.list_due_notifications(session, _now(), limit)
        users = await crud.get_users_by_ids(session, [row.recipient_user_id for row in rows])
        for row in rows:
            user = users.get(row.recipient_user_id)
            if user is None or not user.is_active:
                await crud.update_notification(session, row, status="skipped")
                continue
            subject, html, text = render(row.event, row.payload or {}, user.name or user.email, settings.base_url)
            attempts = (row.attempts or 0) + 1
            try:
                if problems:
                    raise EmailError(" ".join(problems))
                await send(settings, user.email, user.name, subject, html, text)
            except Exception as exc:
                error = str(exc) if isinstance(exc, EmailError) else f"Unexpected error: {exc.__class__.__name__}"
                if attempts >= MAX_ATTEMPTS:
                    await crud.update_notification(session, row, status="failed", attempts=attempts, last_error=error, subject=subject)
                else:
                    await crud.update_notification(
                        session, row, attempts=attempts, last_error=error, subject=subject,
                        next_attempt_at=_now() + timedelta(minutes=2 ** attempts),
                    )
                logger.warning("Email %s to %s failed (attempt %d): %s", row.event, user.email, attempts, error)
                continue
            await crud.update_notification(
                session, row, status="logged" if settings.mode == "log" else "sent", sent_at=_now(),
                attempts=attempts, last_error=None, subject=subject,
            )
            delivered += 1
    return delivered


async def email_loop() -> None:
    global _wake_event
    _wake_event = asyncio.Event()
    logger.info("Email sender started (mode: %s)", email_settings().mode)
    while True:
        try:
            await asyncio.wait_for(_wake_event.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
        _wake_event.clear()
        try:
            await deliver_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Email sender error")


def start_email_worker() -> asyncio.Task:
    return asyncio.create_task(email_loop())
```

  - **`notify.py`:** add `from app.email import sender as email_sender`. Make `notify` return the rows and wake the sender:

```python
async def notify(session, event: str, user_ids, payload: dict) -> list:
    ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id]
    users = await crud.get_users_by_ids(session, ids)
    active = [user_id for user_id in ids if user_id in users and users[user_id].is_active]
    if not active:
        return []
    rows = await crud.add_notifications(session, event, active, payload)
    email_sender.wake()
    return rows
```

  - **`main.py`:** import `from app.email.sender import start_email_worker`. In `lifespan`, start the email worker together with the review worker and cancel both on shutdown:

```python
    background = []
    if environ.get("REVIEW_WORKER_ENABLED", "").lower() == "true":
        background = [start_worker(), start_email_worker()]
    yield
    for task in background:
        task.cancel()
```

    This replaces the single `worker_task` lines.
  - **`docker-compose.yml`:** under the backend `environment:`, after the `SETTINGS_ENCRYPTION_KEY` lines, add:

```yaml
      # Email delivery: log (default, no email sent) | graph | smtp. See docs/.../email-and-stage-tracker-design.md.
      - EMAIL_MODE=${EMAIL_MODE:-log}
      - EMAIL_FROM=${EMAIL_FROM:-}
      - EMAIL_FROM_NAME=${EMAIL_FROM_NAME:-CodeAssure}
      - GRAPH_TENANT_ID=${GRAPH_TENANT_ID:-}
      - GRAPH_CLIENT_ID=${GRAPH_CLIENT_ID:-}
      - GRAPH_CLIENT_SECRET=${GRAPH_CLIENT_SECRET:-}
      - SMTP_HOST=${SMTP_HOST:-}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USERNAME=${SMTP_USERNAME:-}
      - SMTP_PASSWORD=${SMTP_PASSWORD:-}
      - SMTP_STARTTLS=${SMTP_STARTTLS:-true}
```

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: deliver outbox emails via log, SMTP or Microsoft Graph with retries`.

---

### Task 4: Remind endpoint and email admin API

**Files:**
- Modify: `backend/app/api/cycles.py`, `backend/main.py`
- Create: `backend/app/api/email_admin.py`, `backend/tests/test_remind_and_email_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_remind_and_email_api.py
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.email_admin as email_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
NOW = datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, email_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin", name="Ada")
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer")
        await crud.create_user(s, "pm", "pm@example.com", "h", "project_manager")
        await crud.create_project(s, "p1", "Alpha")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev"), (".NET", "rev")])
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform="iOS", status="pending_approval", project_name="Alpha",
            created_at=NOW, completed_at=NOW, total_score_pct=80, llm_provider="azure", llm_model=None,
            compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "iOS"), run_status="completed", review_id="r1")
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", ".NET"), run_status="failed", failure_kind="system")
    yield maker
    await engine.dispose()


def _as(role, user_id="adm"):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _remind(platform, target):
    return client.post(f"/api/cycles/c1/assignments/{platform}/remind", json={"target": target})


async def test_remind_rules(db):
    _as("coordinator", "co")
    body = _remind("Android", "pm").json()
    assert body["pm_reminded_at"] is not None
    assert _remind("iOS", "reviewer").json()["reviewer_reminded_at"] is not None
    for platform, target in (("Android", "reviewer"), ("iOS", "pm"), (".NET", "pm"), (".NET", "reviewer")):
        response = _remind(platform, target)
        assert response.status_code == 409 and response.json()["detail"] == "A reminder isn't needed at this stage."
    assert _remind("Android", "everyone").status_code == 400
    assert client.post("/api/cycles/c9/assignments/Android/remind", json={"target": "pm"}).status_code == 404
    async with db() as s:
        pm = await crud.list_notifications(s, "reminder_pm")
        reviewer = await crud.list_notifications(s, "reminder_reviewer")
    assert [n.recipient_user_id for n in pm] == ["pm"] and pm[0].payload["link"] == "/"
    assert [n.recipient_user_id for n in reviewer] == ["rev"] and reviewer[0].payload["link"] == "/reports/r1"


async def test_remind_pm_after_url_failure(db):
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="url")
    _as("coordinator", "co")
    assert _remind("Android", "pm").status_code == 200


def test_remind_permissions(db):
    _as("project_manager", "pm")
    assert _remind("Android", "pm").status_code == 403


def test_email_status_and_admin_only(db, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "log")
    _as("admin")
    assert client.get("/api/email/status").json()["mode"] == "log"
    _as("management", "m")
    assert client.get("/api/email/status").status_code == 403
    assert client.get("/api/email/outbox").status_code == 403


async def test_test_email_and_outbox_listing(db):
    _as("admin")
    row = client.post("/api/email/test").json()
    assert row["event"] == "test_email" and row["recipient_email"] == "adm@example.com" and row["status"] == "pending"
    listed = client.get("/api/email/outbox?limit=5").json()["emails"]
    assert listed[0]["id"] == row["id"] and listed[0]["recipient_name"] == "Ada"


async def test_retry_only_failed(db):
    _as("admin")
    row = client.post("/api/email/test").json()
    assert client.post(f"/api/email/outbox/{row['id']}/retry").status_code == 409
    async with db() as s:
        r = await crud.get_notification(s, row["id"])
        await crud.update_notification(s, r, status="failed", attempts=5, last_error="boom")
    body = client.post(f"/api/email/outbox/{row['id']}/retry").json()
    assert (body["status"], body["attempts"], body["last_error"]) == ("pending", 0, None)
    assert client.post("/api/email/outbox/nope/retry").status_code == 404
```

- [ ] **Step 2: Run and verify it fails.** Expected: `ModuleNotFoundError: app.api.email_admin`.

- [ ] **Step 3: Implement.** In `cycles.py`:
  - Add `from app.automation.notify import cycle_payload, notify, project_manager_ids`.
  - Append:

```python
class RemindBody(BaseModel):
    target: str


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/remind")
async def remind(cycle_id: str, platform: str, body: RemindBody, user=Depends(require_permission("cycles.initiate"))):
    if body.target not in ("pm", "reviewer"):
        raise HTTPException(status_code=400, detail="target must be 'pm' or 'reviewer'")
    async with new_session() as session:
        cycle, project, assignment = await _load(session, user, cycle_id, platform)
        review_status = (await crud.get_review_statuses(session, [assignment.review_id])).get(assignment.review_id)
        needs_url = assignment.run_status == "waiting_for_url" or (
            assignment.run_status == "failed" and assignment.failure_kind == "url"
        )
        needs_feedback = assignment.run_status == "completed" and review_status != "approved" and assignment.reviewer_id
        if body.target == "pm" and needs_url:
            payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, link="/", run_error=assignment.run_error)
            await notify(session, "reminder_pm", await project_manager_ids(session, cycle.project_id), payload)
            await crud.update_assignment(session, assignment, pm_reminded_at=_now())
        elif body.target == "reviewer" and needs_feedback:
            payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, link=f"/reports/{assignment.review_id}")
            await notify(session, "reminder_reviewer", [assignment.reviewer_id], payload)
            await crud.update_assignment(session, assignment, reviewer_reminded_at=_now())
        else:
            raise HTTPException(status_code=409, detail="A reminder isn't needed at this stage.")
        return await _one(session, assignment)
```

```python
# backend/app/api/email_admin.py
"""Admin email section: delivery status, test email, recent emails and retry."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.permissions import require_permission
from app.automation.notify import notify
from app.db import crud
from app.db.session import new_session
from app.email import sender as email_sender
from app.email.config import describe

router = APIRouter(dependencies=[Depends(require_permission("email.manage"))])


def _iso(value):
    return value.isoformat() if value else None


async def _rows(session, rows) -> list[dict]:
    users = await crud.get_users_by_ids(session, [row.recipient_user_id for row in rows])
    result = []
    for row in rows:
        user = users.get(row.recipient_user_id)
        result.append({
            "id": row.id, "event": row.event,
            "recipient_email": user.email if user else None, "recipient_name": user.name if user else None,
            "subject": row.subject, "status": row.status, "attempts": row.attempts, "last_error": row.last_error,
            "created_at": _iso(row.created_at), "sent_at": _iso(row.sent_at),
        })
    return result


@router.get("/api/email/status")
async def email_status():
    return describe()


@router.post("/api/email/test")
async def send_test_email(user=Depends(require_permission("email.manage"))):
    async with new_session() as session:
        rows = await notify(session, "test_email", [user.id], {"link": "/settings"})
        return (await _rows(session, rows))[0]


@router.get("/api/email/outbox")
async def list_outbox(limit: int = Query(50, ge=1, le=200)):
    async with new_session() as session:
        return {"emails": await _rows(session, await crud.list_recent_notifications(session, limit))}


@router.post("/api/email/outbox/{notification_id}/retry")
async def retry_email(notification_id: str):
    async with new_session() as session:
        row = await crud.get_notification(session, notification_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Email not found")
        if row.status != "failed":
            raise HTTPException(status_code=409, detail="Only a failed email can be retried.")
        row = await crud.update_notification(session, row, status="pending", attempts=0, next_attempt_at=None, last_error=None)
        email_sender.wake()
        return (await _rows(session, [row]))[0]
```

  In `main.py`, add `from app.api.email_admin import router as email_admin_router` and `app.include_router(email_admin_router)`.

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add manual reminders and the admin email API`.

---

### Task 5: Stage tracker UI and reminder buttons

**Files:**
- Create: `frontend/src/components/StageTracker.jsx` and its test
- Modify:
  - `frontend/src/services/api.js`
  - `frontend/src/components/QuarterCard.jsx` (+ test), `frontend/src/components/ManageCycleDialog.jsx` (+ test)
  - `frontend/src/design-system.css`

**Interfaces:**
- Produces: `stagesFor(assignment, initiatedAt)`, `StageDots`, `StageTimeline`, `relativeTime(iso, now)`, and `remindAssignment(cycleId, platform, target)`.

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/components/StageTracker.test.jsx
import { render, screen } from "@testing-library/react";
import { relativeTime, StageDots, StageTimeline, stagesFor } from "./StageTracker";

const INIT = "2026-10-07T09:00:00Z";
const base = { run_status: "waiting_for_url", url_submitted_at: null, finished_at: null, review_status: null, review_approved_at: null };

test("waiting for URL: only initiated is done", () => {
  expect(stagesFor(base, INIT).map((s) => s.state)).toEqual(["done", "pending", "pending", "pending"]);
});

test("queued after URL", () => {
  expect(stagesFor({ ...base, run_status: "queued", url_submitted_at: INIT }, INIT).map((s) => s.state)).toEqual(["done", "done", "pending", "pending"]);
});

test("failed AI run", () => {
  const stages = stagesFor({ ...base, run_status: "failed", url_submitted_at: INIT, finished_at: INIT }, INIT);
  expect(stages[2]).toMatchObject({ state: "failed", at: INIT });
});

test("completed and approved", () => {
  const a = { ...base, run_status: "completed", url_submitted_at: INIT, finished_at: INIT, review_status: "approved", review_approved_at: INIT };
  expect(stagesFor(a, INIT).map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
});

test("dots carry titles and an accessible summary", () => {
  render(<StageDots assignment={{ ...base, run_status: "queued", url_submitted_at: INIT }} initiatedAt={INIT} />);
  const group = screen.getByRole("img");
  expect(group.getAttribute("aria-label")).toMatch(/^Initiated — done .*; URL added — done .*; AI review done — pending; Reviewer feedback — pending$/);
  expect(group.querySelectorAll(".stage-dot--done")).toHaveLength(2);
});

test("timeline lists labels", () => {
  render(<StageTimeline assignment={base} initiatedAt={INIT} />);
  expect(screen.getByText("Reviewer feedback")).toBeInTheDocument();
  expect(screen.getAllByText("Pending")).toHaveLength(3);
});

test("relative time", () => {
  const now = new Date("2026-10-08T12:00:00Z").getTime();
  expect(relativeTime("2026-10-08T11:59:30Z", now)).toBe("just now");
  expect(relativeTime("2026-10-08T11:15:00Z", now)).toBe("45m ago");
  expect(relativeTime("2026-10-08T09:00:00Z", now)).toBe("3h ago");
  expect(relativeTime("2026-10-06T12:00:00Z", now)).toBe("2d ago");
});
```

  Add to `ManageCycleDialog.test.jsx`:
  - Add `remindAssignment: jest.fn()` to the mock factory and import it.
  - Then:

```jsx
test("progress column and reminder buttons", async () => {
  const user = userEvent.setup();
  const stagesEntry = { ...entry, cycle: { ...entry.cycle, assignments: [
    a("Android", { run_status: "waiting_for_url", devops_url: null, pm_reminded_at: "2026-10-08T08:00:00Z" }),
    a("iOS", { run_status: "completed", review_id: "rv1", review_status: "pending_approval", url_submitted_at: "2026-10-07T10:00:00Z", finished_at: "2026-10-07T11:00:00Z" }),
  ] } };
  remindAssignment.mockResolvedValue(a("iOS", { run_status: "completed", review_id: "rv1", review_status: "pending_approval", reviewer_reminded_at: "2026-10-08T12:00:00Z" }));
  render(<ManageCycleDialog project={{ id: "p1", name: "Moove" }} year={2026} entry={stagesEntry} onChanged={jest.fn()} onClose={jest.fn()} />);
  expect(within(row("Android")).getByRole("button", { name: "Remind PM" })).toBeInTheDocument();
  expect(within(row("Android")).queryByRole("button", { name: "Remind reviewer" })).not.toBeInTheDocument();
  expect(within(row("Android")).getByText(/Reminded PM/)).toBeInTheDocument();
  expect(within(row("iOS")).getAllByText("Reviewer feedback").length).toBeGreaterThan(0);
  await user.click(within(row("iOS")).getByRole("button", { name: "Remind reviewer" }));
  await waitFor(() => expect(remindAssignment).toHaveBeenCalledWith("c1", "iOS", "reviewer"));
  expect(await within(row("iOS")).findByText(/Reminded reviewer/)).toBeInTheDocument();
});
```

  Add to `QuarterCard.test.jsx`:

```jsx
test("stage dots appear per platform once a cycle exists", () => {
  const entry = { ...base, status: "in_progress", covered: [], missing: ["Android", "iOS"], can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora", assignments: [
      { platform: "Android", reviewer_id: "r", reviewer_name: "Rae", run_status: "waiting_for_url" },
      { platform: "iOS", reviewer_id: "r", reviewer_name: "Rae", run_status: "queued", url_submitted_at: "2026-10-03T10:00:00Z" },
    ] } };
  const { container } = render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(container.querySelectorAll(".stage-dots")).toHaveLength(2);
});

test("no stage dots without a cycle", () => {
  const { container } = render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(container.querySelectorAll(".stage-dots")).toHaveLength(0);
});
```

- [ ] **Step 2: Run and verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement.** Append to `api.js`:

```js
export async function remindAssignment(cycleId, platform, target) {
  const response = await axios.post(`${assignmentPath(cycleId, platform)}/remind`, { target });
  return response.data;
}
```

```jsx
// frontend/src/components/StageTracker.jsx
export function formatStageTime(iso) {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(iso, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function stagesFor(assignment, initiatedAt) {
  const ai = assignment.run_status === "completed" ? "done" : assignment.run_status === "failed" ? "failed" : "pending";
  return [
    { key: "initiated", label: "Initiated", state: initiatedAt ? "done" : "pending", at: initiatedAt || null },
    { key: "url", label: "URL added", state: assignment.url_submitted_at ? "done" : "pending", at: assignment.url_submitted_at || null },
    { key: "ai", label: "AI review done", state: ai, at: ai === "pending" ? null : assignment.finished_at || null },
    {
      key: "feedback", label: "Reviewer feedback",
      state: assignment.review_status === "approved" ? "done" : "pending", at: assignment.review_approved_at || null,
    },
  ];
}

function describeStage(stage) {
  if (stage.state === "pending") return `${stage.label} — pending`;
  const when = stage.at ? ` ${formatStageTime(stage.at)}` : "";
  return `${stage.label} — ${stage.state}${when}`;
}

export function StageDots({ assignment, initiatedAt }) {
  const stages = stagesFor(assignment, initiatedAt);
  return (
    <span className="stage-dots" role="img" aria-label={stages.map(describeStage).join("; ")}>
      {stages.map((stage) => (
        <span key={stage.key} className={`stage-dot stage-dot--${stage.state}`} title={describeStage(stage)} />
      ))}
    </span>
  );
}

export function StageTimeline({ assignment, initiatedAt }) {
  return (
    <ol className="stage-timeline">
      {stagesFor(assignment, initiatedAt).map((stage) => (
        <li key={stage.key} className={`stage stage--${stage.state}`}>
          <span className={`stage-dot stage-dot--${stage.state}`} aria-hidden="true" />
          <span className="stage-label">{stage.label}</span>
          <span className="stage-time">
            {stage.state === "pending" ? "Pending" : stage.at ? formatStageTime(stage.at) : stage.state === "failed" ? "Failed" : "Done"}
          </span>
        </li>
      ))}
    </ol>
  );
}
```

  **`QuarterCard.jsx`:**
  - Import `{ StageDots }` from `./StageTracker`.
  - In the platform `<li>`, right after `{" "}{platform}`, add:

```jsx
                {entry.cycle && assignmentByPlatform[platform] && (
                  <>{" "}<StageDots assignment={assignmentByPlatform[platform]} initiatedAt={entry.cycle.initiated_at} /></>
                )}
```

  **`ManageCycleDialog.jsx`:**
  - Import `{ relativeTime, StageTimeline }` from `./StageTracker` and `remindAssignment` from the api.
  - Header row: `<th>Platform</th><th>Status</th><th>Progress</th><th>Reviewer</th><th aria-label="Actions" />`.
  - After the Status `<td>`, add:

```jsx
                      <td><StageTimeline assignment={assignment} initiatedAt={entry.cycle.initiated_at} /></td>
```

  - At the top of the Actions `<td>` (before Retry), add:

```jsx
                        {(assignment.run_status === "waiting_for_url" || (assignment.run_status === "failed" && assignment.failure_kind === "url")) && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => remindAssignment(cycleId, assignment.platform, "pm"))}>Remind PM</button>
                        )}
                        {assignment.run_status === "completed" && !approved && assignment.reviewer_id && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => remindAssignment(cycleId, assignment.platform, "reviewer"))}>Remind reviewer</button>
                        )}
```

  - At the end of that `<td>`, after Re-run, add:

```jsx
                        {assignment.pm_reminded_at && <div className="quarter-card-meta">Reminded PM {relativeTime(assignment.pm_reminded_at)}</div>}
                        {assignment.reviewer_reminded_at && <div className="quarter-card-meta">Reminded reviewer {relativeTime(assignment.reviewer_reminded_at)}</div>}
```

  - In the Actions `<td>`, change `style={{ whiteSpace: "nowrap" }}` to `style={{ whiteSpace: "nowrap", verticalAlign: "top" }}`.

  Append to `design-system.css`:

```css
/* — stage tracker — */
.stage-dots { display: inline-flex; gap: 3px; vertical-align: middle; margin-left: 4px; }
.stage-dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; background: #e0a32e; }
.stage-dot--done { background: #2e9e5b; }
.stage-dot--failed { background: var(--color-brand-coral); }
.stage-timeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; min-width: 210px; }
.stage { display: grid; grid-template-columns: 10px 1fr auto; gap: 8px; align-items: center; font-size: 12px; }
.stage-label { color: var(--color-text); }
.stage-time { color: var(--color-text-muted); white-space: nowrap; }
.stage--pending .stage-label { color: var(--color-text-muted); }
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: show the four-stage tracker on quarter cards and in Manage, with reminder buttons`.

---

### Task 6: Settings → Email section

**Files:**
- Create: `frontend/src/components/EmailSettingsSection.jsx` and its test
- Modify:
  - `frontend/src/services/api.js`, `frontend/src/pages/SettingsPage.jsx`
  - `frontend/src/testUtils/authUsers.js`, `frontend/src/context/AuthContext.jsx`

- [ ] **Step 1: Write the failing test.** Add `"email.manage"` to admin in `authUsers.js` and to the `AuthContext.jsx` default list. Then create:

```jsx
// frontend/src/components/EmailSettingsSection.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmailSettingsSection from "./EmailSettingsSection";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getEmailStatus, getEmailOutbox, sendTestEmail, retryEmail } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getEmailStatus: jest.fn(), getEmailOutbox: jest.fn(), sendTestEmail: jest.fn(), retryEmail: jest.fn(),
}));

const status = { mode: "log", from_address: null, from_name: "CodeAssure", base_url: "http://localhost:3000", configured: true, problems: [] };
const email = (extra) => ({ id: "e1", event: "review_ready", recipient_email: "rae@example.com", recipient_name: "Rae",
  subject: "Ready for your review: Moove · iOS (Q4 2026)", status: "logged", attempts: 1, last_error: null,
  created_at: "2026-10-08T10:00:00Z", sent_at: "2026-10-08T10:00:05Z", ...extra });

beforeEach(() => {
  jest.resetAllMocks();
  getEmailStatus.mockResolvedValue(status);
  getEmailOutbox.mockResolvedValue([email(), email({ id: "e2", status: "failed", last_error: "SMTP send failed: SMTPAuthenticationError", attempts: 5 })]);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <EmailSettingsSection />
    </AuthContext.Provider>
  );
}

test("shows the delivery status and recent emails", async () => {
  renderAs("admin");
  expect(await screen.findByText(/Log only/)).toBeInTheDocument();
  const table = screen.getByRole("table");
  expect(within(table).getByText("Ready for your review: Moove · iOS (Q4 2026)", { selector: "td" })).toBeInTheDocument();
  expect(within(table).getByText("SMTP send failed: SMTPAuthenticationError")).toBeInTheDocument();
});

test("lists configuration problems", async () => {
  getEmailStatus.mockResolvedValue({ ...status, mode: "smtp", configured: false, problems: ["SMTP_HOST is not set."] });
  renderAs("admin");
  expect(await screen.findByText("SMTP_HOST is not set.")).toBeInTheDocument();
});

test("send test email and retry a failed one", async () => {
  const user = userEvent.setup();
  sendTestEmail.mockResolvedValue(email({ id: "e3", event: "test_email", status: "pending" }));
  retryEmail.mockResolvedValue(email({ id: "e2", status: "pending" }));
  renderAs("admin");
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "Send test email" }));
  await waitFor(() => expect(sendTestEmail).toHaveBeenCalled());
  expect(await screen.findByText(/Test email queued/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryEmail).toHaveBeenCalledWith("e2"));
});

test("hidden for non-admins", () => {
  const { container } = renderAs("management");
  expect(container).toBeEmptyDOMElement();
  expect(getEmailStatus).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run and verify it fails.** Expected: FAIL.

- [ ] **Step 3: Implement.** Append to `api.js`:

```js
export async function getEmailStatus() {
  const response = await axios.get(`${API_BASE_URL}/email/status`);
  return response.data;
}

export async function sendTestEmail() {
  const response = await axios.post(`${API_BASE_URL}/email/test`);
  return response.data;
}

export async function getEmailOutbox(limit = 50) {
  const response = await axios.get(`${API_BASE_URL}/email/outbox`, { params: { limit } });
  return response.data.emails;
}

export async function retryEmail(id) {
  const response = await axios.post(`${API_BASE_URL}/email/outbox/${id}/retry`);
  return response.data;
}
```

```jsx
// frontend/src/components/EmailSettingsSection.jsx
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { hasPermission } from "../permissions";
import { getEmailOutbox, getEmailStatus, retryEmail, sendTestEmail } from "../services/api";

const MODE_LABELS = { log: "Log only (no email is sent)", graph: "Microsoft Graph", smtp: "SMTP" };

export default function EmailSettingsSection() {
  const { user } = useAuth();
  const allowed = hasPermission(user, "email.manage");
  const [status, setStatus] = useState(null);
  const [emails, setEmails] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    Promise.all([getEmailStatus(), getEmailOutbox()])
      .then(([nextStatus, nextEmails]) => { setStatus(nextStatus); setEmails(nextEmails); setError(""); })
      .catch(() => setError("Failed to load email settings"));
  }, []);

  useEffect(() => { if (allowed) load(); }, [allowed, load]);

  if (!allowed) return null;

  async function handleTest() {
    setMessage("");
    try {
      await sendTestEmail();
      setMessage(`Test email queued for ${user.email}.`);
      load();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Failed to queue a test email");
    }
  }

  async function handleRetry(id) {
    try {
      await retryEmail(id);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to retry the email");
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Email</div>
      <div className="card-title" style={{ fontSize: 18 }}>Workflow emails</div>
      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
      {status && (
        <div className="card-body" style={{ display: "grid", gap: 4 }}>
          <div>Delivery: <strong>{MODE_LABELS[status.mode] || status.mode}</strong>{status.from_address && <> · from {status.from_name} &lt;{status.from_address}&gt;</>}</div>
          <div>Links point to {status.base_url}</div>
          {status.configured ? <div>Configured.</div> : (
            <ul style={{ margin: 0, color: "var(--color-brand-coral)" }}>
              {status.problems.map((problem) => <li key={problem}>{problem}</li>)}
            </ul>
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary" onClick={handleTest}>Send test email</button>
        <button type="button" className="btn btn-ghost" onClick={load}>Refresh</button>
        {message && <span className="card-body" style={{ margin: 0 }}>{message}</span>}
      </div>
      <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
        {emails.length === 0 ? <p className="card-body">No emails yet.</p> : (
          <table className="table table--padded">
            <thead><tr><th>When</th><th>To</th><th>Subject</th><th>Status</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {emails.map((row) => (
                <tr key={row.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(row.created_at).toLocaleString()}</td>
                  <td>{row.recipient_name || row.recipient_email || "—"}</td>
                  <td>{row.subject || row.event}</td>
                  <td>
                    <span className={`email-status email-status--${row.status}`}>{row.status}</span>
                    {row.last_error && <div className="run-error">{row.last_error}</div>}
                  </td>
                  <td>{row.status === "failed" && <button type="button" className="btn btn-ghost" onClick={() => handleRetry(row.id)}>Retry</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
```

  - **`SettingsPage.jsx`:** import `EmailSettingsSection` and render `<EmailSettingsSection />` after `<SampleTemplateSection />`.
  - **`design-system.css`:** append:

```css
.email-status { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; text-transform: capitalize; }
.email-status--sent, .email-status--logged { background: color-mix(in srgb, #2e9e5b 15%, var(--color-bg)); color: #1f6e3f; }
.email-status--pending { background: color-mix(in srgb, #e0b400 18%, var(--color-bg)); color: #6b5300; }
.email-status--failed { background: color-mix(in srgb, var(--color-brand-coral) 15%, var(--color-bg)); color: var(--color-brand-coral); }
.email-status--skipped { background: var(--color-surface); color: var(--color-text-muted); }
```

- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: add the admin Email section (status, test email, recent emails, retry)`.

---

### Task 7: Docker smoke test and progress log

- [ ] **Step 1: Run both suites in full.**
- [ ] **Step 2: Back up the database and rebuild.**
  - `pg_dump` to `<scratchpad>/codereviews-before-email.sql`.
  - Rebuild the backend and frontend.
  - Confirm `Running upgrade f6a7b8c9d0e1 -> a7b8c9d0e1f2`, "Review worker started" and "Email sender started (mode: log)".
  - Confirm every pre-existing outbox row is `skipped`.
- [ ] **Step 3: API smoke test as admin (log mode, so no real email is sent):**
  - `GET /api/email/status` returns mode `log`, configured.
  - `POST /api/email/test` returns `pending`, and within about 5 seconds `GET /api/email/outbox` shows it as `logged` with the subject "CodeAssure test email". The backend log shows `Email (log mode) to …`.
  - Run the reminder checks against the **existing real Moove Q3 cycle** only if a reminder is valid, and don't send real email. Prefer using `Smoke Project` with a smoke PM: remind the PM, and confirm a `reminder_pm` row is `logged` within seconds.
  - Clean up the smoke data and the test-email outbox rows. Confirm the counts.
- [ ] **Step 4: Update `progress.md`** with Phase 12, including the env variables and the network-team prerequisites, then commit with the message `docs: log email delivery and stage tracker in progress.md`.
