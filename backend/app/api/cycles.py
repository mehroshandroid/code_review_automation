from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.analyzer.devops_client import parse_repo_url
from app.auth.permissions import PERMISSIONS, can, require_permission, visible_project_ids
from app.automation.assignments import assignment_dicts
from app.automation.notify import cycle_payload, notify, project_manager_ids
from app.automation.reviewers import APPROVED_LOCKED, reassign_cycle_reviewer
from app.db import crud
from app.db.session import new_session
from app.quarterly import canonical_platform

router = APIRouter()


class UrlBody(BaseModel):
    devops_url: str
    devops_branch: str | None = None


class ReviewerBody(BaseModel):
    reviewer_id: str


def _now():
    return datetime.now(timezone.utc)


async def _scope(session, user):
    return None if can(user, "cycles.view") else await visible_project_ids(session, user)


async def _load(session, user, cycle_id: str, platform: str):
    cycle = await crud.get_cycle_by_id(session, cycle_id)
    scope = await _scope(session, user)
    if cycle is None or (scope is not None and cycle.project_id not in scope):
        raise HTTPException(status_code=404, detail="Review cycle not found")
    assignment = await crud.get_assignment(session, cycle_id, canonical_platform(platform) or platform)
    if assignment is None:
        raise HTTPException(status_code=404, detail="This platform isn't part of the cycle")
    project = await crud.get_project(session, cycle.project_id)
    return cycle, project, assignment


def _validate_url(body: UrlBody):
    if parse_repo_url(body.devops_url.strip()) is None:
        raise HTTPException(status_code=400, detail="Not a recognized Azure DevOps repo URL.")


def _queue_fields(body: UrlBody, user) -> dict:
    return {
        "devops_url": body.devops_url.strip(),
        "devops_branch": (body.devops_branch or "").strip() or None,
        "url_submitted_by": user.id, "url_submitted_at": _now(),
        "run_status": "queued", "queued_at": _now(),
        "run_error": None, "failure_kind": None, "run_phase": None, "run_progress": None,
    }


async def _one(session, assignment) -> dict:
    return (await assignment_dicts(session, [assignment]))[0]


@router.get("/api/my/cycles")
async def list_my_cycles(user=Depends(require_permission("cycles.submit_urls"))):
    async with new_session() as session:
        cycles = await crud.list_open_cycles(session, await _scope(session, user))
        projects = {p.id: p for p in await crud.list_projects(session, project_ids={c.project_id for c in cycles} or None)} if cycles else {}
        by_cycle = await crud.get_cycle_assignments(session, [c.id for c in cycles])
        result = []
        for cycle in cycles:
            result.append({
                "id": cycle.id, "project_id": cycle.project_id, "project_name": projects[cycle.project_id].name,
                "year": cycle.year, "quarter": cycle.quarter, "initiated_at": cycle.initiated_at.isoformat(),
                "assignments": await assignment_dicts(session, by_cycle[cycle.id]),
            })
    return {"cycles": result}


@router.put("/api/cycles/{cycle_id}/assignments/{platform}/url")
async def submit_url(cycle_id: str, platform: str, body: UrlBody, user=Depends(require_permission("cycles.submit_urls"))):
    _validate_url(body)
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        if assignment.run_status not in ("waiting_for_url", "failed"):
            raise HTTPException(status_code=409, detail="This platform's review is already queued, running or completed.")
        await crud.update_assignment(session, assignment, **_queue_fields(body, user))
        return await _one(session, assignment)


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/retry")
async def retry(cycle_id: str, platform: str, user=Depends(require_permission("cycles.submit_urls"))):
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        if assignment.run_status != "failed":
            raise HTTPException(status_code=409, detail="Only a failed review can be retried.")
        await crud.update_assignment(
            session, assignment, run_status="queued", queued_at=_now(),
            run_error=None, failure_kind=None, run_phase=None, run_progress=None,
        )
        return await _one(session, assignment)


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/rerun")
async def rerun(cycle_id: str, platform: str, body: UrlBody, user=Depends(require_permission("cycles.initiate"))):
    _validate_url(body)
    async with new_session() as session:
        _, _, assignment = await _load(session, user, cycle_id, platform)
        statuses = await crud.get_review_statuses(session, [assignment.review_id])
        if assignment.run_status != "completed" or statuses.get(assignment.review_id) == "approved":
            raise HTTPException(status_code=409, detail="Only a completed review that isn't approved yet can be re-run.")
        fields = _queue_fields(body, user)
        if "devops_branch" not in body.model_fields_set:
            # A re-run with only a corrected URL keeps the branch the PM chose.
            fields["devops_branch"] = assignment.devops_branch
        await crud.update_assignment(session, assignment, **fields)
        return await _one(session, assignment)


@router.put("/api/cycles/{cycle_id}/assignments/{platform}/reviewer")
async def change_reviewer(cycle_id: str, platform: str, body: ReviewerBody, user=Depends(require_permission("reviews.assign_reviewer"))):
    async with new_session() as session:
        cycle, project, assignment = await _load(session, user, cycle_id, platform)
        statuses = await crud.get_review_statuses(session, [assignment.review_id])
        if statuses.get(assignment.review_id) == "approved":
            raise HTTPException(status_code=409, detail=APPROVED_LOCKED)
        reviewer = (await crud.get_users_by_ids(session, [body.reviewer_id])).get(body.reviewer_id)
        if reviewer is None or not reviewer.is_active or reviewer.role not in PERMISSIONS["reviews.finalize_own"]:
            raise HTTPException(status_code=400, detail="The reviewer must be an active reviewer, management or admin account.")
        await reassign_cycle_reviewer(session, cycle, project, assignment, body.reviewer_id, user.id)
        return await _one(session, assignment)


class RemindBody(BaseModel):
    target: str


@router.post("/api/cycles/{cycle_id}/assignments/{platform}/remind")
async def remind(cycle_id: str, platform: str, body: RemindBody, user=Depends(require_permission("cycles.initiate"))):
    if body.target not in ("pm", "reviewer"):
        raise HTTPException(status_code=400, detail="target must be 'pm' or 'reviewer'")
    async with new_session() as session:
        cycle, project, assignment = await _load(session, user, cycle_id, platform)
        review_status = (await crud.get_review_statuses(session, [assignment.review_id])).get(assignment.review_id)
        needs_url = assignment.run_status == "waiting_for_url" or (
            assignment.run_status == "failed" and assignment.failure_kind == "url"
        )
        needs_feedback = assignment.run_status == "completed" and review_status != "approved" and assignment.reviewer_id
        if body.target == "pm" and needs_url:
            payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, link="/", run_error=assignment.run_error)
            await notify(session, "reminder_pm", await project_manager_ids(session, cycle.project_id), payload)
            await crud.update_assignment(session, assignment, pm_reminded_at=_now())
        elif body.target == "reviewer" and needs_feedback:
            payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, link=f"/reports/{assignment.review_id}")
            await notify(session, "reminder_reviewer", [assignment.reviewer_id], payload)
            await crud.update_assignment(session, assignment, reviewer_reminded_at=_now())
        else:
            raise HTTPException(status_code=409, detail="A reminder isn't needed at this stage.")
        return await _one(session, assignment)
