import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.reviews import _review_summary_to_dict
from app.auth.dependencies import get_current_user
from app.auth.permissions import PROJECT_MANAGER, can, require_permission, visible_project_ids
from app.automation.uploads import delete_cycle_uploads
from app.db import crud
from app.db.session import new_session
from app.quarterly import canonical_platform

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


class SetManagersRequest(BaseModel):
    user_ids: list[str]


def _project_to_dict(
    project, review_count: int = 0, manager_ids: list[str] | None = None, platforms: list[str] | None = None,
) -> dict:
    data = {
        "id": project.id, "name": project.name, "created_at": project.created_at.isoformat(),
        "review_count": review_count,
    }
    if manager_ids is not None:
        data["manager_ids"] = manager_ids
    if platforms is not None:
        data["platforms"] = platforms
    return data


@router.post("/api/projects")
async def create_project(body: CreateProjectRequest, user=Depends(require_permission("projects.create"))):
    async with new_session() as session:
        try:
            project = await crud.create_project(session, project_id=str(uuid.uuid4()), name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        return _project_to_dict(project, manager_ids=[], platforms=[])


@router.get("/api/projects")
async def list_projects(user=Depends(get_current_user)):
    async with new_session() as session:
        staff = can(user, "projects.view")
        scope = None if staff else await visible_project_ids(session, user)
        projects = await crud.list_projects(session, project_ids=scope)
        counts = await crud.count_reviews_by_project(session)
        managers = await crud.get_manager_ids_for_projects(session, [p.id for p in projects]) if staff else {}
        platforms = await crud.get_platforms_for_projects(session, [p.id for p in projects])
    return {"projects": [
        _project_to_dict(p, counts.get(p.id, 0), managers.get(p.id, []) if staff else None, platforms.get(p.id, []))
        for p in projects
    ]}


@router.patch("/api/projects/{project_id}")
async def update_project(project_id: str, body: CreateProjectRequest, user=Depends(require_permission("projects.edit"))):
    async with new_session() as session:
        try:
            project = await crud.update_project_name(session, project_id=project_id, name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        return _project_to_dict(project, platforms=platforms)


@router.put("/api/projects/{project_id}/managers")
async def set_project_managers(project_id: str, body: SetManagersRequest, user=Depends(require_permission("projects.assign_pm"))):
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        for user_id in body.user_ids:
            candidate = await crud.get_user_by_id(session, user_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
            if candidate.role != PROJECT_MANAGER or not candidate.is_active:
                raise HTTPException(status_code=400, detail=f"{candidate.email} is not an active project manager.")
        await crud.set_managers_for_project(session, project_id, body.user_ids)
        manager_ids = (await crud.get_manager_ids_for_projects(session, [project_id]))[project_id]
        review_count = await crud.count_reviews_for_project(session, project_id)
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        return _project_to_dict(project, review_count, manager_ids, platforms)


class SetPlatformsRequest(BaseModel):
    platforms: list[str]


@router.put("/api/projects/{project_id}/platforms")
async def set_project_platforms(project_id: str, body: SetPlatformsRequest, user=Depends(require_permission("projects.edit"))):
    canonical = [canonical_platform(p) for p in body.platforms]
    if any(p is None for p in canonical):
        raise HTTPException(status_code=400, detail="platforms must be Android, iOS or .NET")
    async with new_session() as session:
        project = await crud.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await crud.set_platforms_for_project(session, project_id, canonical)
        platforms = (await crud.get_platforms_for_projects(session, [project_id]))[project_id]
        review_count = await crud.count_reviews_for_project(session, project_id)
        return _project_to_dict(project, review_count, platforms=platforms)


@router.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, user=Depends(require_permission("projects.delete"))):
    async with new_session() as session:
        if await crud.get_project(session, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        review_count = await crud.count_reviews_for_project(session, project_id)
        if review_count > 0:
            raise HTTPException(status_code=409, detail=f"This project has {review_count} reviews and can't be deleted.")
        delete_cycle_uploads(await crud.list_cycle_ids_for_project(session, project_id))
        await crud.delete_project(session, project_id)
    return Response(status_code=204)


@router.get("/api/project-managers")
async def list_project_managers(user=Depends(require_permission("projects.assign_pm"))):
    async with new_session() as session:
        candidates = await crud.list_reviewer_candidates(session, frozenset({PROJECT_MANAGER}))
    return {"managers": [{"id": c.id, "email": c.email, "name": c.name} for c in candidates]}


@router.get("/api/projects/{project_id}/reviews")
async def list_project_reviews(project_id: str, user=Depends(get_current_user)):
    async with new_session() as session:
        scope = await visible_project_ids(session, user)
        if scope is not None and project_id not in scope:
            raise HTTPException(status_code=404, detail="Project not found")
        reviews = await crud.list_reviews_for_project(session, project_id)
        return {"reviews": [_review_summary_to_dict(r) for r in reviews]}
