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
