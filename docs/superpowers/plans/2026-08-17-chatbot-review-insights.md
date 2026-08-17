# Chatbot for Review Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating chatbot to the main project dashboard that answers natural-language questions about review history (e.g. "what was the reason for .NET low score", "common issue in .NET reviews for 2025"), using a LangChain tool-calling agent over a single deterministic, read-only DB query tool.

**Architecture:** `POST /api/chat` builds a LangChain `AgentExecutor` (Azure OpenAI via `langchain-openai`, reusing the app's existing `OPENAI_API_BASE`/`OPENAI_DEPLOYMENT_NAME`/`OPENAI_API_VERSION`/`AZURE_OPENAI_KEY` env vars) bound to one tool, `query_reviews`, which runs a parameterized SQLAlchemy query against `platform_reviews` — the LLM never writes SQL. The agent may call the tool one or more times, then synthesizes a narrative answer from whatever the tool returned. The endpoint extracts every review the tool call(s) returned as `sources`; the frontend renders those as a compact table and (when there are 2+ dated points) a small trend chart, entirely client-side — the backend has no chart-specific logic.

**Tech Stack:** FastAPI + SQLAlchemy (existing), `langchain==0.3.30` + `langchain-openai==0.3.35` (new), React + Recharts (existing).

## Global Constraints

- Chat only ever reasons over data already persisted per review (`platform`, `project_name`, `total_score_pct`, `status`, `created_at`, `result_data.category_scores`/`warnings`/`lint_issues`) — never the original code or full LLM prompt logs (those are deliberately not persisted).
- The LLM never writes or executes SQL. `query_reviews` is a fixed, typed, parameterized query function; the agent can only choose its arguments, never its implementation.
- Chat always uses Azure OpenAI (`AzureChatOpenAI`), regardless of the org's configured default provider for reviews (ollama vs azure) — this was an explicit design decision, not an oversight.
- No conversation persistence: the frontend owns and resends the full message history each turn; nothing is stored server-side. This matches the app's current no-auth/no-user-accounts POC stage.
- When `AZURE_OPENAI_KEY` is unset (`app.analyzer.openai_client.is_stub_mode()` returns `True`), `/api/chat` must return a clear "not configured" message instead of failing — matches the existing graceful-degradation pattern used for review scoring.
- The chat widget renders only on `ProjectDashboardPage.jsx`, not other pages.
- Rich answer content (tables/charts) renders **compactly inline** in the floating widget — the widget does not resize/expand for data-heavy answers.
- All new backend tests run against in-memory SQLite with no live Azure OpenAI calls (mock the LangChain agent at the `app.chatbot.agent.answer_question` / `app.chatbot.agent._build_agent_executor` boundary), consistent with how the rest of this test suite avoids live LLM calls.

---

## File Structure

- Create: `backend/app/chatbot/__init__.py` — empty, makes this a package
- Create: `backend/app/chatbot/tools.py` — the `query_reviews` LangChain tool + its pure, directly-testable implementation
- Create: `backend/app/chatbot/agent.py` — builds the `AgentExecutor` and exposes `answer_question(message, history)`
- Create: `backend/app/api/chat.py` — `POST /api/chat` FastAPI router
- Modify: `backend/requirements.txt` — add `langchain==0.3.30`, `langchain-openai==0.3.35`
- Modify: `backend/main.py` — register the new chat router
- Create: `backend/tests/test_chatbot_tools.py`
- Create: `backend/tests/test_chatbot_agent.py`
- Create: `backend/tests/test_chat_api.py`
- Modify: `frontend/src/services/api.js` — add `sendChatMessage(message, history)`
- Modify: `frontend/src/icons.jsx` — add `ChatIcon`
- Create: `frontend/src/components/ChatWidget.jsx`
- Create: `frontend/src/components/ChatWidget.test.jsx`
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx` — render `<ChatWidget />`
- Modify: `frontend/src/pages/ProjectDashboardPage.test.jsx` — one test confirming it renders

---

### Task 1: `query_reviews` LangChain tool

**Files:**
- Create: `backend/app/chatbot/__init__.py`
- Create: `backend/app/chatbot/tools.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_chatbot_tools.py`

**Interfaces:**
- Consumes: `app.db.models.PlatformReview`, `app.db.session.new_session` (existing)
- Produces: `app.chatbot.tools.query_reviews` (LangChain `@tool`-decorated, used by Task 2's agent), `app.chatbot.tools._query_reviews(platform=None, year=None, start_date=None, end_date=None, max_score=None, min_score=None, limit=20) -> list[dict]` (the plain async implementation, directly testable), `app.chatbot.tools.MAX_LIMIT = 50`, `app.chatbot.tools.DEFAULT_LIMIT = 20`. Each returned dict: `{"id": str, "project_name": str, "platform": str, "total_score_pct": float | None, "created_at": str (ISO), "failing_clauses": [{"id": str, "description": str, "remark": str}], "warnings": list[str], "lint_issues": list}`.

- [ ] **Step 1: Add the new dependencies**

Add to `backend/requirements.txt` (append, don't reorder existing lines):

```
langchain==0.3.30
langchain-openai==0.3.35
```

Run: `cd backend && venv/bin/pip install -r requirements.txt`
Expected: installs cleanly (already verified compatible on Python 3.11 during planning).

- [ ] **Step 2: Create the package init**

Create `backend/app/chatbot/__init__.py` (empty file).

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_chatbot_tools.py`:

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.chatbot.tools as tools_module
from app.chatbot.tools import DEFAULT_LIMIT, MAX_LIMIT, _query_reviews
from app.db.models import Base, PlatformReview


@pytest.fixture
async def sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(tools_module, "new_session", lambda: maker())
    yield maker
    await engine.dispose()


async def _add_review(sessionmaker, **overrides):
    defaults = dict(
        id="r1", project_id=None, platform=".NET", status="pending_approval", project_name="Moove",
        created_at=datetime(2025, 6, 1, tzinfo=timezone.utc), completed_at=None,
        total_score_pct=60.0, llm_provider="azure", llm_model=None, compile_check_mode="compiler",
        source="upload", workbook_path=None,
        result_data={
            "category_scores": [
                {"id": "1", "name": "Structure", "sub_criteria": [
                    {"id": "1.1", "description": "Naming", "score": 0, "remark": "Inconsistent casing"},
                    {"id": "1.2", "description": "Formatting", "score": 1, "remark": "Fine"},
                ]},
            ],
            "warnings": ["Outdated SDK"],
            "lint_issues": [],
        },
    )
    defaults.update(overrides)
    async with sessionmaker() as session:
        session.add(PlatformReview(**defaults))
        await session.commit()


async def test_query_reviews_filters_by_platform(sessionmaker):
    await _add_review(sessionmaker, id="r1", platform=".NET")
    await _add_review(sessionmaker, id="r2", platform="Android")

    results = await _query_reviews(platform=".NET")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_platform_match_is_case_insensitive(sessionmaker):
    await _add_review(sessionmaker, id="r1", platform=".NET")

    results = await _query_reviews(platform=".net")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_year(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2024, 6, 1, tzinfo=timezone.utc))

    results = await _query_reviews(year=2025)

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_date_range(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 3, 15, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2025, 9, 1, tzinfo=timezone.utc))

    results = await _query_reviews(start_date="2025-01-01", end_date="2025-06-01")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_max_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)
    await _add_review(sessionmaker, id="r2", total_score_pct=95.0)

    results = await _query_reviews(max_score=70)

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_min_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)
    await _add_review(sessionmaker, id="r2", total_score_pct=95.0)

    results = await _query_reviews(min_score=90)

    assert [r["id"] for r in results] == ["r2"]


