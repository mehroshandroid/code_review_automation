# CodeAssure — Progress Log

CodeAssure (formerly "Code Review Automation") is an AI-assisted tool for reviewing source code. You give it an Android, iOS or .NET project as an uploaded ZIP or an Azure DevOps repo. It runs structural, secrets and compile/lint checks on the project, then has an LLM score each clause of the org's Excel review template. Completed reviews are stored in Postgres and appear on a project dashboard.

This file records what has been built and in what order, so a future developer can see what exists and why. For the design behind each feature, read the specs in `docs/superpowers/specs/`. Each spec has a matching step-by-step plan in `docs/superpowers/plans/`.

_Last updated: 2026-10-06_

---

## Architecture at a glance

| Component | Location | Runs as | Purpose |
|---|---|---|---|
| Backend API | `backend/` | Docker (`backend`) | FastAPI service that runs the review pipeline, auth/RBAC, projects, settings and chat |
| Frontend | `frontend/` | Docker (`frontend`, port 3000) | React (CRA) single-page app, served with `serve -s build` |
| Database | — | Docker (`postgres`, plus `adminer` on port 8080) | Stores projects, reviews, users, org settings, clause checklists and sample templates. Schema is managed by Alembic |
| Android compiler | `compiler/` | Docker (`compiler`, amd64) | Runs Gradle Lint for clause 1.4 |
| .NET compiler | `dotnet_compiler/` | Docker (`dotnet-compiler`) | Runs `dotnet build` diagnostics |
| Mac build agent | `mac_build_agent/` | Host-native macOS | Runs `xcodebuild` lint for iOS, and Android lint in "local" mode |
| Claude CLI agent | `claude_cli_agent/` | Host-native | Scores reviews with the local `claude` CLI |

LLM providers: Azure OpenAI, Ollama (local) and Claude CLI (local). Admins set the default in Settings. A different provider can be picked for each review.

---

## Timeline

### Phase 0: Android proof of concept (2026-07-23 to 07-24)
- Backend analyzers: Gradle/SDK version checks, hardcoded-secrets scanner, project structure validation, source stats and JaCoCo coverage detection.
- Excel handler that reads the real production template and resolves its columns dynamically.
- Azure OpenAI scoring client, which also has a stub mode. Prompts include relevant source code as context.
- Review API: create a review, poll its progress, download the result.
- First React frontend (upload form, progress tracker, findings panel and stats), plus Docker Compose.

### Phase 1: UI redesign and transparency (07-27 to 07-29)
- The "Industry" design system was adopted and every component was restyled.
- Per-category score chart, LLM token-usage stats and a prompt debug log.
- **Real compile/lint check:** clause 1.4 is scored by a Gradle Lint run in the `compiler` service rather than by the LLM. Scoring became binary (0 or 1, no half marks).
- Project name in the header, a per-clause report table and a performance breakdown popup.
- Multi-platform landing page with routing (PR #1).

### Phase 2: Local LLMs and multi-platform support (07-29 to 07-31)
- Ollama provider, with a model picker and a provider dispatcher (`llm_client.py`) (PR #2).
- Compile-check modes: Docker, local (Mac agent) or static, where the LLM scores clause 1.4.
- Prompts adapt to the platform. Categories are read from the template rather than hardcoded.
- **Azure DevOps source:** a repo can be cloned with a URL and PAT instead of uploading a ZIP (PR #3).
- **iOS support:** iOS analyzer, plus `mac_build_agent` for xcodebuild lint.
- **.NET support:** .NET analyzer, plus a Dockerized `dotnet-compiler` service.
- Warnings and secrets on the completed screen open in a popup.

### Phase 3: Org-wide platform (08-07 to 08-21)
- More precise prompts (for example, an auth-focused checklist for .NET clause 2.4) and Ollama context-window fixes.
- Full visual redesign from the design handoff.
- **Postgres persistence:** projects and reviews are saved, with migrations managed by Alembic (PR #4).
- Project dashboard and a read-only page for viewing past review reports.
- **Settings page:** default LLM provider, clause checklists and sample templates. Approvers can edit scores and status.
- Dashboard redesign: year, platform and project filters, a Final Score ring plus one ring per category, a results table and per-clause trend charts.
- Completed review sheets can be uploaded directly.

### Phase 4: Insights chatbot (08-17)
- LangChain review-insights chatbot (`/api/chat`) shown in a widget on the dashboard. It only answers questions about review history (PR #5). It was later updated to render markdown and to support resizing.

### Phase 5: Auth and RBAC (08-25 to 09-21)
- User accounts, password hashing, JWT session cookies and the roles admin, reviewer and viewer. Every API endpoint enforces RBAC.
- Login page, a Users admin page and role-based menu items and actions in the UI.
- Clause guidance can be overridden for a single review. The guidance used is saved with the review, and the most recent review's guidance becomes the default for the next one.
- A reviewer can be assigned to each review (PR #6).
- `docs/PRODUCTION_READINESS.md` lists what must change before a real deployment.

### Phase 6: Microsoft SSO (09-28 to 09-29)
- "Sign in with Microsoft" via OAuth. It links to an existing account or provisions a new one (PR #7).

### Phase 7: Claude CLI provider and polish (10-02 to present). Branch: `claude-cli-provider`
- `claude_cli_agent` host service and a third LLM provider, "Claude CLI (local)". Each run's cost is capped by a spend budget, and the review reports the real token usage.
- The report page shows review metadata (source, compile-check mode and provider). Admins can delete reviews.
- Dashboard ring layout: a 2x2 Final Score ring next to a 4x2 grid of category rings.
- **2026-10-06:**
  - Renamed the project to **CodeAssure**: nav brand, page headings ("CodeAssure for Android" and so on), page title, manifest, API title and README headings.
  - The favicon and app icons now use the nav logo mark (coral and navy split with a white check). This added `favicon.svg`.
  - Stopped browsers from autofilling the saved login (`admin@example.com` and its password) into the Azure DevOps URL and PAT fields on the review form.

---

## Running locally

```bash
docker compose up -d --build                           # full stack
docker compose up -d --build --no-deps frontend        # rebuild the frontend only
cd frontend && CI=true npx react-scripts test --watchAll=false   # frontend tests
cd backend && pytest                                   # backend tests
```
The host-native agents (`mac_build_agent/`, `claude_cli_agent/`) are started separately. Each has its own README.

## Known gaps and next steps
- Production hardening (HTTPS, secrets management, host-native agents) is tracked in `docs/PRODUCTION_READINESS.md`.
- The `claude-cli-provider` branch has not been merged into `master` yet.
- The historical specs and plans in `docs/superpowers/` still say "Code Review Automation". They were left unchanged on purpose as a record of past work.
