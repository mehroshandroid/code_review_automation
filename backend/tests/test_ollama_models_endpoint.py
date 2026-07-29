from fastapi.testclient import TestClient

import app.api.ollama as ollama_api
from main import app

client = TestClient(app)


def test_list_ollama_models_returns_installed_models(monkeypatch):
    async def fake_list_models():
        return ["mistral:latest", "qwen2.5-coder:7b"]

    monkeypatch.setattr(ollama_api.ollama_client, "list_models", fake_list_models)

    response = client.get("/api/ollama/models")

    assert response.status_code == 200
    assert response.json() == {"models": ["mistral:latest", "qwen2.5-coder:7b"]}


def test_list_ollama_models_returns_empty_list_when_unreachable(monkeypatch):
    async def fake_list_models():
        return []

    monkeypatch.setattr(ollama_api.ollama_client, "list_models", fake_list_models)

    response = client.get("/api/ollama/models")

    assert response.status_code == 200
    assert response.json() == {"models": []}
