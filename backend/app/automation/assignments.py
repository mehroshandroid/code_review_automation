from app.db import crud
from app.quarterly import TRACKED_PLATFORMS


def _iso(value):
    return value.isoformat() if value else None


async def assignment_dicts(session, assignments, keep_order=False) -> list[dict]:
    users = await crud.get_users_by_ids(session, [a.reviewer_id for a in assignments])
    statuses = await crud.get_review_statuses(session, [a.review_id for a in assignments])
    positions = {key: index + 1 for index, key in enumerate(await crud.list_queued_keys(session))}
    rows = []
    for a in assignments if keep_order else sorted(assignments, key=lambda a: TRACKED_PLATFORMS.index(a.platform)):
        reviewer = users.get(a.reviewer_id)
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
            "cancel_requested": a.cancel_requested,
            "override_llm_provider": a.override_llm_provider,
            "override_llm_model": a.override_llm_model,
            "override_compile_mode": a.override_compile_mode,
        })
    return rows
