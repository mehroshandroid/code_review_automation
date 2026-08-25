import os
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)


def _secret_key() -> str:
    return os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-key")


def create_access_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + TOKEN_TTL}
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
