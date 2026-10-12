import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.auth.permissions import PERMISSIONS, require_permission
from app.automation.assignments import assignment_dicts
from app.automation.notify import cycle_payload, notify, project_manager_ids
from app.db import crud
from app.db.session import new_session
from app.quarterly import (
    TRACKED_PLATFORMS, can_initiate, canonical_platform, is_late, quarter_bounds, quarter_status, sort_platforms,
)

router = APIRouter()
logger = logging.getLogger(__name__)

ALREADY_INITIATED = "This quarter's review has already been initiated."


class AssignmentIn(BaseModel):
    platform: str
    reviewer_id: str


class InitiateCycleRequest(BaseModel):
    year: int
    quarter: int
    assignments: list[AssignmentIn]


class BulkProjectIn(BaseModel):
    project_id: str
    assignments: list[AssignmentIn]


class BulkInitiateRequest(BaseModel):
    year: int
    quarter: int
    projects: list[BulkProjectIn]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _display_name(user) -> str | None:
    return (user.name or user.email) if user else None


async def _quarter_entries(session, projects, year: int, today: date) -> dict[str, list[dict]]:
    project_ids = [p.id for p in projects]
    platforms_by_project = await crud.get_platforms_for_projects(session, project_ids)
    reviews = await crud.list_review_coverage_rows(session, project_ids, year)
    cycles = await crud.list_cycles_for_projects_in_year(session, project_ids, year)
    assignments = await crud.get_cycle_assignments(session, [c.id for c in cycles])
    user_ids = [c.initiated_by for c in cycles] + [a.reviewer_id for rows in assignments.values() for a in rows]
    users = await crud.get_users_by_ids(session, user_ids)
    cycle_by_key = {(c.project_id, c.quarter): c for c in cycles}
    first_reviews = await crud.get_first_review_dates(session, project_ids)
    # A review run for a quarter's cycle counts only for that quarter, whatever date it ran
    # (catching up a past quarter); every other review counts by its own date.
    cycle_review_ids = await crud.list_cycle_review_ids(session, project_ids)
    # One pass over the year's reviews: the newest review per (project, quarter, platform).
    latest_review = {}
    for review in reviews:  # newest first
        if review.id in cycle_review_ids:
            continue
        platform = canonical_platform(review.platform)
        reviewed_on = _as_date(review.created_at)
        key = (review.project_id, (reviewed_on.month - 1) // 3 + 1, platform)
        if platform is not None and key not in latest_review:
            latest_review[key] = review
    linked = {row.id: row for row in await crud.get_review_coverage_rows_by_ids(
        session, [a.review_id for rows in assignments.values() for a in rows],
    )}
    for cycle in cycles:
        for assignment in assignments[cycle.id]:
            review = linked.get(assignment.review_id)
            if review is not None:
                latest_review[(cycle.project_id, cycle.quarter, canonical_platform(assignment.platform))] = review

    entries: dict[str, list[dict]] = {}
    for project in projects:
        platforms = platforms_by_project[project.id]
        if not platforms:
            entries[project.id] = []
            continue
        # Tracked from whichever is earlier: the project record or its first
        # review -- historical sheets are often uploaded after the record exists.
        tracked_since = _as_date(project.created_at)
        if project.id in first_reviews:
            tracked_since = min(tracked_since, _as_date(first_reviews[project.id]))
        project_quarters = []
        for quarter in (1, 2, 3, 4):
            start, end = quarter_bounds(year, quarter)
            latest_by_platform = {
                platform: latest_review[(project.id, quarter, platform)]
                for platform in platforms if (project.id, quarter, platform) in latest_review
            }
            covered = set(latest_by_platform)
            cycle = cycle_by_key.get((project.id, quarter))
            status = quarter_status(tracked_since, platforms, covered, cycle is not None, year, quarter, today)
            late_platforms = {p for p, review in latest_by_platform.items() if _as_date(review.created_at) > end}
            project_quarters.append({
                "quarter": quarter,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": status,
                # Still running past the quarter's end, or completed only after it ended.
                "late": is_late(status, year, quarter, today) or (status == "done" and bool(late_platforms)),
                "covered": [
                    {
                        "platform": p, "review_id": latest_by_platform[p].id,
                        "reviewed_at": latest_by_platform[p].created_at.isoformat(), "late": p in late_platforms,
                    }
                    for p in sort_platforms(covered)
                ],
                "missing": [p for p in platforms if p not in covered],
                "can_initiate": can_initiate(status, cycle is not None, year, quarter, today),
                "cycle": None if cycle is None else {
                    "id": cycle.id,
                    "initiated_at": cycle.initiated_at.isoformat(),
                    "initiated_by_name": _display_name(users.get(cycle.initiated_by)),
                    "assignments": await assignment_dicts(session, assignments[cycle.id]),
                },
            })
        entries[project.id] = project_quarters
    return entries


@router.get("/api/quarterly")
async def get_quarterly(year: int | None = None, user=Depends(require_permission("cycles.view"))):
    today = _today()
    year = year or today.year
    async with new_session() as session:
        projects = sorted(await crud.list_projects(session), key=lambda p: p.name.lower())
        platforms = await crud.get_platforms_for_projects(session, [p.id for p in projects])
        entries = await _quarter_entries(session, projects, year, today)
    return {
        "year": year,
        "today": today.isoformat(),
        "projects": [
            {"id": p.id, "name": p.name, "platforms": platforms[p.id], "quarters": entries[p.id]} for p in projects
        ],
    }


def _valid_reviewer(user) -> bool:
    return user is not None and user.is_active and user.role in PERMISSIONS["reviews.finalize_own"]


async def _initiate_one(session, project, year: int, quarter: int, assignments: list[AssignmentIn], user, today: date) -> None:
    """Validate and create one project's cycle; raises HTTPException with a user-facing reason."""
    platforms = (await crud.get_platforms_for_projects(session, [project.id]))[project.id]
    if not platforms:
        raise HTTPException(status_code=400, detail="Set this project's platforms before initiating a review.")
    requested = [canonical_platform(a.platform) for a in assignments]
    if sorted(p or "" for p in requested) != sorted(platforms) or len(set(requested)) != len(requested):
        raise HTTPException(status_code=400, detail="Assign exactly one reviewer to each of the project's platforms.")
    reviewers = await crud.get_users_by_ids(session, [a.reviewer_id for a in assignments])
    if not all(_valid_reviewer(reviewers.get(a.reviewer_id)) for a in assignments):
        raise HTTPException(status_code=400, detail="Each reviewer must be an active reviewer, management or admin account.")
    if await crud.get_cycle(session, project.id, year, quarter) is not None:
        raise HTTPException(status_code=409, detail=ALREADY_INITIATED)
    current = (await _quarter_entries(session, [project], year, today))[project.id][quarter - 1]
    if not current["can_initiate"]:
        raise HTTPException(status_code=400, detail="This quarter can't be initiated.")
    try:
        await crud.create_cycle(
            session, str(uuid.uuid4()), project.id, year, quarter, user.id,
            [(canonical_platform(a.platform), a.reviewer_id) for a in assignments],
        )
    except IntegrityError:
        # Lost a race with a concurrent initiate: the unique constraint held.
        await session.rollback()
        raise HTTPException(status_code=409, detail=ALREADY_INITIATED)


@router.post("/api/projects/{project_id}/cycles")
async def initiate_cycle(project_id: str, body: InitiateCycleRequest, user=Depends(require_permission("cycles.initiate"))):
    if body.quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="quarter must be 1-4")
    today = _today()
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await _initiate_one(session, project, body.year, body.quarter, body.assignments, user, today)
        for_pms = cycle_payload(project.name, None, body.year, body.quarter, link="/")
        await notify(session, "cycle_initiated", await project_manager_ids(session, project_id), for_pms)
        for assignment in body.assignments:
            await notify(
                session, "reviewer_assigned", [assignment.reviewer_id],
                cycle_payload(project.name, canonical_platform(assignment.platform), body.year, body.quarter),
            )
        return (await _quarter_entries(session, [project], body.year, today))[project_id][body.quarter - 1]


