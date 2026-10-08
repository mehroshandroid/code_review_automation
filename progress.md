# CodeAssure — Progress Log

CodeAssure (formerly "Code Review Automation") is an AI-assisted tool for reviewing source code. You give it an Android, iOS or .NET project as an uploaded ZIP or an Azure DevOps repo. It runs structural, secrets and compile/lint checks on the project, then has an LLM score each clause of the org's Excel review template. Completed reviews are stored in Postgres and appear on a project dashboard.

This file records what has been built and in what order, so a future developer can see what exists and why. For the design behind each feature, read the specs in `docs/superpowers/specs/`. Each spec has a matching step-by-step plan in `docs/superpowers/plans/`.

_Last updated: 2026-10-08_

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
  - **2026-10-07:** Added "Claude CLI (local)" to the Settings page's organization-wide default LLM provider options, which had only listed Azure and Ollama.

### Phase 8: Roles and access, part 1 of the quarterly review workflow (2026-10-07). Branch: `claude-cli-provider`

Spec: `docs/superpowers/specs/2026-10-07-roles-and-access-design.md`. Plan: `docs/superpowers/plans/2026-10-07-roles-and-access.md`.

- **Roles:** there are now five roles: `admin`, `management`, `coordinator`, `reviewer` and `project_manager`. The old `user` role is retired, and the migration moves `user` accounts to `project_manager` with no projects assigned. Microsoft sign-in now creates new accounts as `project_manager` and fills in the person's name.
- **Permissions:** `backend/app/auth/permissions.py` lists which roles hold each capability, and is the only place that does. Endpoints check a capability with `require_permission(...)`. Every dashboard and review query is limited by `visible_project_ids(...)`. `/api/auth/me` returns the user's `permissions` and `home_path`, and the frontend uses those to decide what to show.
- **Projects page (`/projects`):** coordinators, Management and admins can create and rename projects and assign Project Managers. Only admins and Management can delete a project, and only when it has no reviews (otherwise the API returns 409).
- **Project Managers:** see the dashboard, report pages and chatbot for their assigned projects only. Opening a review outside those projects returns 404.
- **Reviewers:** have a "My reviews" page (`/my-reviews`) and can finalize only the reviews assigned to them. They no longer see the dashboard or Settings.
- **Coordinators:** their home page is Projects. They can assign reviewers, and in Part 2 they will run quarterly cycles.
- **Navbar:** a new shared navbar (`AppNav`) shows links for the user's role and an avatar menu with initials, name and role. It replaces `TopNav` and `NavActions`.
- **Rollout note:** existing reviewer accounts lose access to the dashboard and Settings. The old code can't set the `management` role, so re-role people **right after the migration runs, before announcing the release**. Either use the Users page as an admin, or run the following against the database, listing the emails of reviewers who still need the dashboard:
  ```sql
  UPDATE users SET role = 'management' WHERE email IN ('person1@teo-intl.com', 'person2@teo-intl.com');
  ```
- **Next:** Part 2 is quarterly cycles (Coordinator starts a cycle, PM enters a DevOps URL for each platform, the review runs automatically). Part 3 is email notifications.

### Phase 9: Quarterly dashboard and starting a review cycle, Part 2 slice 1 (2026-10-07). Branch: `quarterly-cycles`, stacked on `roles-and-access`

Spec: `docs/superpowers/specs/2026-10-07-quarterly-dashboard-design.md`. Plan: `docs/superpowers/plans/2026-10-07-quarterly-dashboard.md`.

- **Project platforms:** each project now has a list of its platforms (Android, iOS, .NET), set with checkboxes on the Projects page. "Rename" became "Edit". The migration `c3d4e5f6a7b8` fills in existing projects from the platforms they have non-errored reviews for.
- **Quarterly dashboard (`/` for coordinators, `/quarterly` for admins and Management):** one row per project with four cards for Q1–Q4. The status rules live in `backend/app/quarterly.py`, and quarters run on UTC calendar dates.

  | Status | Colour | Meaning |
  |---|---|---|
  | Done | green | Every platform has at least one non-errored review that quarter |
  | In progress | yellow | A cycle was started or some platforms are covered, and the quarter isn't over |
  | Overdue | coral | The quarter has ended without being done |
  | Not started | white | A future quarter, or the current one with nothing yet |
  | N/A | grey | The quarter ended before the project was being tracked |

  A project counts as tracked from its creation date or its first review, whichever is earlier. Historical sheets were uploaded after the project records existed.
