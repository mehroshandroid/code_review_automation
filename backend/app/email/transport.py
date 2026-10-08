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
    message["To"] = formataddr((" ".join((to_name or "").split()), to_address))
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
