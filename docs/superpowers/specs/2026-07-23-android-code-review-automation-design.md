# Android Code Review Automation — Design Spec

**Status:** Approved
**Date:** 2026-07-23
**Source:** Derived from `HANDOVER_ANDROID_CODE_REVIEW.md` and `QUICK_REFERENCE.md`, with open questions resolved below.

## Purpose

A web app that automates Android code review scoring: upload an Android project ZIP + a review-template Excel file, analyze the code with Azure OpenAI (gpt-4o-mini), score it against fixed review categories, and return the Excel populated with scores/remarks — formatting untouched.

## Repo Layout

Flat layout at repo root (no nested `android-code-review/` wrapper):

```
backend/
  main.py
  requirements.txt
  app/
    api/reviews.py
    analyzer/
      android_analyzer.py     # gradle + source parsing, dependency listing
      secrets_scanner.py      # regex-based hardcoded secret detection
      version_checker.py      # SDK/Gradle/Kotlin version comparison
      excel_handler.py        # openpyxl load/populate/save
      openai_client.py        # Azure OpenAI scoring client (+ stub mode)
    utils/logger.py
  Dockerfile
  .env                        # gitignored
frontend/
  package.json
  src/
    App.jsx
    components/UploadForm.jsx, ProgressTracker.jsx, StatsDisplay.jsx
    services/api.js
  Dockerfile
docker-compose.yml
.gitignore
```

## Architecture

```
React Frontend (upload, progress polling, download, stats)
        │ HTTP
FastAPI Backend
  1. Upload Handler        — validate ZIP + Excel schema, store in temp dir
  2. Android Analyzer      — extract gradle/source files, detect test coverage,
                              scan secrets, check SDK/Gradle versions
  3. Azure OpenAI Orchestrator — score each of the 5 categories via chat completions
  4. Excel Manipulator     — populate template values only, preserve all styling
  5. Progress Tracker      — phase timings, exposed via polling endpoint
```

## API

```
POST   /api/reviews                 FormData: androidZip, excelTemplate → { review_id, status }
GET    /api/reviews/{id}/progress   { status, phase, progress, message, stats, download_url, error }
GET    /api/reviews/{id}/download   Binary xlsx; deletes output file after download
GET    /api/health                  { status, azure_openai_connected }
```

No WebSocket — polling only, 2s client-side interval, per the handover doc's own POC recommendation.

**Progress phases:** `pending → extracting → analyzing → scoring → generating → completed | error`

## Analysis Pipeline

1. **Ingest** — extract ZIP to a `tempfile.TemporaryDirectory()`, validate it looks like an Android project (build.gradle[.kts], AndroidManifest.xml, src/main). Missing files are flagged as warnings, not fatal.
2. **Extract & parse**
   - Gradle: compileSdkVersion, targetSdkVersion, Gradle/Kotlin plugin versions, dependency list, jacoco/kover presence (regex-based; handles both Groovy and Kotlin DSL with the same patterns).
   - Source: count .java/.kt files, package structure, test file detection (JUnit patterns).
   - Test coverage: look for JaCoCo/Kover config and report files; if absent, coverage is `None` (no estimate-from-file-count fallback — avoids reporting a misleading number).
   - Secrets: regex patterns for API keys, AWS secrets, generic tokens/passwords, Firebase keys; reports file + line, never fails the run.
   - Versions: compare extracted SDK/Gradle/Kotlin versions against hardcoded "latest known" constants; warn if outdated.
3. **Score via Azure OpenAI** — one call per category (5 categories: Code Structure 1.1-1.6, Reliability/Security/Observability 2.1-2.4, Delivery Discipline & Architecture 3.1-3.4, AI Usage & Code Ownership 4.1-4.3, Safe & Integrated AI Code 6.1-6.3), each returning `{score: 0|0.5|1|null, remark: str}` per sub-criterion. Source is chunked to stay under ~8k tokens per call.
4. **Populate Excel** — see below.

## Azure OpenAI Integration

- `httpx` async client against `{OPENAI_API_BASE}/openai/deployments/{OPENAI_DEPLOYMENT_NAME}/chat/completions`, `api-key` header, temperature 0.3, max_tokens 1500, 30s timeout, exponential backoff on 429.
- **Stub mode:** if `AZURE_OPENAI_KEY` is unset/empty in `.env`, the client returns a clearly-labeled dummy response (`remark` prefixed `[STUB]`, deterministic placeholder scores) instead of failing. This lets the rest of the pipeline (analyzer → Excel → download → cleanup) be exercised end-to-end today. No code branching needed later — supplying a real key in `.env` switches to live calls automatically.
- Real credentials are provided by the user directly into `backend/.env` (gitignored); not handled by this implementation.

## Excel Handling

- `openpyxl.load_workbook(path, read_only=False)`.
- On load, parse the header row once to resolve column indices for Avg Points / Final Points / % Points / Remarks dynamically — never hardcode column letters.
- Write only `.value` on data cells; never touch font/fill/border/merge objects; leave formula cells alone so built-in totals recompute naturally.
- Unscored sub-criteria are left blank (`None`), not forced to 0.

## Error Handling

- **Non-fatal** (continue, mark that piece unavailable): missing build.gradle, no coverage report, version-parse failure, Azure OpenAI timeout/error for a given category.
- **Fatal** (stop immediately, return error status): invalid ZIP structure, Excel template schema mismatch, no .java/.kt source files found.
- All responses are HTTP 200; errors are carried in the JSON body (`status: "error"`, `message`, `phase`) so the frontend can render them without special-casing transport failures. No secrets/keys ever appear in logs or error messages.

## Cleanup

`tempfile.TemporaryDirectory()` per review for uploads/extraction (auto-cleaned on context exit). Output xlsx persists until downloaded, then deleted.

## Testing

- Unit tests for `android_analyzer`, `secrets_scanner`, `version_checker` against small inline fixtures (no external sample project required).
- Integration tests for the Excel population + OpenAI-stub pipeline end-to-end.
- Full upload→download flow against a real Android project ZIP is deferred until the user supplies one.

## Deployment

Docker Compose with `backend` (Python 3.11-slim, port 8000) and `frontend` (port 3000) services, per the handover doc's existing Dockerfile/compose definitions. `.env` values passed through as environment variables; `/tmp/reviews` mounted as a volume for temp data.

## Open Items (deferred, not blocking)

- Real Android project ZIP for full end-to-end testing — user to provide later.
- Real Azure OpenAI credentials — user to add to `backend/.env` later; stub mode covers development until then.
