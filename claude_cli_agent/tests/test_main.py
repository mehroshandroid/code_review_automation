from fastapi.testclient import TestClient

import main as main_module
from main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_endpoint_returns_the_claude_result(monkeypatch):
    async def fake_run_claude(prompt):
        assert prompt == "score this"
        return {"status": "ok", "result": "the answer"}

    monkeypatch.setattr(main_module, "run_claude", fake_run_claude)

    response = client.post("/ask", json={"prompt": "score this"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "result": "the answer"}


def test_ask_endpoint_returns_the_claude_error(monkeypatch):
    async def fake_run_claude(prompt):
        return {"status": "error", "message": "claude CLI process timed out."}

    monkeypatch.setattr(main_module, "run_claude", fake_run_claude)

    response = client.post("/ask", json={"prompt": "score this"})

    assert response.status_code == 200
    assert response.json() == {"status": "error", "message": "claude CLI process timed out."}


def test_ask_endpoint_requires_a_prompt_field():
    response = client.post("/ask", json={})

    assert response.status_code == 422
