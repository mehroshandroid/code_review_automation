# Production Readiness Checklist

This app currently runs entirely as a local dev stack (`docker-compose.yml`,
plain HTTP, hardcoded secrets, host-native build agents). This document is
the checklist of what has to change before it's deployed for real users.
Nothing here is done yet — treat every section as a TODO.

## 1. Secrets and configuration

- [ ] **Remove hardcoded secrets from `docker-compose.yml`.** `ADMIN_PASSWORD`,
      `AUTH_SECRET_KEY`, and the Postgres `POSTGRES_PASSWORD=postgres` are
      committed to git in plaintext today. Move them to `${VAR}` references
      (the way `OPENAI_API_BASE`/`AZURE_OPENAI_KEY` already do) backed by a
      `.env` file that is **not** committed (`.env`/`backend/.env` are
      already gitignored — use that) or a real secrets manager (AWS
      Secrets Manager, Azure Key Vault, Doppler, etc.) for a managed
      deployment.
- [ ] **Generate a strong `AUTH_SECRET_KEY`.** The JWT signing key
      (`backend/app/auth/token.py`) currently defaults to
      `"dev-insecure-secret-key"` if the env var is unset, and the
      docker-compose value is a placeholder. Generate a long random secret
      (e.g. `openssl rand -hex 32`) and never let the app fall back to the
      hardcoded default in production — consider making `main.py` refuse to
      start if `AUTH_SECRET_KEY` is unset outside of a `DEBUG`/dev flag.
- [ ] **Set real `ADMIN_EMAIL`/`ADMIN_PASSWORD`** for the first-boot seed
      (`main.py::_seed_admin_if_needed`), then **log in and rotate the
      password via the Users page** immediately — the seeded credential
      shouldn't be the long-term admin password, since it likely sat in
      plaintext config.
- [ ] **Set `COOKIE_SECURE=true`** once served over HTTPS (see §2) — until
      then the session cookie is sent over plaintext HTTP.
- [ ] **Set real Azure OpenAI credentials** (`AZURE_OPENAI_KEY`,
      `OPENAI_API_BASE`, `OPENAI_API_VERSION`, `OPENAI_DEPLOYMENT_NAME`) via
      the same secrets mechanism, not inline in compose.
- [ ] **Point `DATABASE_URL` at a managed Postgres instance**, not the
      `postgres` service in `docker-compose.yml` (see §3).

## 2. Network / TLS

- [ ] **Put a TLS-terminating reverse proxy or load balancer in front of
      both services** (nginx, Caddy, or a cloud LB) — the app itself serves
      plain HTTP on ports 3000/8000 with no TLS support built in.
- [ ] **Update CORS to the real frontend origin.** `backend/main.py` hardcodes
      `allow_origins=["http://localhost:3000"]` in the `CORSMiddleware`
      config — this must become the production frontend's actual origin
      (ideally env-driven, e.g. `ALLOWED_ORIGIN` read from an env var)
      before deploy, or every browser request will be blocked by CORS once
      the frontend is no longer on `localhost:3000`.
