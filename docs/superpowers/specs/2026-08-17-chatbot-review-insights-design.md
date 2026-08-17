# Chatbot for Review Insights: Design Spec

**Status:** Approved
**Date:** 2026-08-17
**Branch:** `chatbot-langchain-review-insights` (branched from `org-wide-phase1-db`, since the chatbot's data source is the `platform_reviews` schema built in phases 1-3, which is not yet in `master`)

## Purpose

Add a chatbot to the main project dashboard that answers natural-language analytical questions about review history, e.g.:

- "what was the reason for .NET low score"
- "what was the common issue in all .NET reviews for the current year, or for 2025"

Per the user's mentor, orchestration is built with LangChain.

## Scope

**In scope:** questions answerable from data already persisted per review — `platform`, `project_name`, `total_score_pct`, `status`, `created_at`, and each clause's `score`/`remark` (from `result_data.category_scores`), plus `warnings`/`lint_issues`.

**Explicitly out of scope:** the original uploaded code and full LLM prompt logs. These are deliberately not persisted (excluded in phase 1 for size — `code_context`/`prompt_log` can run to 120,000 characters each) and stay that way; the chatbot reasons over remarks/warnings text, not source code.

## Architecture

A new `POST /api/chat` endpoint backed by a **LangChain tool-calling agent** with exactly one read-only tool: `query_reviews(platform, year, start_date, end_date, max_score, min_score, limit)`.

- The tool runs a deterministic, parameterized SQLAlchemy query against `platform_reviews`. **The LLM never writes SQL** — there is no text-to-SQL step and therefore no injection surface. This was chosen over a LangChain SQL agent (text-to-SQL: more flexible but the LLM runs real queries against the DB, needs a locked-down read-only role and heavy guardrails to be safe) and over full RAG with a vector store (adds real infra — embeddings, a vector DB, chunking — that this app's data volume, structured rows rather than a large unstructured document corpus, doesn't need yet).
- The tool returns, per matching review: `id`, `project_name`, `platform`, `total_score_pct`, `created_at`, and the **failing clauses' remarks only** (`score == 0` sub-criteria) — that's what's relevant to "why low" / "common issues", and keeps the prompt small even across dozens of reviews.
- The agent may call the tool once or more per question, then the LLM synthesizes the narrative answer grounded in whatever the tool returned. The agent's system prompt explicitly instructs it to answer only from the tool's returned data and say so plainly when nothing matches, rather than filling gaps from general knowledge.
- One tool covers both example questions. More tools (e.g. cross-platform comparison, per-project trend) can be added later without a redesign — this scales by adding tools, not rearchitecting the agent.

## Backend

**New files:**
- `backend/app/chatbot/tools.py` — the `query_reviews` tool: a plain async function wrapped with LangChain's `@tool` decorator. Filters: `platform` (exact match), `year` (matches `created_at`'s year) OR explicit `start_date`/`end_date`, `max_score`/`min_score` (bounds on `total_score_pct`), `limit` (default 20, max 50, to bound prompt size). Queries only `status != 'error'` reviews (errored reviews have no scores/remarks to reason about). For each matching review, includes only sub-criteria with `score == 0` from `result_data.category_scores`, plus `warnings`/`lint_issues`.
- `backend/app/chatbot/agent.py` — builds the LangChain `AgentExecutor`: `AzureChatOpenAI` (from `langchain-openai`) configured from the *same* env vars `app/analyzer/openai_client.py` already uses (`OPENAI_API_BASE`, `OPENAI_DEPLOYMENT_NAME`, `OPENAI_API_VERSION`, `AZURE_OPENAI_KEY`) — no new config surface. Exposes `async def answer_question(message: str, history: list[dict]) -> dict` returning `{"answer": str, "sources": list[dict]}`, where `sources` is the flattened list of reviews the tool call(s) returned (deduplicated by review id).
- `backend/app/api/chat.py` — `POST /api/chat`. Request body: `{"message": str, "history": [{"role": "user"|"assistant", "content": str}, ...]}` (frontend owns and resends the conversation history each turn; no server-side persistence — matches the app's current no-auth/no-user-accounts POC stage). Response: `{"answer": str, "sources": [...]}`.
- `backend/requirements.txt` gains `langchain` and `langchain-openai`.
- `backend/main.py` registers the new chat router.

**Stub mode:** when `AZURE_OPENAI_KEY` is unset (same `is_stub_mode()` check `openai_client.py` already uses), `/api/chat` skips building the agent entirely and returns a fixed response explaining chat isn't configured, rather than failing — matches the existing graceful-degradation pattern used for review scoring in local dev without a hosted key.

## Frontend

**New files:**
- `frontend/src/components/ChatWidget.jsx` — a floating chat bubble, bottom-right, rendered only on `ProjectDashboardPage.jsx` (not other pages). Click expands into a compact panel (~360×480px) built from existing design-system classes (`.card`, `.btn`, `.input`) with a message list, text input, and send button; collapses back to the bubble.
  - Message history lives in component state as `[{role, content, sources?}, ...]` — lost on page refresh (no persistence, matching the backend's stateless design).
  - Sending a message: appends the user's message, POSTs `{message, history}` to `/api/chat` via `sendChatMessage`, shows a loading spinner (reusing `SpinnerIcon`), appends the assistant's `{answer, sources}` response on success, shows an inline error message on failure.
  - **Rendering a response:** the narrative `answer` text always renders. When `sources` is non-empty, a compact inline table renders below it (columns: project, platform, score, date), each row clickable and navigating to the existing `/reports/:reviewId` page. When `sources` has 2+ entries with varying `created_at` dates, an additional small inline sparkline-style line chart of `total_score_pct` over time renders, reusing the same Recharts `LineChart` pattern already used in `ProjectReviewHistory.jsx`, sized compactly for the widget. The backend has no chart-specific logic — both the table and the chart are derived client-side from the same `sources` array.
- `frontend/src/services/api.js` gains `sendChatMessage(message, history)`.

`ProjectDashboardPage.jsx` renders `<ChatWidget />` once, alongside its existing content.

## Testing

- **Backend:** `test_chatbot_tools.py` — `query_reviews` against in-memory SQLite, covering platform filter, year filter, score-threshold filters, the failing-clauses-only extraction, and the `status != 'error'` exclusion. `test_chat_api.py` — `/api/chat` with the LangChain agent **mocked** (no real Azure OpenAI calls in tests/CI, matching how `openai_client.py`'s own tests avoid live network calls) covering a normal Q&A round-trip, multi-turn history being forwarded to the agent, and the stub-mode-when-unconfigured path.
- **Frontend:** `ChatWidget.test.jsx` — bubble opens/closes, sending a message calls `sendChatMessage` with the accumulated history, a mocked response with `sources` renders the table and (when applicable) the sparkline, loading and error states render correctly.
