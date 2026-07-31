# .NET Compile-Time Check (Container-Based) Design Spec

**Status:** Approved
**Date:** 2026-07-31
**Source:** "okay lets do compile of dotnet, i would prefere container based option for it" — following the .NET project-analysis round, clause 1.4 ("No compile-time warnings," confirmed against the real `SampleBackendReview.xlsx` template) is still always scored by the LLM for .NET, same as iOS/Android before their own compile-check rounds. Unlike iOS (Xcode, macOS-only) and Android-local (needs the host Mac's own SDK), .NET's own build tooling — the `dotnet` CLI — is fully cross-platform and runs natively on Linux, so this round uses a new Dockerized service instead of `mac_build_agent`.

## Purpose

Give .NET reviews a real compile-time-warnings check for clause 1.4, running `dotnet build` inside its own Docker Compose service (mirroring `compiler/`, the existing Android Gradle/Lint container) rather than requiring any host-machine involvement.

## Out of Scope

- A "local" (host-machine) .NET build option — .NET's build tooling has no macOS-only dependency the way Xcode does, so there's no equivalent need; can be revisited later if there's a reason to want it.
- Module/project scoping analogous to Android's "skip vendored library modules" logic — NuGet packages are compiled separately and never appear as local project files the way Android's vendored-library-modules-as-local-projects pattern does, so this doesn't apply to .NET.
- Structured MSBuild logger output (binary/JSON logs) — plain console text regex parsing is simpler and sufficient, matching every other checker built this session.

## 1. `dotnet_compiler/` — new Docker Compose service

Mirrors `compiler/`'s structure exactly:

- `Dockerfile`: based on a pinned `mcr.microsoft.com/dotnet/sdk:8.0` image (matching `compare_dotnet_versions`'s own "net8.0 is latest" baseline from the previous round).
- `app/dotnet_build_runner.py`:
  - `find_project(project_dir) -> Path | None`: prefers a `.sln` (shallowest path) over a standalone `.csproj`, mirroring `dotnet_analyzer.py`'s `find_project_config()` precedent from the previous round — build the whole discovered solution/project with no extra module-scoping, since .NET's dependency model doesn't have Android's "vendored module" problem.
  - `_stream_and_collect(stream, label) -> str` / `_run_subprocess(command, cwd, timeout_seconds) -> dict`: copied from `compiler/app/lint_runner.py`'s existing streaming implementation verbatim — prints each output line immediately (flushed) as `dotnet build` produces it, so `docker compose logs -f dotnet-compiler` shows live progress exactly like the Android service already does, not just a final dump once the whole build exits.
  - `run_build(project_dir) -> dict`: runs `dotnet build <path> --nologo -nodeReuse:false` in the discovered project's directory via `_run_subprocess`, with `DOTNET_BUILD_TIMEOUT_SECONDS` (generous enough for a cold-cache NuGet restore + build, same scale as Android's `GRADLE_TIMEOUT_SECONDS`). Returns `{"returncode": int|None, "stdout": str, "stderr": str}` — success/failure is decided by the caller from parsed diagnostics, not the exit code, same as every other runner this session.
  - `-nodeReuse:false` is required, not optional: MSBuild defaults to keeping background worker processes alive after a build finishes, to speed up the *next* build. Since this container handles many review requests over its lifetime (it isn't restarted per request the way a serverless invocation would be), those worker processes would otherwise accumulate in memory across reviews. Passing this flag makes MSBuild fully tear down its worker process every time, trading a bit of per-build speed for guaranteed clean memory between requests.
- `app/dotnet_build_parser.py`:
  - `parse_build_output(text) -> list`: regex for MSBuild's diagnostic line format, `<file>(<line>,<col>): warning|error <CODE>: <message> [<project>]`, producing `{"severity": "Warning"|"Error", "message": str, "file": str, "line": int}` entries (mirrors the shape every other parser this session produces).
  - `count_warnings(issues) -> int`: counts `Warning`+`Error` severities, same convention as the other parsers.
- `main.py`'s `/lint` endpoint (same endpoint name as `compiler`/`mac_build_agent`'s services, despite this step being a compile rather than a separate lint pass — keeps the naming convention the backend clients already expect): extracts the uploaded zip, calls `run_build`, parses the captured stdout+stderr for diagnostics. If the exit code is non-zero **and** zero diagnostics were parsed at all, returns `{"status": "build_failed", "warning_count": None, "issues": [], "log": <last 4000 chars>}` (e.g. a missing project file, or a restore failure with no compiler output yet) — otherwise returns `{"status": "ok", "warning_count": ..., "issues": [...]}`, since a `dotnet build` that fails specifically due to real compiler errors still produces parseable diagnostic lines, which become real `"Error"`-severity issues rather than being swallowed into a generic failure.
- A new persistent `nuget-cache` volume (mirroring `gradle-cache`'s existing rationale) mounted at `/root/.nuget/packages`, so the NuGet package cache survives container recreation instead of re-downloading every dependency from scratch each time.

**Cleanup summary** (three distinct concerns, each already resolved above): per-review disk usage (the extracted project and its `bin`/`obj` build output, both project-local, not a separate global location) is deleted by `main.py`'s existing `finally: shutil.rmtree(work_dir, ...)` pattern, same as `compiler`/`mac_build_agent`; the NuGet package cache is *intentionally* persistent and shared across reviews, same as `gradle-cache`, and is never cleared automatically; and per-review *memory* (MSBuild's background worker processes) is prevented from accumulating by `-nodeReuse:false` on every build, since this is a long-lived container handling many requests, not a fresh process per request.

## 2. Backend wiring

- New `backend/app/analyzer/dotnet_compile_checker.py`: `async def check_dotnet_build_warnings(zip_path) -> dict`, posting to `{DOTNET_COMPILER_SERVICE_URL}/lint` (default `http://dotnet-compiler:8000`), with the same `except (httpx.HTTPError, OSError): return {"status": "unavailable", "warning_count": None, "issues": []}` fallback as `compile_checker.py`/`ios_build_checker.py`/`android_local_checker.py`.
- `docker-compose.yml`: new `dotnet-compiler` service (own `Dockerfile`, `nuget-cache` volume, on the existing `review-network`), plus `DOTNET_COMPILER_SERVICE_URL=http://dotnet-compiler:8000` and a `depends_on: dotnet-compiler` entry added to the `backend` service.
- `reviews.py`: the compiling-phase gate widens from `platform in ("Android", "iOS")` to `platform in ("Android", "iOS", ".NET")`. Checker dispatch becomes: `.NET` → `check_dotnet_build_warnings`; `iOS` → `check_ios_build_warnings` (unchanged); `Android` → `check_android_local_warnings` if `compile_check_mode == "local"` else `check_compile_warnings` (unchanged). The two clause-1.4-exclusion/merge conditions in the scoring loop (currently `platform in ("Android", "iOS")`) widen the same way, so .NET's clause 1.4 is excluded from the LLM and merged from the real build result exactly like Android/iOS already do. No changes needed to `_compile_result_to_sub_score`/`_merge_compile_result_into_category_1` — both already consume any checker's result shape unchanged.

## 3. Frontend

`UploadForm`'s "Clause 1.4 evaluation" toggle currently shows the "(Docker)"/"(local)" label suffix and the third "local" button only when `platformLabel === "Android"`. This splits into two independent checks: `showDockerSuffix = platformLabel === "Android" || platformLabel === ".NET"` (so .NET's Docker-backed button now correctly reads "Compile-time lint (Docker)" instead of the current plain "Compile-time lint"), and `showLocalButton = platformLabel === "Android"` (unchanged — no .NET-local option exists this round). iOS is unaffected — it keeps its plain "Compile-time lint" label, since it has no Docker alternative to disambiguate from.

