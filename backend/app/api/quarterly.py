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

ALREADY_INITIATED = "This quarter's review has already been initiated."


class AssignmentIn(BaseModel):
    platform: str
    reviewer_id: str


class InitiateCycleRequest(BaseModel):
    year: int
    quarter: int
    assignments: list[AssignmentIn]


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
    # One pass over the year's reviews: the newest review per (project, quarter, platform).
    latest_review = {}
    for review in reviews:  # newest first
        platform = canonical_platform(review.platform)
        reviewed_on = _as_date(review.created_at)
        key = (review.project_id, (reviewed_on.month - 1) // 3 + 1, platform)
        if platform is not None and key not in latest_review:
            latest_review[key] = review

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
            project_quarters.append({
                "quarter": quarter,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": status,
                "late": is_late(status, year, quarter, today),
                "covered": [
                    {"platform": p, "review_id": latest_by_platform[p].id, "reviewed_at": latest_by_platform[p].created_at.isoformat()}
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


@router.post("/api/projects/{project_id}/cycles")
async def initiate_cycle(project_id: str, body: InitiateCycleRequest, user=Depends(require_permission("cycles.initiate"))):
    if body.quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="quarter must be 1-4")
    today = _today()
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        if not platforms:
            raise HTTPException(status_code=400, detail="Set this project's platforms before initiating a review.")
        requested = [canonical_platform(a.platform) for a in body.assignments]
        if sorted(p or "" for p in requested) != sorted(platforms) or len(set(requested)) != len(requested):
            raise HTTPException(status_code=400, detail="Assign exactly one reviewer to each of the project's platforms.")
        reviewers = await crud.get_users_by_ids(session, [a.reviewer_id for a in body.assignments])
        for assignment in body.assignments:
            reviewer = reviewers.get(assignment.reviewer_id)
            if reviewer is None or not reviewer.is_active or reviewer.role not in PERMISSIONS["reviews.finalize_own"]:
                raise HTTPException(status_code=400, detail="Each reviewer must be an active reviewer, management or admin account.")
        if await crud.get_cycle(session, project_id, body.year, body.quarter) is not None:
            raise HTTPException(status_code=409, detail=ALREADY_INITIATED)
        current = (await _quarter_entries(session, [project], body.year, today))[project_id][body.quarter - 1]
        if not current["can_initiate"]:
            raise HTTPException(status_code=400, detail="This quarter can't be initiated.")
        try:
            await crud.create_cycle(
                session, str(uuid.uuid4()), project_id, body.year, body.quarter, user.id,
                [(canonical_platform(a.platform), a.reviewer_id) for a in body.assignments],
            )
        except IntegrityError:
            # Lost a race with a concurrent initiate: the unique constraint held.
            await session.rollback()
            raise HTTPException(status_code=409, detail=ALREADY_INITIATED)
        for_pms = cycle_payload(project.name, None, body.year, body.quarter, link="/")
        await notify(session, "cycle_initiated", await project_manager_ids(session, project_id), for_pms)
        for assignment in body.assignments:
            await notify(
                session, "reviewer_assigned", [assignment.reviewer_id],
                cycle_payload(project.name, canonical_platform(assignment.platform), body.year, body.quarter),
            )
        return (await _quarter_entries(session, [project], body.year, today))[project_id][body.quarter - 1]
