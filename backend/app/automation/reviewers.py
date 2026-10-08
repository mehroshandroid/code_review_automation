"""Changing a quarterly cycle review's reviewer -- shared by the cycle Manage
dialog and the report page's reviewer picker so both follow the same rules."""
from datetime import datetime, timezone

from app.automation.notify import cycle_payload, notify
from app.db import crud

APPROVED_LOCKED = "This review is already approved; its reviewer can't change."


async def reassign_cycle_reviewer(session, cycle, project, assignment, reviewer_id: str, by_user_id: str):
    previous = assignment.reviewer_id
    if previous == reviewer_id:
        return assignment
    await crud.update_assignment(
        session, assignment, reviewer_id=reviewer_id, reviewer_assigned_by=by_user_id,
        reviewer_assigned_at=datetime.now(timezone.utc),
    )
    if assignment.review_id:
        await crud.set_review_reviewer(session, assignment.review_id, reviewer_id)
    link = {"link": f"/reports/{assignment.review_id}"} if assignment.review_id else {}
    await notify(session, "reviewer_assigned", [reviewer_id], cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, **link))
    await notify(session, "reviewer_unassigned", [previous], cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter))
    return assignment
