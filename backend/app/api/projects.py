import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.db import crud
from app.db.session import new_session

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


def _project_to_dict(project) -> dict:
    return {"id": project.id, "name": project.name, "created_at": project.created_at.isoformat()}


@router.post("/api/projects")
async def create_project(body: CreateProjectRequest):
    async with new_session() as session:
        try:
            project = await crud.create_project(session, project_id=str(uuid.uuid4()), name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        return _project_to_dict(project)


@router.get("/api/projects")
async def list_projects():
    async with new_session() as session:
        projects = await crud.list_projects(session)
        return {"projects": [_project_to_dict(p) for p in projects]}


@router.patch("/api/projects/{project_id}")
async def update_project(project_id: str, body: CreateProjectRequest):
    async with new_session() as session:
        try:
            project = await crud.update_project_name(session, project_id=project_id, name=body.name)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _project_to_dict(project)


def _review_summary_to_dict(review) -> dict:
    result_data = review.result_data or {}
    return {
        "id": review.id,
        "platform": review.platform,
        "status": review.status,
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "total_score_pct": float(review.total_score_pct) if review.total_score_pct is not None else None,
        # Trimmed to just id/name/percent_points -- the dashboard's
        # per-clause chart doesn't need sub_criteria/remarks, and this
        # endpoint already returns every review for a project in one call.
        "category_scores": [
            {"id": category.get("id"), "name": category.get("name"), "percent_points": category.get("percent_points")}
            for category in result_data.get("category_scores", [])
        ],
    }


@router.get("/api/projects/{project_id}/reviews")
async def list_project_reviews(project_id: str):
    async with new_session() as session:
        reviews = await crud.list_reviews_for_project(session, project_id)
        return {"reviews": [_review_summary_to_dict(r) for r in reviews]}