- [ ] **Rebuild the frontend with the real backend URL.** `REACT_APP_API_URL`
      is baked into the frontend image at *build* time via a Docker build
      arg (`docker-compose.yml`'s `frontend.build.args`), currently
      `http://localhost:8000/api`. The production frontend image must be
      built with `REACT_APP_API_URL` pointing at the real backend's public
      URL — this can't be changed at container-start time, only at build
      time.
- [ ] Since the cookie-based session relies on the frontend and backend being
      treated as the same site by the browser, confirm the chosen frontend
      and backend domains/subdomains keep `SameSite=Lax` cookies working
      (same registrable domain), or switch to `SameSite=None` + `Secure` if
      they end up on genuinely different domains.

## 3. Database

- [ ] **Use a managed Postgres instance** (RDS, Azure Database for
      PostgreSQL, Cloud SQL, etc.) instead of the `postgres` container —
      the compose service has no backup strategy and its data volume lives
      on a single host.
- [ ] **Set up automated backups** (point-in-time recovery if available) —
      nothing in this repo backs up review history, project data, or user
      accounts today.
- [ ] **Run `alembic upgrade head` as a separate, explicit deploy step**
      rather than relying on the backend container's entrypoint
      (`sh -c 'alembic upgrade head && uvicorn ...'`) if you ever run
      multiple backend replicas — concurrent replicas racing to run
      migrations on startup is a real risk in a multi-instance deployment.
- [ ] Confirm the production Postgres user has least-privilege access
      (not the `postgres` superuser the local compose setup uses).

## 4. File storage

- [ ] **Move `REVIEW_ARTIFACTS_DIR` and `SAMPLE_TEMPLATES_DIR` off local
      Docker volumes onto durable, shared storage** (S3, Azure Blob
      Storage, etc.) if you run more than one backend instance or use
      ephemeral containers — the current named volumes
      (`review-artifacts`, `sample-templates`) are tied to a single Docker
      host and are lost if that host/volume disappears.
- [ ] Decide a retention policy for persisted review workbooks
      (`.xlsx` files under `REVIEW_ARTIFACTS_DIR`) — nothing currently
      expires or archives old ones.

## 5. Auth hardening (beyond what this branch implements)

The `auth-rbac` branch adds email/password login + role enforcement, but
deliberately left some things out of scope (see
`docs/superpowers/specs/2026-08-25-auth-rbac-design.md`, "Out of scope").
Before a real production launch, decide on:

- [ ] **Rate limiting / brute-force protection on `POST /api/auth/login`** —
      there is currently no limit on login attempts. Add this at the reverse
      proxy (e.g. nginx `limit_req`) or in-app (e.g. `slowapi`).
- [ ] **Account lockout** after repeated failed logins, if required by your
      security policy.
- [ ] **Password reset / "forgot password" flow** — today, only another
      admin can change a locked-out user's password via the Users page.
- [ ] **Session revocation.** JWTs are valid for 7 days with no server-side
      revocation list — a stolen token remains valid until it naturally
      expires, and there's no "log out everywhere" mechanism. If that's not
      acceptable, moving to a server-side session table (considered and
      rejected in the design spec in favor of simplicity) or adding a
      revocation/blocklist becomes necessary.
- [ ] **Multi-factor authentication**, if required by your security policy —
      not implemented at all currently.
- [ ] **Audit logging** of logins, role changes, and account
      deactivations — none of this is logged today beyond default request
      logs.
- [ ] Confirm the **password minimum length (8 characters, no complexity
      rules)** enforced in `backend/app/api/users.py` meets your actual
      security requirements.

## 6. Compute dependencies that are dev-only today

- [ ] **Android/iOS build agents.** `compiler` (Android) is a Linux
      container pinned to `linux/amd64`; `mac_build_agent` (iOS lint +
      Android local mode) is documented in `docker-compose.yml` as running
      **natively on a host Mac, started manually** — this is not a
      production-ready architecture. Decide on a real strategy: dedicated
      macOS build runners (cloud Mac instances, MacStadium, GitHub-hosted
      macOS runners, etc.) reachable by the backend, not a manually-started
      process on someone's laptop.
- [ ] **Ollama.** `OLLAMA_BASE_URL=http://host.docker.internal:11434`
      assumes Ollama runs on the same machine as Docker Desktop. In
      production, either stand up a real reachable Ollama server or
      default the org to Azure OpenAI only and treat local-model support as
      opt-in/unavailable.
- [ ] `.NET` compiler service (`dotnet-compiler`) is a normal container and
      should be fine to run as-is in most container orchestrators, but
      confirm its resource limits (build/compile workloads can spike
      memory/CPU).

## 7. Deployment / orchestration

- [ ] `docker-compose.yml` is a **dev orchestration file** — for production,
      use a real orchestrator (Kubernetes, ECS, Azure Container Apps, etc.)
      or at minimum a hardened compose file with restart policies, resource
      limits, and health checks wired to your infra's monitoring.
- [ ] **Build and push images to a registry**, deploy by tag/digest rather
      than `docker compose up --build` from source on the target host.
- [ ] Add **liveness/readiness checks** beyond the existing
      `GET /api/health` — e.g. verifying DB connectivity, not just process
      health.

## 8. Observability

- [ ] **Structured logging** — `backend/app/utils/logger.py` exists but
      confirm log output is shipped somewhere durable (not just container
      stdout lost on restart) in production.
- [ ] **Error tracking** (Sentry or similar) — none configured today;
      exceptions currently only go to logs.
- [ ] **Metrics/alerting** on the backend, database, and build-agent
      services — nothing currently alerts on failures beyond Docker's own
      health checks.

## 9. CI / testing before every deploy

- [ ] **Set up a CI pipeline** (GitHub Actions or similar) — none exists in
      this repo yet (`.github/workflows/` is empty). At minimum, run the
      backend (`pytest`) and frontend (`react-scripts test`) suites on
      every push/PR before allowing a merge to `master`.
- [ ] Add a CI step (or manual step) that runs `alembic upgrade head`
      against a throwaway database to catch migration errors before they
      hit production.

## Suggested order of operations

1. Secrets + `.env` cleanup (§1) — do this first, it's a prerequisite for
   everything else being safe to deploy at all.
2. Managed Postgres + backups (§3), durable file storage (§4).
3. TLS + real CORS origin + frontend rebuild (§2).
4. Auth hardening decisions (§5) — at least rate limiting, before opening
   this up beyond a trusted internal group.
5. Real build-agent / Ollama strategy (§6) if those platforms/features are
   needed in production.
6. Orchestration hardening + CI (§7, §9) — can happen in parallel with the
   above.
7. Observability (§8) — ideally before launch, but can follow shortly after
   if timeline is tight.