async def test_query_reviews_excludes_errored_reviews(sessionmaker):
    await _add_review(sessionmaker, id="r1", status="pending_approval")
    await _add_review(sessionmaker, id="r2", status="error")

    results = await _query_reviews()

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_returns_only_failing_clauses(sessionmaker):
    await _add_review(sessionmaker, id="r1")

    results = await _query_reviews()

    assert results[0]["failing_clauses"] == [{"id": "1.1", "description": "Naming", "remark": "Inconsistent casing"}]


async def test_query_reviews_includes_warnings_and_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)

    results = await _query_reviews()

    assert results[0]["warnings"] == ["Outdated SDK"]
    assert results[0]["total_score_pct"] == 60.0
    assert results[0]["project_name"] == "Moove"


async def test_query_reviews_respects_limit_and_orders_newest_first(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 6, 2, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))

    results = await _query_reviews(limit=1)

    assert len(results) == 1
    assert results[0]["id"] == "r1"


def test_default_and_max_limit_constants():
    assert DEFAULT_LIMIT == 20
    assert MAX_LIMIT == 50
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_chatbot_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chatbot'`

- [ ] **Step 5: Implement the tool**

Create `backend/app/chatbot/tools.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import extract, select

from app.db.models import PlatformReview
from app.db.session import new_session

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _failing_clauses(result_data: dict) -> list[dict]:
    failing = []
    for category in result_data.get("category_scores", []):
        for sub in category.get("sub_criteria", []):
            if sub.get("score") == 0:
                failing.append({
                    "id": sub.get("id"),
                    "description": sub.get("description"),
                    "remark": sub.get("remark"),
                })
    return failing


def _review_to_source(review: PlatformReview) -> dict:
    result_data = review.result_data or {}
    return {
        "id": review.id,
        "project_name": review.project_name,
        "platform": review.platform,
        "total_score_pct": float(review.total_score_pct) if review.total_score_pct is not None else None,
        "created_at": review.created_at.isoformat(),
        "failing_clauses": _failing_clauses(result_data),
        "warnings": result_data.get("warnings", []),
        "lint_issues": result_data.get("lint_issues", []),
    }


async def _query_reviews(
    platform: Optional[str] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_score: Optional[float] = None,
    min_score: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    limit = max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))
    query = select(PlatformReview).where(PlatformReview.status != "error")
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if year is not None:
        query = query.where(extract("year", PlatformReview.created_at) == year)
    if start_date:
        query = query.where(PlatformReview.created_at >= datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc))
    if end_date:
        query = query.where(PlatformReview.created_at <= datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc))
    if max_score is not None:
        query = query.where(PlatformReview.total_score_pct <= max_score)
    if min_score is not None:
        query = query.where(PlatformReview.total_score_pct >= min_score)
    query = query.order_by(PlatformReview.created_at.desc()).limit(limit)

    async with new_session() as session:
        result = await session.execute(query)
        reviews = result.scalars().all()
    return [_review_to_source(review) for review in reviews]


@tool
async def query_reviews(
    platform: Optional[str] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_score: Optional[float] = None,
    min_score: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Query code review history.

    platform: e.g. "Android", "iOS", ".NET", "Web (React)". Case-insensitive.
    year: 4-digit year, e.g. 2025.
    start_date/end_date: ISO date strings (YYYY-MM-DD), an alternative to
      year for custom ranges.
    max_score/min_score: bounds on the review's total_score_pct (0-100),
      e.g. max_score=70 for "low-scoring" reviews.
    limit: max reviews to return (default 20, capped at 50).

    Returns, per matching review: id, project_name, platform,
    total_score_pct, created_at, the clauses it failed (id/description/
    remark), and its warnings/lint_issues. Excludes errored reviews (they
    have no scores to reason about).
    """
    return await _query_reviews(platform, year, start_date, end_date, max_score, min_score, limit)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_chatbot_tools.py -v`
