import jwt as pyjwt
from fastapi import HTTPException, Request

from app.auth.token import decode_access_token
from app.db import crud
from app.db.models import User
from app.db.session import new_session

COOKIE_NAME = "access_token"


async def get_current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    async with new_session() as session:
        user = await crud.get_user_by_id(session, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user

