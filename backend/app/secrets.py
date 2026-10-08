"""Symmetric encryption for secrets stored in the database (e.g. the org DevOps PAT).

Uses SETTINGS_ENCRYPTION_KEY (a Fernet key) when set, otherwise a key derived
from AUTH_SECRET_KEY -- changing either makes previously stored secrets
unreadable, which decrypt() reports as None rather than raising.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if not key:
        secret = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-key")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