Expected: PASS (12 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/chatbot/__init__.py backend/app/chatbot/tools.py backend/tests/test_chatbot_tools.py
git commit -m "feat: add query_reviews LangChain tool for the review-insights chatbot"
```

---

### Task 2: Agent builder

**Files:**
- Create: `backend/app/chatbot/agent.py`
- Test: `backend/tests/test_chatbot_agent.py`

**Interfaces:**
- Consumes: `app.chatbot.tools.query_reviews` (Task 1)
- Produces: `app.chatbot.agent.answer_question(message: str, history: list[dict]) -> dict` (used by Task 3's endpoint), returning `{"answer": str, "sources": list[dict]}`. `history` items are `{"role": "user"|"assistant", "content": str}`. `app.chatbot.agent._build_agent_executor()` (monkeypatch point for tests).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chatbot_agent.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_chatbot_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chatbot.agent'`

- [ ] **Step 3: Implement the agent builder**

Create `backend/app/chatbot/agent.py`:

```python
import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import AzureChatOpenAI

from app.chatbot.tools import query_reviews

SYSTEM_PROMPT = (
    "You are an assistant embedded in a code review dashboard. You answer "
    "questions about past code review history using the query_reviews tool "
    "-- platform, score, date, and per-clause remarks/warnings. Answer only "
    "from what the tool returns; if nothing matches, say so plainly rather "
    "than guessing or filling gaps from general knowledge. Be concise."
)


def _build_agent_executor() -> AgentExecutor:
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ["OPENAI_API_BASE"],
        azure_deployment=os.environ["OPENAI_DEPLOYMENT_NAME"],
        api_version=os.environ["OPENAI_API_VERSION"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        temperature=0.2,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, [query_reviews], prompt)
    return AgentExecutor(agent=agent, tools=[query_reviews], return_intermediate_steps=True, max_iterations=5)


def _to_lc_history(history: list[dict]) -> list:
    messages = []
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        else:
            messages.append(AIMessage(content=turn["content"]))
    return messages


def _extract_sources(intermediate_steps: list) -> list[dict]:
    sources_by_id = {}
    for _action, observation in intermediate_steps:
        if not isinstance(observation, list):
            continue
        for item in observation:
            if isinstance(item, dict) and "id" in item:
                sources_by_id[item["id"]] = item
    return list(sources_by_id.values())


async def answer_question(message: str, history: list[dict]) -> dict:
    executor = _build_agent_executor()
    result = await executor.ainvoke({"input": message, "chat_history": _to_lc_history(history)})
    return {
        "answer": result["output"],
        "sources": _extract_sources(result.get("intermediate_steps", [])),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_chatbot_agent.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/chatbot/agent.py backend/tests/test_chatbot_agent.py
git commit -m "feat: add LangChain agent builder for the review-insights chatbot"
```

---

### Task 3: `/api/chat` endpoint

**Files:**
- Create: `backend/app/api/chat.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: `app.chatbot.agent.answer_question` (Task 2), `app.analyzer.openai_client.is_stub_mode` (existing)
- Produces: `POST /api/chat` — request `{"message": str, "history": [{"role": str, "content": str}, ...]}`, response `{"answer": str, "sources": list[dict]}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chat_api.py`:

```python
from fastapi.testclient import TestClient

import app.api.chat as chat_module
from main import app

client = TestClient(app)


def test_chat_returns_a_not_configured_message_when_azure_key_is_unset(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    response = client.post("/api/chat", json={"message": "what was the reason for .NET low score", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert "not configured" in body["answer"].lower()
    assert body["sources"] == []


async def test_chat_returns_answer_question_result_when_configured(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "fake-key")

    async def fake_answer_question(message, history):
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

    async def fake_answer_question(message, history):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.chat'`

- [ ] **Step 3: Implement the endpoint**

Create `backend/app/api/chat.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel

from app.analyzer.openai_client import is_stub_mode
from app.chatbot.agent import answer_question

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("/api/chat")
async def chat(body: ChatRequest):
    if is_stub_mode():
        return {
            "answer": (
                "Chat isn't configured yet -- set AZURE_OPENAI_KEY (and "
                "OPENAI_API_BASE/OPENAI_DEPLOYMENT_NAME/OPENAI_API_VERSION) "
                "to enable it."
            ),
            "sources": [],
        }
    history = [{"role": message.role, "content": message.content} for message in body.history]
    return await answer_question(body.message, history)
```

- [ ] **Step 4: Register the router**

Modify `backend/main.py` — add the import next to the other routers and register it:

```python
from app.api.chat import router as chat_router
```

(add alongside the existing `from app.api.ollama import router as ollama_router` etc. imports)

```python
app.include_router(chat_router)
```

(add alongside the existing `app.include_router(...)` calls)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && venv/bin/python -m pytest tests/ -q`
Expected: all tests pass (previous count + 21 new tests from Tasks 1-3)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/chat.py backend/main.py backend/tests/test_chat_api.py
git commit -m "feat: add POST /api/chat endpoint for the review-insights chatbot"
```

---

### Task 4: Frontend API client function

**Files:**
- Modify: `frontend/src/services/api.js`
- Test: `frontend/src/services/api.test.js`

**Interfaces:**
- Produces: `sendChatMessage(message: string, history?: Array<{role: string, content: string}>) -> Promise<{answer: string, sources: Array}>`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/services/api.test.js` (add `sendChatMessage` to the existing import list at the top, then add this describe block near the end of the file, after the `previewSampleTemplate` describe block):

```javascript
describe("sendChatMessage", () => {
  it("posts the message and history and returns the response body", async () => {
    const response = { answer: "It commonly failed on naming.", sources: [{ id: "r1" }] };
    axios.post.mockResolvedValue({ data: response });

    const result = await sendChatMessage("what was the reason for .NET low score", [
      { role: "user", content: "earlier question" },
      { role: "assistant", content: "earlier answer" },
    ]);

    expect(result).toEqual(response);
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/chat"), {
      message: "what was the reason for .NET low score",
      history: [
        { role: "user", content: "earlier question" },
        { role: "assistant", content: "earlier answer" },
      ],
    });
  });

  it("defaults history to an empty array when omitted", async () => {
    axios.post.mockResolvedValue({ data: { answer: "ok", sources: [] } });

    await sendChatMessage("hello");

    const [, body] = axios.post.mock.calls[0];
    expect(body.history).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: FAIL with `sendChatMessage is not defined` / import error

- [ ] **Step 3: Implement the function**

Add to `frontend/src/services/api.js`, after `previewSampleTemplate`:

```javascript
export async function sendChatMessage(message, history = []) {
  const response = await axios.post(`${API_BASE_URL}/chat`, {
    message,
    history: history.map((entry) => ({ role: entry.role, content: entry.content })),
  });
  return response.data;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js
git commit -m "feat: add sendChatMessage API client function"
```

---

### Task 5: ChatWidget component

**Files:**
- Modify: `frontend/src/icons.jsx` — add `ChatIcon`
- Create: `frontend/src/components/ChatWidget.jsx`
- Test: `frontend/src/components/ChatWidget.test.jsx`

**Interfaces:**
- Consumes: `sendChatMessage` (Task 4), `ChatIcon`/`SpinnerIcon` (icons.jsx), `useNavigate` from `react-router-dom`
- Produces: `export default function ChatWidget()` — no props, self-contained. Renders a floating bubble that expands into a chat panel. Used by Task 6.

- [ ] **Step 1: Add the ChatIcon**

Add to `frontend/src/icons.jsx`, after `GearIcon`:

```jsx
export function ChatIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}
```

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/components/ChatWidget.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ChatWidget from "./ChatWidget";
import { sendChatMessage } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  sendChatMessage: jest.fn(),
}));

beforeEach(() => {
  jest.resetAllMocks();
});

function renderWidget() {
  return render(
    <MemoryRouter>
      <ChatWidget />
    </MemoryRouter>
  );
}

test("starts collapsed, showing only the open button", () => {
  renderWidget();
  expect(screen.getByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/ask a question/i)).not.toBeInTheDocument();
});

test("clicking the bubble opens the panel with the input visible", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));

  expect(screen.getByLabelText(/ask a question/i)).toBeInTheDocument();
});

