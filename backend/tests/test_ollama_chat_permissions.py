from fastapi.testclient import TestClient

import app.api.ollama as ollama_module
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


def test_list_ollama_models_forbidden_for_pm():
    _as("project_manager")
    assert client.get("/api/ollama/models").status_code == 403


def test_list_ollama_models_allowed_for_management(monkeypatch):
    _as("management")

    async def _models():
        return []

    monkeypatch.setattr(ollama_module.ollama_client, "list_models", _models)
    assert client.get("/api/ollama/models").status_code == 200


def test_chat_requires_login():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_forbidden_for_coordinator():
    _as("coordinator")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 403


def test_chat_forbidden_for_reviewer():
    _as("reviewer")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 403


def test_chat_allowed_for_project_manager(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    _as("project_manager")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
