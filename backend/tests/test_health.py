from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok_and_stub_mode_when_no_key(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["azure_openai_connected"] is False
