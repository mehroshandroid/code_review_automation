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
