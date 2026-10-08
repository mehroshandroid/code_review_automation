from cryptography.fernet import Fernet

from app.secrets import decrypt, encrypt


def test_roundtrip_with_explicit_key(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt("my-pat-value")
    assert token != "my-pat-value"
    assert decrypt(token) == "my-pat-value"


def test_roundtrip_with_key_derived_from_auth_secret(monkeypatch):
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("AUTH_SECRET_KEY", "some-secret")
    assert decrypt(encrypt("abc")) == "abc"


def test_decrypt_with_wrong_key_returns_none(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt("abc")
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert decrypt(token) is None


def test_decrypt_none_or_garbage_returns_none():
    assert decrypt(None) is None
    assert decrypt("not-a-token") is None