## Testing

- **`dotnet_compiler` service**: new `tests/test_dotnet_build_parser.py` (diagnostic-line extraction, warning/error counting, no-diagnostics case) and `tests/test_dotnet_build_runner.py` (mirrors `compiler/tests/test_lint_runner.py`'s split: `find_project` tested directly with `tmp_path` fixtures — no mocking; `_run_subprocess` tested with real simple shell commands, not `dotnet` itself; `run_build`'s actual `dotnet build` invocation is *not* directly unit-tested, matching the established "the real build-invoking orchestrator is only exercised indirectly, via main.py's monkeypatched tests" precedent already used for `compiler`/`mac_build_agent`). `tests/test_main.py` for the `/lint` endpoint (ok-with-issues, build_failed-with-log, health check), monkeypatching `run_build` the same way `compiler`'s and `mac_build_agent`'s own `test_main.py` files already do.
- **Backend**: new `test_dotnet_compile_checker.py` mirroring `test_ios_build_checker.py`/`test_android_local_checker.py` exactly (success, connection-error → unavailable, non-2xx → unavailable, env-var/URL-path check). `test_reviews_create.py`/`test_reviews_integration.py`: a new `.NET` + `compile_check_mode="compiler"` case proving clause 1.4 is excluded from the LLM and merged from the real build result, plus a static-mode case proving it's skipped correctly — mirroring the existing Android/iOS compile-check test pairs exactly.
- **Frontend**: extend `UploadForm.test.jsx` for `.NET`'s new "(Docker)" suffix (no third button) and confirm iOS's plain label is unaffected.
- Full existing Android, iOS, and .NET-analysis-only test suites must pass unchanged.

## Ambiguity resolved during self-review

- The `/lint` endpoint name (not `/build` or `/compile`) was chosen specifically to keep naming consistent with `compiler/` and `mac_build_agent`'s existing endpoints, even though this step is a compile rather than a separate lint pass — avoids the backend client code having a one-off different path convention for no functional reason.
- "Build failed" vs. "ok with issues" is decided the same way for .NET as it already is for iOS: a non-zero exit code alone doesn't mean `build_failed` — only a non-zero exit code **combined with** zero parsed diagnostics does, since a real compile error is itself a parseable, actionable diagnostic line, not an opaque failure.
