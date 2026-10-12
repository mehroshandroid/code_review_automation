"""Subjects and bodies for workflow emails. Payload values are untrusted: always escaped in HTML."""
from html import escape


def _where(p: dict) -> str:
    platform = f" · {p.get('platform')}" if p.get("platform") else ""
    return f"{p.get('project_name')}{platform} (Q{p.get('quarter')} {p.get('year')})"


def _round(p: dict) -> str:
    number = p.get("round")
    return f" — round {number}" if isinstance(number, int) and number > 1 else ""


def _score(p: dict) -> str:
    score = p.get("total_score_pct")
    return f" — {score:g}%" if isinstance(score, (int, float)) else ""


def _failure_hint(p: dict) -> str:
    if p.get("failure_kind") == "url":
        return " The project's PM may need to correct the repository URL."
    return " An admin should check the setup (DevOps PAT, compile and LLM services)."


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _quarter_label(p: dict) -> str:
    return f"Q{p.get('quarter')} {p.get('year')}"


def _with_platforms(name, platforms) -> str:
    return f"{name} ({', '.join(platforms)})" if platforms else f"{name}"


def _digest_projects(p: dict) -> str:
    return ", ".join(
        _with_platforms(item.get("name"), item.get("platforms")) if isinstance(item, dict) else str(item)
        for item in p.get("projects") or []
    )


def _digest_assignments(p: dict) -> str:
    return "; ".join(f"{a.get('project_name')} · {a.get('platform')}" for a in p.get("assignments") or [])


# event -> (subject, message, button label)
_EVENTS = {
    "cycle_initiated": (
        lambda p: f"Action needed: add DevOps URLs for {p.get('project_name')} · Q{p.get('quarter')} {p.get('year')} review",
        lambda p: f"The Q{p.get('quarter')} {p.get('year')} code review for {_with_platforms(p.get('project_name'), p.get('platforms'))} has started. "
                  "Please add the Azure DevOps repository URL for each platform so the automatic review can run.",
        "Add repository URLs",
    ),
    "cycles_initiated_digest": (
        lambda p: f"Action needed: Q{p.get('quarter')} {p.get('year')} "
                  f"{'review' if len(p.get('projects') or []) == 1 else 'reviews'} started for "
                  f"{len(p.get('projects') or [])} of your projects",
        lambda p: f"The Q{p.get('quarter')} {p.get('year')} code reviews have started for: {_digest_projects(p)}. "
                  "Please add the Azure DevOps repository URL (or upload the source zip) for each platform so the automatic reviews can run.",
        "Add repository URLs",
    ),
    "reviewer_assigned_digest": (
        lambda p: f"You're the reviewer for {_count(len(p.get('assignments') or []), _quarter_label(p) + ' review')}",
        lambda p: f"You've been assigned to review these Q{p.get('quarter')} {p.get('year')} reviews: {_digest_assignments(p)}. "
                  "You'll get an email for each one when its automatic review is ready.",
        "Open CodeAssure",
    ),
    "cycle_reinitiated": (
        lambda p: f"Action needed: add the source for {_where(p)}{_round(p)}",
        lambda p: f"A new review round ({_round(p).replace(' — ', '')}) has started for {_where(p)}. "
                  "Please add the Azure DevOps repository URL or upload the source zip so the automatic review can run.",
        "Add the source",
    ),
    "reviewer_assigned": (
        lambda p: f"You're the reviewer for {_where(p)}{_round(p)}",
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
    # Collapse whitespace: untrusted names with line breaks must never reach an email header.
    subject = " ".join(subject_fn(payload).split())
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
