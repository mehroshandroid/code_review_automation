from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.db.models import User
from main import app

client = TestClient(app)


def _as(role):
    user = User(id="u1", email=f"{role}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_ollama_models_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/ollama/models")
    assert response.status_code == 401


def test_list_ollama_models_allows_the_user_role():
    _as("user")
    response = client.get("/api/ollama/models")
    assert response.status_code == 200


def test_chat_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_allows_the_user_role():
    _as("user")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
