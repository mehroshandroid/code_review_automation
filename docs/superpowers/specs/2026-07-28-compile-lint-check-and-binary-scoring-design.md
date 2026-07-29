# Real Compile-Time Lint Check & Binary Scoring — Design Spec

**Status:** Approved
**Date:** 2026-07-28
**Source:** Team demo feedback (item 3) — clause 1.4 ("No compile-time warnings") should be scored from a real build/lint run instead of an LLM guess, and every sub-criterion's scoring rubric should be binary (0/1) rather than 0/0.5/1.

## Purpose

Today every sub-criterion, including 1.4, is scored by the LLM from a static code snippet — it has no way to actually know whether a project compiles cleanly. This spec adds a second, sandboxed Docker service that actually runs the uploaded project's own Gradle build (`./gradlew lint`) and uses its real result to score 1.4 deterministically, while the LLM continues to score every other sub-criterion. It also simplifies the scoring rubric to strictly 0/1 (no partial credit) across all categories.

## 1. New `compiler` service

A second, long-running Docker Compose service, separate from `backend`, because running an uploaded project's Gradle build means executing arbitrary build-script code — this must not happen inside the process that holds `AZURE_OPENAI_KEY` or serves the main API.

- **Image**: JDK 17 + Android SDK cmdline-tools with licenses pre-accepted at build time + a fallback Gradle install (used only if an uploaded project has no `gradlew` wrapper).
- **API**: one endpoint, `POST /lint`, accepting the project as a multipart zip upload.
- **Behavior per request**:
  1. Extract to a fresh, isolated temp directory (same disposable-temp-dir pattern the backend already uses per review).
  2. Write a `local.properties` pointing `sdk.dir` at the image's baked-in SDK location (uploads never include this file — it's conventionally gitignored).
  3. Run the project's own Gradle wrapper via `sh ./gradlew lint` (invoked through `sh`, not executed directly, so the wrapper's executable bit — which zip extraction doesn't reliably preserve — doesn't matter). Falls back to the image's preinstalled Gradle only if no wrapper is present.
  4. Regardless of the Gradle process's own exit code (Android Lint's Gradle task itself exits non-zero whenever there's an Error-severity finding, by design — that is not the same as the build failing to compile), search the extracted tree for a `lint-results*.xml` report, the same "search anywhere, don't assume module layout" approach already used for the JaCoCo report.
  5. If a report is found: parse every `<issue>` (severity, message, file, line), return `{status: "ok", warning_count, issues: [...]}` where `warning_count` counts only `Warning` and `Error` severity issues (Informational/Hint-level findings don't count as "warnings").
  6. If no report exists anywhere: the project never got far enough to run lint (a genuine compile error upstream) — return `{status: "build_failed", warning_count: null, issues: []}`.
- **Network**: the service needs outbound internet access (to resolve the wrapper's declared Gradle distribution and the project's Maven dependencies) — this is an accepted, unavoidable requirement of running arbitrary uploaded builds, not an oversight.
- **Cleanup**: the per-request temp directory is deleted after the response is sent, mirroring the backend's existing review-cleanup pattern.

## 2. Backend pipeline integration

- New module `backend/app/analyzer/compile_checker.py`: `async def check_compile_warnings(zip_path: Path) -> dict`, POSTs the original uploaded zip to `COMPILER_SERVICE_URL` (new env var, default `http://compiler:8000`) with a 5-minute `httpx` timeout. Returns one of:
  - `{"status": "ok", "warning_count": int, "issues": [...]}`
  - `{"status": "build_failed", "warning_count": None, "issues": []}`
  - `{"status": "unavailable", "warning_count": None, "issues": []}` — connection error or timeout talking to the compiler service.
- New phase `"compiling"` in `_run_review`, inserted between `"analyzing"` and `"scoring"` (progress checkpoints shift to make room: extracting→15, analyzing→35, compiling→55, scoring 55→85, generating→95→100).
- Result maps to sub-criterion `"1.4"` directly:
  - `status: "ok"`, `warning_count == 0` → score `1`, remark `"No Lint warnings or errors found."`
  - `status: "ok"`, `warning_count > 0` → score `0`, remark summarizing the count (e.g. `"3 Lint warnings/errors found."`)
  - `status: "build_failed"` → score `0`, remark `"Project failed to compile."`
  - `status: "unavailable"` → score `null`, remark `"Compile check unavailable (compiler service unreachable)."`
- **Sub-criterion `"1.4"` is removed from what's sent to the LLM** when scoring category `"1"` — there's no reason to ask the LLM to guess something now measured directly. The LLM scores `["1.1", "1.2", "1.3", "1.5", "1.6"]` for category 1 only (every other category is unaffected).
- After the LLM call returns for category 1, its 5-entry result is merged with the compile-check's 1.4 entry and **rebuilt in `CATEGORIES["1"]["sub_criteria"]`'s declared order** (`1.1, 1.2, 1.3, 1.4, 1.5, 1.6`) before calling `aggregate_category_scores` — `populate_scores` writes Excel rows positionally by dict key order, so an out-of-order merge would silently misalign every row from 1.4 onward.
- `state["lint_issues"]` (list) and `state["compile_status"]` (`"ok"|"build_failed"|"unavailable"`) are new state fields, set once the compiling phase finishes, and exposed on `GET /progress` the same way `secrets_found`/`warnings` already are.

## 3. Frontend changes

- `ProgressTracker`: 5th step, **"Compiling & linting"**, between "Analyzing code" and "Scoring with AI"; phase→step-index mapping extends to include `"compiling"`.
- `FindingsPanel`: 4th card, **"Lint issues"** — same expandable pattern as Warnings/Secrets (count + caption, expands to a list of `file:line (severity): message`). Caption reflects `compile_status`: a warning/error count when `"ok"`, `"Project failed to compile."` when `"build_failed"`, `"Compile check unavailable."` when `"unavailable"`. Grid layout adjusts from 3 to 4 cards (wraps 2×2 within the left column's narrower width in the existing 2-band layout).

## 4. Binary scoring (0/1 only, every category)

`_category_instructions` (in `openai_client.py`) drops the `0.5 (partial)` option from the rubric text sent to the LLM — every sub-criterion becomes strictly `0 (fails)`, `1 (meets it)`, or `null` (can't evaluate from the given code). This is a **prompt-text-only change**: `aggregate_category_scores` already averages whatever numeric scores it receives, so no aggregation-math changes are needed — the LLM will simply never be instructed to return `0.5` again.

## Testing

- **Compiler service**: new test suite (its own `tests/` — this is a new, separate Python service) covering: report-found → parsed issues with correct severity filtering (Warning/Error counted, Informational excluded); no-report-found → `build_failed`; wrapper-invocation via `sh` regardless of executable bit.
- **Backend**: `test_openai_client.py` extended to assert the rubric text no longer mentions "0.5"; a new test verifying category 1's `score_category` call is invoked with `sub_criteria` excluding `"1.4"`; `test_reviews_create.py`/`test_reviews_integration.py` extended for the new `"compiling"` phase, the four `compile_checker` result branches mapping to the right 1.4 score/remark, and the merged sub_results landing back in the correct declared order (regression-testing the exact positional-misalignment risk called out above). `test_reviews_progress.py` extended for `lint_issues`/`compile_status` round-tripping.
- **Frontend**: `ProgressTracker.test.jsx` extended for the 5th step; `FindingsPanel.test.jsx` extended for the new lint-issues card and its three caption states; `App.test.jsx`/fixtures updated for the new fields.

## Out of Scope

- No sandboxing beyond process/container isolation and the 5-minute timeout — no CPU/memory cgroup limits, no network egress allow-listing for the compiler service. Acceptable for this POC's scale; a production hardening pass would revisit this.
- No concurrency control between simultaneous compile jobs on the compiler service (each gets its own temp dir; Gradle daemon/cache contention under concurrent load is accepted, not solved, here).
- No change to how any other sub-criterion (besides 1.4) is scored, beyond dropping the 0.5 option from the rubric text.
- No retry logic for a failed/timed-out compiler-service call — a single attempt, then `"unavailable"`.
