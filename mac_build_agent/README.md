# mac_build_agent

A small FastAPI service that runs natively on your Mac (never in Docker) so
the review pipeline can do real compile-time checks that need tooling only
a real macOS machine has:

- **iOS** — builds with `xcodebuild` (no Xcode CLI tools exist in a Linux
  container).
- **Android (local mode)** — builds with Gradle/Lint using your own
  Android SDK, as a faster, non-emulated alternative to the Dockerized
  `compiler` service (which is forced to `linux/amd64` and runs under
  emulation on Apple Silicon).

It's started the same way Ollama already is for local LLM support: manually,
outside `docker-compose`, and the backend container reaches it over
`host.docker.internal`.

## Prerequisites

- **For iOS builds:** Xcode installed, with the command line tools set up
  (`xcode-select -p` should print a path under `/Applications/Xcode.app`).
- **For Android local builds:** an Android SDK installed. The agent looks
  for it in this order:
  1. `$ANDROID_HOME`
  2. `$ANDROID_SDK_ROOT`
  3. `~/Library/Android/sdk` (the default Android Studio install location)

  If you already have Android Studio set up, you almost certainly don't
  need to do anything — this will just work.
- Python 3.

## Setup (one-time)

```bash
cd mac_build_agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Running it

```bash
cd mac_build_agent
venv/bin/uvicorn main:app --host 0.0.0.0 --port 8100
```

Leave this running in its own terminal tab while you use the app. The
backend container is already configured (via `MAC_BUILD_AGENT_URL` in
`docker-compose.yml`) to reach it at `http://host.docker.internal:8100` —
no other setup needed on the backend side.

To confirm it's up:

```bash
curl http://localhost:8100/health
# {"status":"ok"}
```

## What happens if it's not running

Nothing breaks. Both checkers gracefully report `"status": "unavailable"`
if the agent can't be reached, and the review still completes — clause 1.4
just won't get a real compile-time score for that run. Selecting "Static
file analysis" or the Docker-based "Compile-time lint" for Android never
needs this agent at all.

## Endpoints

- `GET /health` — liveness check.
- `POST /lint` — iOS: accepts a zipped project, builds it with `xcodebuild`
  (no code signing needed — builds against a generic iOS Simulator
  destination), parses the build log for warnings/errors.
- `POST /android-lint` — Android: accepts a zipped project, runs
  `gradlew lint` scoped to the app module, parses the resulting
  `lint-results*.xml` report.

Both return the same shape: `{"status": "ok"|"build_failed"|"unavailable",
"warning_count": int|None, "issues": [{"severity", "message", "file",
"line"}, ...]}`.

## Live output

Build output streams to this terminal line-by-line as it happens (prefixed
`[xcodebuild stdout]` / `[xcodebuild stderr]`), not just once the whole
build finishes — a real build can take a few minutes, especially the first
run against a project with many dependencies (Swift Package Manager /
Gradle both need to resolve and download everything the first time).

## Disk usage / cleanup

- **Per-review temp files** (the extracted project, and for iOS its
  DerivedData) are deleted automatically after every request — nothing
  accumulates here.
- **Global caches are intentionally left alone** — SPM's package cache
  (`~/Library/Caches/org.swift.swiftpm`) and Gradle's dependency/wrapper
  cache (`~/.gradle`) are shared across every project on your machine, not
  just this tool, and clearing them just means slower resolution next
  time. They're both safe to clear manually if you ever need the disk
  space back:
  ```bash
  rm -rf ~/Library/Developer/Xcode/DerivedData/*   # Xcode's own cache, unrelated to this agent, safe to clear
  rm -rf ~/Library/Caches/org.swift.swiftpm/*       # SPM package cache
  # Gradle's cache is left alone by design -- clearing ~/.gradle is rarely worth it,
  # since it forces every future Android build (not just this tool's) to
  # re-download Gradle itself plus every dependency from scratch.
  ```
