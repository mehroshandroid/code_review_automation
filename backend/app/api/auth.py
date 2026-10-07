import os
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth import microsoft as microsoft_auth
from app.auth.dependencies import COOKIE_NAME, get_current_user
from app.auth.hashing import verify_password
from app.auth.permissions import HOME_PATHS, PROJECT_MANAGER, permissions_for
from app.auth.token import create_access_token
from app.db import crud
from app.db.session import new_session
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60
SSO_STATE_COOKIE = "sso_state"
SSO_STATE_MAX_AGE_SECONDS = 10 * 60


class LoginRequest(BaseModel):
    email: str
    password: str


def _cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def _user_to_dict(user) -> dict:
    return {
        "id": user.id, "email": user.email, "role": user.role, "name": user.name,
        "home_path": HOME_PATHS.get(user.role, "/"),
        "permissions": permissions_for(user),
    }


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


@router.get("/api/auth/microsoft/login")
async def microsoft_login():
    state = secrets.token_urlsafe(24)
    authorization_url = microsoft_auth.get_authorization_url(state)
    redirect_response = RedirectResponse(url=authorization_url)
    redirect_response.set_cookie(
        key=SSO_STATE_COOKIE, value=state, httponly=True, samesite="lax",
        secure=_cookie_secure(), max_age=SSO_STATE_MAX_AGE_SECONDS,
    )
    return redirect_response


@router.get("/api/auth/microsoft/callback")
async def microsoft_callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
):
    failure = RedirectResponse(url=f"{microsoft_auth.frontend_base_url()}/login?error=sso_failed")
    failure.delete_cookie(SSO_STATE_COOKIE)

    cookie_state = request.cookies.get(SSO_STATE_COOKIE)
    if error:
        logger.warning("Microsoft SSO callback: Microsoft reported an error: %s", error)
        return failure
    if not code or not state or not cookie_state or state != cookie_state:
        logger.warning(
            "Microsoft SSO callback: missing/mismatched state (has_code=%s, has_state=%s, has_cookie=%s, match=%s)",
            bool(code), bool(state), bool(cookie_state), state == cookie_state,
        )
        return failure

    try:
        claims = microsoft_auth.exchange_code_for_claims(code)
    except ValueError as exc:
        logger.warning("Microsoft SSO callback: token exchange failed: %s", exc)
        return failure

    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        logger.warning("Microsoft SSO callback: no email or preferred_username claim in %s", sorted(claims.keys()))
        return failure

    display_name = claims.get("name")
    async with new_session() as session:
        user = await crud.get_user_by_email(session, email)
        if user is None:
            user = await crud.create_user(
                session, user_id=str(uuid.uuid4()), email=email, password_hash="",
                role=PROJECT_MANAGER, name=display_name,
            )
        elif not user.name and display_name:
            user = await crud.update_user(session, user.id, name=display_name)

    if not user.is_active:
        logger.warning("Microsoft SSO callback: account for %s is deactivated", email)
        return failure

    token = create_access_token(user.id)
    success = RedirectResponse(url=f"{microsoft_auth.frontend_base_url()}/")
    success.delete_cookie(SSO_STATE_COOKIE)
    success.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, samesite="lax",
        secure=_cookie_secure(), max_age=SEVEN_DAYS_SECONDS,
    )
    return success


@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/api/auth/me")
async def me(current_user=Depends(get_current_user)):
    return _user_to_dict(current_user)
