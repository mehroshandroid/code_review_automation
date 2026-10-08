import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.auth.hashing import hash_password
from app.auth.permissions import ALL_ROLES, PROJECT_MANAGER, require_permission
from app.db import crud
from app.db.session import new_session

router = APIRouter(dependencies=[Depends(require_permission("users.manage"))])

ALLOWED_ROLES = ALL_ROLES
MIN_PASSWORD_LENGTH = 8


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str
    name: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    name: str | None = None


def _user_to_dict(user, project_ids: list[str] | None = None) -> dict:
    data = {
        "id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "is_active": user.is_active, "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if user.role == PROJECT_MANAGER:
        data["project_ids"] = project_ids or []
    return data


@router.post("/api/users")
async def create_user(body: CreateUserRequest):
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(ALLOWED_ROLES)}")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    async with new_session() as session:
        try:
            user = await crud.create_user(
                session, user_id=str(uuid.uuid4()), email=body.email,
                password_hash=hash_password(body.password), role=body.role, name=body.name,
            )
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A user with this email already exists")
    return _user_to_dict(user)


@router.get("/api/users")
async def list_users():
    async with new_session() as session:
        users = await crud.list_users(session)
        assignments = await crud.get_project_ids_for_managers(
            session, [u.id for u in users if u.role == PROJECT_MANAGER],
        )
    return {"users": [_user_to_dict(u, assignments.get(u.id)) for u in users]}


@router.patch("/api/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, current_user=Depends(require_permission("users.manage"))):
    if body.role is not None and body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(ALLOWED_ROLES)}")
    if body.password is not None and len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if user_id == current_user.id:
        if body.role is not None and body.role != current_user.role:
            raise HTTPException(status_code=400, detail="You cannot change your own role.")
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    password_hash = hash_password(body.password) if body.password is not None else None
    async with new_session() as session:
        user = await crud.update_user(
            session, user_id, role=body.role, is_active=body.is_active, password_hash=password_hash, name=body.name,
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.role != PROJECT_MANAGER or not user.is_active:
            await crud.clear_projects_for_manager(session, user.id)
        assignments = await crud.get_project_ids_for_managers(session, [user.id]) if user.role == PROJECT_MANAGER else {}
    return _user_to_dict(user, assignments.get(user.id))


@router.delete("/api/users/{user_id}", status_code=204)
async def delete_user(user_id: str, current_user=Depends(require_permission("users.manage"))):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    async with new_session() as session:
        deleted = await crud.delete_user(session, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=204)
