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