test("clicking close collapses the panel again", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.click(screen.getByRole("button", { name: /close chat/i }));

  expect(screen.queryByLabelText(/ask a question/i)).not.toBeInTheDocument();
});

test("sending a message calls sendChatMessage and renders the answer", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({ answer: "It commonly failed on naming conventions.", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "what was the reason for .NET low score");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText("It commonly failed on naming conventions.")).toBeInTheDocument();
  expect(sendChatMessage).toHaveBeenCalledWith("what was the reason for .NET low score", []);
});

test("clears the input after sending", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({ answer: "ok", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  const input = screen.getByLabelText(/ask a question/i);
  await user.type(input, "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(input).toHaveValue(""));
});

test("sends accumulated history on the second message", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValueOnce({ answer: "First answer", sources: [] });
  sendChatMessage.mockResolvedValueOnce({ answer: "Second answer", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "first question");
  await user.click(screen.getByRole("button", { name: /send/i }));
  await screen.findByText("First answer");

  await user.type(screen.getByLabelText(/ask a question/i), "second question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(sendChatMessage).toHaveBeenLastCalledWith("second question", [
    { role: "user", content: "first question" },
    { role: "assistant", content: "First answer" },
  ]));
});

test("renders a sources table with project names when the answer has sources", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({
    answer: "Two reviews scored low.",
    sources: [
      { id: "r1", project_name: "Moove", platform: ".NET", total_score_pct: 60, created_at: "2025-06-01T00:00:00Z" },
      { id: "r2", project_name: "Payments", platform: ".NET", total_score_pct: 55, created_at: "2025-07-01T00:00:00Z" },
    ],
  });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText("Moove")).toBeInTheDocument();
  expect(screen.getByText("Payments")).toBeInTheDocument();
});

