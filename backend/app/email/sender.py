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
