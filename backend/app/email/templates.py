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
