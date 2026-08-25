import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import require_roles
from app.auth.hashing import hash_password
from app.db import crud
from app.db.session import new_session

router = APIRouter(dependencies=[Depends(require_roles("admin"))])

ALLOWED_ROLES = {"admin", "reviewer", "user"}
MIN_PASSWORD_LENGTH = 8


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


def _user_to_dict(user) -> dict:
    return {
        "id": user.id, "email": user.email, "role": user.role,
        "is_active": user.is_active, "created_at": user.created_at.isoformat() if user.created_at else None,
    }


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
                password_hash=hash_password(body.password), role=body.role,
            )
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A user with this email already exists")
    return _user_to_dict(user)


@router.get("/api/users")
async def list_users():
    async with new_session() as session:
        users = await crud.list_users(session)
    return {"users": [_user_to_dict(u) for u in users]}


@router.patch("/api/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, current_user=Depends(require_roles("admin"))):
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
        user = await crud.update_user(session, user_id, role=body.role, is_active=body.is_active, password_hash=password_hash)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_dict(user)
