import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth.dependencies import COOKIE_NAME, get_current_user
from app.auth.hashing import verify_password
from app.auth.token import create_access_token
from app.db import crud
from app.db.session import new_session

router = APIRouter()

SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60


class LoginRequest(BaseModel):
    email: str
    password: str


def _cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def _user_to_dict(user) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


@router.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    async with new_session() as session:
        user = await crud.get_user_by_email(session, body.email)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(user.id)
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, samesite="lax",
        secure=_cookie_secure(), max_age=SEVEN_DAYS_SECONDS,
    )
    return _user_to_dict(user)


@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/api/auth/me")
async def me(current_user=Depends(get_current_user)):
    return _user_to_dict(current_user)
