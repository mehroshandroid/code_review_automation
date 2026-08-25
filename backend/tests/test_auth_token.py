import datetime

import jwt
import pytest

from app.auth.token import create_access_token, decode_access_token


def test_create_and_decode_round_trips_the_user_id():
    token = create_access_token("user-123")

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"


def test_decode_raises_on_a_tampered_token():
    token = create_access_token("user-123")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)


def test_decode_raises_on_an_expired_token(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")
    expired = jwt.encode(
        {"sub": "user-123", "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)},
        "test-secret", algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)
