from app.db import crud
from app.quarterly import TRACKED_PLATFORMS


def _name(user):
    return (user.name or user.email) if user else None


def _iso(value):
    return value.isoformat() if value else None


async def assignment_dicts(session, assignments, keep_order=False) -> list[dict]:
    users = await crud.get_users_by_ids(session, [a.reviewer_id for a in assignments])
    statuses = await crud.get_review_statuses(session, [a.review_id for a in assignments])
    approved_times = await crud.get_review_approved_times(session, [a.review_id for a in assignments])
    positions = {key: index + 1 for index, key in enumerate(await crud.list_queued_keys(session))}
    history = {}
    for archived in await crud.list_rounds(session, list({a.cycle_id for a in assignments})):
        history.setdefault((archived.cycle_id, archived.platform), []).append(archived)
    history_reviewers = await crud.get_users_by_ids(session, [r.reviewer_id for rows in history.values() for r in rows])
    rows = []
    for a in assignments if keep_order else sorted(assignments, key=lambda a: TRACKED_PLATFORMS.index(a.platform)):
        reviewer = users.get(a.reviewer_id)
        rounds = history.get((a.cycle_id, a.platform), [])
        approved = statuses.get(a.review_id) == "approved"
        # A retry or re-run of an approved row can still be queued or running: never reset under it.
        idle = a.run_status not in ("queued", "running") and not a.cancel_requested
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
            "cycle_id": a.cycle_id,
            "source_type": a.source_type,
            "source_zip_name": a.source_zip_name,
            "url_submitted_at": _iso(a.url_submitted_at),
            "review_approved_at": _iso(approved_times.get(a.review_id)),
            "pm_reminded_at": _iso(a.pm_reminded_at),
            "reviewer_reminded_at": _iso(a.reviewer_reminded_at),
            "cancel_requested": a.cancel_requested,
            "override_llm_provider": a.override_llm_provider,
            "override_llm_model": a.override_llm_model,
            "override_compile_mode": a.override_compile_mode,
            "round": a.round,
            # Every archived round was approved: only an approved review can be reinitiated.
            "approved_rounds": len(rounds) + (1 if approved else 0),
            "can_reinitiate": approved and idle,
            "history": [
                {
                    "round": r.round, "review_id": r.review_id, "approved_at": _iso(r.approved_at),
                    "reviewer_name": _name(history_reviewers.get(r.reviewer_id)),
                }
                for r in rounds
            ],
        })
    return rows
