"""Admin queue monitor: snapshot of automated cycle reviews, pause/resume and per-item actions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.permissions import require_permission
from app.automation.assignments import assignment_dicts
from app.automation.config import ALLOWED_COMPILE_MODES, effective_compile_modes
from app.automation.notify import cycle_payload, notify, project_manager_ids
from app.db import crud
from app.db.session import new_session
from app.quarterly import canonical_platform

router = APIRouter(dependencies=[Depends(require_permission("queue.manage"))])

LLM_PROVIDERS = ("azure", "ollama", "claude")
FAILED_LIMIT = 50
COMPLETED_LIMIT = 20


class RunSettingsBody(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    compile_mode: str | None = None


async def _items(session, assignments) -> list[dict]:
    if not assignments:
        return []
    rows = await assignment_dicts(session, assignments, keep_order=True)
    cycles = {cycle_id: await crud.get_cycle_by_id(session, cycle_id) for cycle_id in {a.cycle_id for a in assignments}}
    projects = {p.id: p for p in await crud.list_projects(session, project_ids={c.project_id for c in cycles.values()})}
    for row in rows:
        cycle = cycles[row["cycle_id"]]
        row.update(project_id=cycle.project_id, project_name=projects[cycle.project_id].name, year=cycle.year, quarter=cycle.quarter)
    return rows


async def _snapshot(session) -> dict:
    state = await crud.get_queue_state(session)
    pauser = (await crud.get_users_by_ids(session, [state.paused_by])).get(state.paused_by)
    org = await crud.get_org_settings(session)
    return {
        "paused": state.paused,
        "paused_by_name": (pauser.name or pauser.email) if pauser else None,
        "paused_at": state.paused_at.isoformat() if state.paused_at else None,
        "running": await _items(session, await crud.list_assignments_with_status(session, "running")),
        "queued": await _items(session, await crud.list_assignments_with_status(session, "queued")),
        "failed": await _items(session, await crud.list_assignments_with_status(session, "failed", True, FAILED_LIMIT)),
        "completed": await _items(session, await crud.list_assignments_with_status(session, "completed", True, COMPLETED_LIMIT)),
        "waiting_for_url": await crud.count_assignments_with_status(session, "waiting_for_url"),
        "defaults": {
            "llm_provider": org.default_llm_provider if org else "ollama",
            "llm_model": org.default_ollama_model if org else None,
            "compile_modes": effective_compile_modes(org.auto_compile_modes if org else None),
        },
    }


async def _load(session, cycle_id: str, platform: str):
    assignment = await crud.get_assignment(session, cycle_id, canonical_platform(platform) or platform)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return assignment


async def _one(session, assignment) -> dict:
    return (await _items(session, [assignment]))[0]


@router.get("/api/queue")
async def get_queue():
    async with new_session() as session:
        return await _snapshot(session)


@router.post("/api/queue/pause")
async def pause_queue(user=Depends(require_permission("queue.manage"))):
    async with new_session() as session:
        await crud.set_queue_paused(session, True, user.id)
        for assignment in await crud.list_assignments_with_status(session, "running"):
            await crud.update_assignment(session, assignment, cancel_requested="pause")
        return await _snapshot(session)


@router.post("/api/queue/resume")
async def resume_queue():
    async with new_session() as session:
        await crud.set_queue_paused(session, False, None)
        return await _snapshot(session)


@router.post("/api/queue/items/{cycle_id}/{platform}/stop")
async def stop_item(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "running":
            raise HTTPException(status_code=409, detail="Only a running review can be stopped.")
        await crud.update_assignment(session, assignment, cancel_requested="stop")
        return await _one(session, assignment)


@router.post("/api/queue/items/{cycle_id}/{platform}/remove")
async def remove_item(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "queued":
            raise HTTPException(status_code=409, detail="Only a queued review can be removed from the queue.")
        await crud.update_assignment(session, assignment, run_status="waiting_for_url", queued_at=None)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        payload = cycle_payload(project.name, assignment.platform, cycle.year, cycle.quarter, devops_url=assignment.devops_url, link="/")
        await notify(session, "review_removed_from_queue", await project_manager_ids(session, cycle.project_id), payload)
        return await _one(session, assignment)


@router.post("/api/queue/items/{cycle_id}/{platform}/front")
async def move_to_front(cycle_id: str, platform: str):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status != "queued":
            raise HTTPException(status_code=409, detail="Only a queued review can be moved.")
        await crud.update_assignment(session, assignment, queued_at=await crud.front_of_queue_time(session))
        return await _one(session, assignment)


@router.put("/api/queue/items/{cycle_id}/{platform}/settings")
async def set_run_settings(cycle_id: str, platform: str, body: RunSettingsBody):
    async with new_session() as session:
        assignment = await _load(session, cycle_id, platform)
        if assignment.run_status not in ("waiting_for_url", "queued", "failed"):
            raise HTTPException(status_code=409, detail="A running or completed review's settings can't change.")
        if body.llm_provider is not None and body.llm_provider not in LLM_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"llm_provider must be one of {list(LLM_PROVIDERS)}")
        if body.compile_mode is not None and body.compile_mode not in ALLOWED_COMPILE_MODES[assignment.platform]:
            raise HTTPException(status_code=400, detail=f"{body.compile_mode!r} isn't a valid compile check for {assignment.platform}")
        model = ((body.llm_model or "").strip() or None) if body.llm_provider else None
        await crud.update_assignment(
            session, assignment, override_llm_provider=body.llm_provider, override_llm_model=model,
            override_compile_mode=body.compile_mode,
        )
        return await _one(session, assignment)