def _skip_reason(entry: dict | None, year: int, quarter: int, today: date) -> str | None:
    """Why a project can't be bulk-initiated for this quarter, or None when it can."""
    if entry is None:
        return "No platforms set"
    if entry["cycle"] is not None:
        return "Already initiated"
    if entry["status"] == "done":
        return "Already done this quarter"
    if entry["status"] == "not_applicable":
        return "Not tracked yet that quarter"
    if today < quarter_bounds(year, quarter)[0]:
        return "Quarter hasn't started"
    return None if entry["can_initiate"] else "This quarter can't be initiated."


def _check_quarter(quarter: int) -> None:
    if quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="quarter must be 1-4")


@router.get("/api/quarterly/bulk-preview")
async def bulk_preview(year: int, quarter: int, user=Depends(require_permission("cycles.initiate"))):
    _check_quarter(quarter)
    today = _today()
    async with new_session() as session:
        projects = sorted(await crud.list_projects(session), key=lambda p: p.name.lower())
        project_ids = [p.id for p in projects]
        platforms = await crud.get_platforms_for_projects(session, project_ids)
        entries = await _quarter_entries(session, projects, year, today)
        managers = await crud.get_manager_ids_for_projects(session, project_ids)
        last_reviewers = await crud.get_latest_cycle_assignments(session, project_ids)
        users = await crud.get_users_by_ids(
            session,
            [u for ids in managers.values() for u in ids] + [r for m in last_reviewers.values() for r in m.values()],
        )
    eligible, skipped = [], []
    for project in projects:
        quarters = entries[project.id]
        reason = _skip_reason(quarters[quarter - 1] if quarters else None, year, quarter, today)
        if reason is not None:
            skipped.append({"project_id": project.id, "project_name": project.name, "reason": reason})
            continue
        last = last_reviewers[project.id]
        eligible.append({
            "project_id": project.id,
            "project_name": project.name,
            "platforms": platforms[project.id],
            "managers": [
                {"id": m, "name": _display_name(users[m])}
                for m in managers[project.id] if m in users and users[m].is_active
            ],
            # Last cycle's reviewer, while that account can still review.
            "suggested_reviewers": {
                platform: last.get(platform) if _valid_reviewer(users.get(last.get(platform))) else None
                for platform in platforms[project.id]
            },
        })
    return {"year": year, "quarter": quarter, "eligible": eligible, "skipped": skipped}


