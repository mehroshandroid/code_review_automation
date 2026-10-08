import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_module
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    async def _all(session, user):
        return None

    class _NullSession:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(chat_module, "visible_project_ids", _all, raising=False)
    monkeypatch.setattr(chat_module, "new_session", lambda: _NullSession(), raising=False)


def test_chat_returns_a_not_configured_message_when_azure_key_is_unset(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    response = client.post("/api/chat", json={"message": "what was the reason for .NET low score", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert "isn't configured" in body["answer"].lower()
    assert body["sources"] == []


async def test_chat_returns_answer_question_result_when_configured(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "fake-key")

    async def fake_answer_question(message, history, project_ids=None):
        assert message == "what was the reason for .NET low score"
        assert history == []
        return {"answer": "It commonly failed on naming.", "sources": [{"id": "r1"}]}

    monkeypatch.setattr(chat_module, "answer_question", fake_answer_question)

    response = client.post("/api/chat", json={"message": "what was the reason for .NET low score", "history": []})

    assert response.status_code == 200
    assert response.json() == {"answer": "It commonly failed on naming.", "sources": [{"id": "r1"}]}


async def test_chat_forwards_history_to_answer_question(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "fake-key")
    captured = {}

    async def fake_answer_question(message, history, project_ids=None):
        captured["history"] = history
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(chat_module, "answer_question", fake_answer_question)

    client.post("/api/chat", json={
        "message": "what about iOS?",
        "history": [{"role": "user", "content": "what about .NET?"}, {"role": "assistant", "content": "..."}],
    })

    assert captured["history"] == [
        {"role": "user", "content": "what about .NET?"},
        {"role": "assistant", "content": "..."},
    ]


def test_chat_defaults_history_to_empty_when_omitted(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200


async def test_chat_passes_the_users_project_scope(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "fake-key")
    captured = {}

    async def _scope(session, user):
        return {"p1"}

    async def fake_answer_question(message, history, project_ids=None):
        captured["project_ids"] = project_ids
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(chat_module, "visible_project_ids", _scope, raising=False)
    monkeypatch.setattr(chat_module, "answer_question", fake_answer_question)

    client.post("/api/chat", json={"message": "q", "history": []})

    assert captured["project_ids"] == {"p1"}
