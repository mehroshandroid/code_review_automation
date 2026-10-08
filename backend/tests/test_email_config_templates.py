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