@router.post("/api/quarterly/bulk-initiate")
async def bulk_initiate(body: BulkInitiateRequest, user=Depends(require_permission("cycles.initiate"))):
    _check_quarter(body.quarter)
    today = _today()
    results = []
    projects_by_pm: dict[str, list[str]] = {}
    assignments_by_reviewer: dict[str, list[dict]] = {}
    for item in body.projects:
        # Each project gets its own session: a rollback after a lost race or an unexpected
        # error expires that session's objects, and must not touch the other projects.
        async with new_session() as session:
            project = await crud.get_project(session, item.project_id)
            if project is None:
                results.append({"project_id": item.project_id, "project_name": None, "status": "skipped",
                                "reason": "Project not found"})
                continue
            project_id, project_name = project.id, project.name
            try:
                await _initiate_one(session, project, body.year, body.quarter, item.assignments, user, today)
                manager_ids = await project_manager_ids(session, project_id)
            except HTTPException as error:
                results.append({"project_id": project_id, "project_name": project_name, "status": "skipped",
                                "reason": error.detail})
                continue
            except Exception:
                logger.exception("Bulk initiate failed for project %s", project_id)
                await session.rollback()
                results.append({"project_id": project_id, "project_name": project_name, "status": "skipped",
                                "reason": "Unexpected error — please try again."})
                continue
        results.append({"project_id": project_id, "project_name": project_name, "status": "started", "reason": None})
        for pm_id in manager_ids:
            projects_by_pm.setdefault(pm_id, []).append(project_name)
        for assignment in item.assignments:
            assignments_by_reviewer.setdefault(assignment.reviewer_id, []).append(
                {"project_name": project_name, "platform": canonical_platform(assignment.platform)}
            )
    # One email per person, however many projects they're involved in.
    async with new_session() as session:
        for pm_id, names in projects_by_pm.items():
            await notify(session, "cycles_initiated_digest", [pm_id],
                         {"year": body.year, "quarter": body.quarter, "projects": names, "link": "/"})
        for reviewer_id, assigned in assignments_by_reviewer.items():
            await notify(session, "reviewer_assigned_digest", [reviewer_id],
                         {"year": body.year, "quarter": body.quarter, "assignments": assigned, "link": "/"})
    return {"results": results}