test("shows an error message when sendChatMessage fails", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockRejectedValue(new Error("network error"));
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
});

test("disables send while a response is loading, re-enables after", async () => {
  const user = userEvent.setup();
  let resolvePromise;
  sendChatMessage.mockReturnValue(new Promise((resolve) => { resolvePromise = resolve; }));
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  resolvePromise({ answer: "done", sources: [] });
  await waitFor(() => expect(screen.getByRole("button", { name: /send/i })).toBeEnabled());
});

test("does not send an empty or whitespace-only message", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/ask a question/i), "   ");
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  expect(sendChatMessage).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/components/ChatWidget.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './ChatWidget'`

- [ ] **Step 4: Implement the component**

Create `frontend/src/components/ChatWidget.jsx`:

```jsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChatIcon, SpinnerIcon } from "../icons";
import { sendChatMessage } from "../services/api";

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

function SourcesTable({ sources, onSelectReview }) {
  return (
    <table className="table" style={{ marginTop: "var(--space-2)", fontSize: 12 }}>
      <thead>
        <tr>
          <th>Project</th>
          <th>Platform</th>
          <th>Score</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((source) => (
          <tr key={source.id} style={{ cursor: "pointer" }} onClick={() => onSelectReview(source.id)}>
            <td>{source.project_name}</td>
            <td>{source.platform}</td>
            <td>{source.total_score_pct !== null && source.total_score_pct !== undefined ? `${source.total_score_pct}%` : "—"}</td>
            <td>{formatDate(source.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SourcesSparkline({ sources }) {
  const points = [...sources]
    .filter((source) => source.total_score_pct !== null && source.total_score_pct !== undefined)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .map((source) => ({ date: formatDate(source.created_at), score: source.total_score_pct }));

  const uniqueDates = new Set(points.map((point) => point.date));
  if (points.length < 2 || uniqueDates.size < 2) return null;

  return (
    <div style={{ height: 80, marginTop: "var(--space-2)" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <XAxis dataKey="date" tick={{ fontSize: 9 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={24} />
          <Tooltip />
          <Line dataKey="score" stroke="#1B3A6B" dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSend(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    const history = messages.map((message) => ({ role: message.role, content: message.content }));
    const nextMessages = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);
    try {
      const response = await sendChatMessage(question, history);
      setMessages([...nextMessages, { role: "assistant", content: response.answer, sources: response.sources }]);
    } catch (err) {
      setMessages([...nextMessages, {
        role: "assistant",
        content: "Sorry, something went wrong answering that. Please try again.",
        isError: true,
      }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectReview(reviewId) {
    navigate(`/reports/${reviewId}`);
  }

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-primary"
        aria-label="Open review insights chat"
        style={{
          position: "fixed", bottom: 24, right: 24, borderRadius: 999, width: 56, height: 56,
          padding: 0, boxShadow: "var(--shadow-lg)", display: "flex", alignItems: "center", justifyContent: "center",
        }}
        onClick={() => setOpen(true)}
      >
        <ChatIcon />
      </button>
    );
  }

  return (
    <div
      className="card elev-md"
      style={{
        position: "fixed", bottom: 24, right: 24, width: 360, height: 480,
        display: "flex", flexDirection: "column", padding: 0, overflow: "hidden", zIndex: 100,
      }}
    >
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--color-divider)",
      }}
      >
        <span className="card-title" style={{ fontSize: 15 }}>Ask about your reviews</span>
        <button type="button" className="btn btn-ghost" aria-label="Close chat" onClick={() => setOpen(false)}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-3) var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
        {messages.length === 0 && (
          <p className="card-body">
            Ask things like "what was the reason for .NET low score" or "common issue in .NET reviews for 2025".
          </p>
        )}
        {messages.map((message, index) => (
          <div key={index} style={{ textAlign: message.role === "user" ? "right" : "left" }}>
            <p
              className="card-body"
              style={{
                display: "inline-block", margin: 0, padding: "8px 12px", borderRadius: 12, textAlign: "left",
                background: message.role === "user" ? "var(--color-accent)" : "var(--color-surface)",
                color: message.role === "user" ? "#fff" : (message.isError ? "var(--color-brand-coral)" : "var(--color-text)"),
              }}
            >
              {message.content}
            </p>
            {message.sources && message.sources.length > 0 && (
              <>
                <SourcesTable sources={message.sources} onSelectReview={handleSelectReview} />
                <SourcesSparkline sources={message.sources} />
              </>
            )}
          </div>
        ))}
        {loading && <SpinnerIcon />}
      </div>

      <form
        onSubmit={handleSend}
        style={{ display: "flex", gap: "var(--space-2)", padding: "var(--space-3) var(--space-4)", borderTop: "1px solid var(--color-divider)" }}
      >
        <input
          type="text"
          className="input"
          aria-label="Ask a question"
          placeholder="Ask a question…"
          value={input}
          disabled={loading}
          onChange={(event) => setInput(event.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={loading || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/ChatWidget.test.jsx --watchAll=false`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/icons.jsx frontend/src/components/ChatWidget.jsx frontend/src/components/ChatWidget.test.jsx
git commit -m "feat: add ChatWidget component for the review-insights chatbot"
```

---

### Task 6: Wire ChatWidget into the dashboard

**Files:**
- Modify: `frontend/src/pages/ProjectDashboardPage.jsx`
- Modify: `frontend/src/pages/ProjectDashboardPage.test.jsx`

**Interfaces:**
- Consumes: `ChatWidget` (Task 5, default export, no props)

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/ProjectDashboardPage.test.jsx`, near the other standalone tests (after the "renders a Settings link" test is a good spot):

```javascript
test("renders the review-insights chat widget", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  expect(await screen.findByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/pages/ProjectDashboardPage.test.jsx --watchAll=false`
Expected: FAIL — no element with that accessible name

- [ ] **Step 3: Wire in the component**

Modify `frontend/src/pages/ProjectDashboardPage.jsx`. Add the import alongside the other component imports at the top:

```javascript
import ChatWidget from "../components/ChatWidget";
```

Then render it once, as a sibling of the outermost `<div>`'s content — add it right after the closing `</main>` tag and before the outer `</div>`:

```jsx
      </main>
      <ChatWidget />
    </div>
  );
}
```

(This replaces the existing `      </main>\n    </div>\n  );\n}` ending of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npx react-scripts test src/pages/ProjectDashboardPage.test.jsx --watchAll=false`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ProjectDashboardPage.jsx frontend/src/pages/ProjectDashboardPage.test.jsx
git commit -m "feat: render ChatWidget on the project dashboard"
```

---

### Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && venv/bin/python -m pytest tests/ -q`
Expected: all tests pass, zero failures

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: all tests pass, zero failures

- [ ] **Step 3: Rebuild and start the Docker stack**

Run: `docker compose up -d --build backend frontend`
Expected: both containers start; `docker compose logs backend --tail 20` shows `Application startup complete` with no import errors (confirms `langchain`/`langchain-openai` installed correctly in the container image)

- [ ] **Step 4: Smoke-test stub mode**

Run: `curl -s -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message": "test", "history": []}'`
Expected: `{"answer":"Chat isn't configured yet...","sources":[]}` if `AZURE_OPENAI_KEY` isn't set in the environment, OR a real synthesized answer if it is set — check `docker compose exec backend env | grep AZURE_OPENAI_KEY` first to know which to expect.

- [ ] **Step 5: If Azure OpenAI is configured, smoke-test a real question**

Only if `AZURE_OPENAI_KEY` is set: create at least one `.NET` review via the existing upload flow (or reuse existing data), then:

```bash
curl -s -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"message": "what was the reason for the .NET low score", "history": []}' | python3 -m json.tool
```

Expected: a real narrative `answer` grounded in actual review remarks, and `sources` listing the matching review(s). Confirms the full LangChain agent — tool-calling, Azure OpenAI call, source extraction — works end-to-end against the real database, not just mocks.

- [ ] **Step 6: Manual UI check**

Open `http://localhost:3000/` in a browser, confirm the chat bubble appears bottom-right, opens/closes, and (if Azure OpenAI is configured) a real question produces a rendered answer with a sources table.

- [ ] **Step 7: Final commit if any fixes were needed during verification**

If Steps 1-6 required any fixes, commit them:

```bash
git add -A
git commit -m "fix: address issues found during chatbot final verification"
```