- **Starting a review:** a coordinator, Management or admin can start the current quarter or an overdue one by assigning a reviewer to each platform. This creates `review_cycles` and `review_cycle_assignments` records.
- **Navigation:** the coordinator's home and "Dashboard" link point to the quarterly dashboard, with "Projects" as a separate link. Admins and Management get a "Quarterly" link.
- **Next slices of Part 2:** the PM enters a DevOps URL for each platform, an org-wide PAT is stored in Settings, the review runs automatically, review progress is saved in the database, and the coordinator gets a stage tracker with reminders. Part 3 is emails.

### Phase 10: Automated cycle reviews, Part 2 slice 2 (2026-10-08). Branch: `automated-reviews`, stacked on `quarterly-cycles`

Spec: `docs/superpowers/specs/2026-10-07-automated-cycle-reviews-design.md`. Plan: `docs/superpowers/plans/2026-10-07-automated-cycle-reviews.md`.

- **PM dashboard:** a "Pending quarterly reviews" panel lists each started cycle on the PM's projects. For each platform the PM enters the Azure DevOps URL (and an optional branch), which queues that review. The panel shows the status (Waiting for URL, Queued #n, Running with phase and %, Completed with a View link, Failed with the error) and refreshes every 10 seconds while anything is running.
- **Worker (`backend/app/automation/worker.py`):** a single background worker, started when `REVIEW_WORKER_ENABLED=true`, runs queued reviews one at a time, oldest first. It uses the org PAT, the org LLM default, the sample template, and the compile check set for that platform. The finished review is assigned to the cycle's reviewer.
- **Queue state:** the queue and progress are stored on `review_cycle_assignments`. On startup the worker re-queues runs that were interrupted and runs that failed for system reasons.
- **Failure kinds:**
  - **url:** the repo isn't found, or isn't a project for that platform. The PM fixes the URL and saves again.
  - **system:** the PAT is missing or rejected, a service is unreachable, or something else went wrong. Admins are notified, and these runs are re-queued when an admin saves the PAT or the stack restarts.
- **Coordinator "Manage" dialog** on a started quarter card: change the reviewer for each platform at any point until the review is approved (the finished review moves to the new reviewer), retry failed runs, and re-run a completed but not-yet-approved run with a new URL.
- **Settings, "Automatic reviews":** the org DevOps PAT, which only admins can set. It's stored encrypted and only "••••last4" is ever shown. Also a compile check per platform; the defaults are Android and .NET using Docker, iOS using static analysis.
- **`notification_outbox`:** every workflow email is recorded here for Part 3's mailer to send: `cycle_initiated`, `reviewer_assigned`, `reviewer_unassigned`, `review_ready`, `review_failed` and `review_finalized`.
- **Deploy notes:**
  1. Set `SETTINGS_ENCRYPTION_KEY` (a Fernet key) before saving the PAT. Changing it later means the PAT has to be entered again.
  2. The PAT needs Code (Read) access on every project's repos.
  3. Run the worker on exactly one backend instance.
- **Next:**
  - **Slice 3:** a coordinator stage tracker with green and orange dots, timestamps and reminder buttons.
  - **Part 3:** a mailer that sends what's waiting in the outbox.

### Phase 11: Admin queue monitor, two review statuses, table padding (2026-10-08). Branch: `queue-monitor`, stacked on `automated-reviews`

Spec: `docs/superpowers/specs/2026-10-08-queue-monitor-design.md`. Plan: `docs/superpowers/plans/2026-10-08-queue-monitor.md`.

- **Queue tab** (admin only, after Users; capability `queue.manage`): a live view of the automated review queue, refreshing every 5 seconds.

  | Panel | Shows | Actions |
  |---|---|---|
  | Running now | Phase, progress bar, time elapsed, attempt | Stop |
  | Queued | Position, time waited | Move to front, Remove (PMs are notified), Run settings |
  | Failed | The error, tagged URL, System or Stopped | Retry, Run settings |
  | Recently completed | How long it took | View |

- **Pause and resume:** pause stops the running review immediately, puts it back at the front of the queue and saves nothing for the cancelled run. The pause state is kept in `review_queue_state`, not in org settings.
- **Run settings:** each review can override the LLM provider (and model) and the compile check for that review only, including its retries. Settings stays unchanged and supplies the defaults.
- **Review statuses:** reviews now have two statuses, Pending approval and Approved. The four reviews marked "Completed" were migrated to Approved.
- **Tables:** tables on the Users, Projects, My reviews and cycle screens now have padding around their cells (`.table--padded`).

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
