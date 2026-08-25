from langchain_core.messages import AIMessage, HumanMessage

import app.chatbot.agent as agent_module
from app.chatbot.agent import answer_question


class _FakeExecutor:
    def __init__(self, result):
        self._result = result
        self.captured_input = None

    async def ainvoke(self, payload):
        self.captured_input = payload
        return self._result


async def test_answer_question_returns_output_and_sources(monkeypatch):
    source = {
        "id": "r1", "project_name": "Moove", "platform": ".NET", "total_score_pct": 60.0,
        "created_at": "2025-06-01T00:00:00+00:00", "failing_clauses": [], "warnings": [], "lint_issues": [],
    }
    fake_executor = _FakeExecutor({
        "output": "The .NET reviews commonly failed on naming conventions.",
        "intermediate_steps": [(object(), [source])],
    })
    monkeypatch.setattr(agent_module, "_build_agent_executor", lambda: fake_executor)

    result = await answer_question("what was the reason for .NET low score", [])

    assert result["answer"] == "The .NET reviews commonly failed on naming conventions."
    assert result["sources"] == [source]


async def test_answer_question_deduplicates_sources_across_tool_calls(monkeypatch):
    source = {
        "id": "r1", "project_name": "Moove", "platform": ".NET", "total_score_pct": 60.0,
        "created_at": "2025-06-01T00:00:00+00:00", "failing_clauses": [], "warnings": [], "lint_issues": [],
    }
    fake_executor = _FakeExecutor({
        "output": "answer",
        "intermediate_steps": [(object(), [source]), (object(), [source])],
    })
    monkeypatch.setattr(agent_module, "_build_agent_executor", lambda: fake_executor)

    result = await answer_question("question", [])

    assert result["sources"] == [source]


async def test_answer_question_ignores_non_list_observations(monkeypatch):
    fake_executor = _FakeExecutor({
        "output": "answer",
        "intermediate_steps": [(object(), "not a tool result list")],
    })
    monkeypatch.setattr(agent_module, "_build_agent_executor", lambda: fake_executor)

    result = await answer_question("question", [])

    assert result["sources"] == []


async def test_answer_question_handles_missing_intermediate_steps(monkeypatch):
    fake_executor = _FakeExecutor({"output": "answer"})
    monkeypatch.setattr(agent_module, "_build_agent_executor", lambda: fake_executor)

    result = await answer_question("question", [])

    assert result == {"answer": "answer", "sources": []}


async def test_answer_question_forwards_message_and_history_to_the_executor(monkeypatch):
    fake_executor = _FakeExecutor({"output": "answer", "intermediate_steps": []})
    monkeypatch.setattr(agent_module, "_build_agent_executor", lambda: fake_executor)

    await answer_question(
        "what about iOS?",
        [{"role": "user", "content": "what about .NET?"}, {"role": "assistant", "content": "..."}],
    )

    assert fake_executor.captured_input["input"] == "what about iOS?"
    history = fake_executor.captured_input["chat_history"]
    assert isinstance(history[0], HumanMessage) and history[0].content == "what about .NET?"
    assert isinstance(history[1], AIMessage) and history[1].content == "..."
