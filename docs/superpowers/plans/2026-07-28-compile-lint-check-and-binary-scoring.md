# Real Compile-Time Lint Check & Binary Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score clause 1.4 ("No compile-time warnings") from a real, sandboxed Gradle Lint run instead of an LLM guess, via a new separate `compiler` service, and drop the 0.5 partial-credit option from the scoring rubric everywhere.

**Architecture:** A new standalone FastAPI service (`compiler/`) accepts a project zip, runs `sh ./gradlew lint` inside an isolated temp dir, and returns a structured result. The main backend gets a thin async HTTP client (`compile_checker.py`) for it, a new `"compiling"` phase in `_run_review` between "analyzing" and "scoring", and merges the real 1.4 result into category 1's LLM-scored results (excluding 1.4 from what's sent to the LLM, then re-inserting it in the template's declared row order). The frontend gets a 5th progress step and a 4th findings card.

**Tech Stack:** New service: Python 3.11 + FastAPI + JDK 17 + Android SDK cmdline-tools + Gradle (same stack family as the existing backend, packaged separately). No new frontend dependencies.

## Global Constraints

- The compiler service is a **separate** Docker Compose service from `backend` — it must never share a process with anything holding `AZURE_OPENAI_KEY`, since running an uploaded project's Gradle build means executing arbitrary build-script code.
- Only Warning and Error severity Lint findings count toward `warning_count`; Informational/Hint-level findings don't.
- `status: "ok"` is determined by **whether a lint report file exists**, not by Gradle's own exit code (Android Lint's Gradle task legitimately exits non-zero on Error-severity findings — that's not the same as the project failing to compile).
- `status: "build_failed"` (no report at all) → 1.4 scores `0`. `status: "unavailable"` (compiler service unreachable/timed out) → 1.4 scores `null`. These must never be conflated.
- Sub-criterion `"1.4"` is excluded from what's sent to the LLM for category 1 and re-inserted afterward in `CATEGORIES["1"]["sub_criteria"]`'s exact declared order (`1.1, 1.2, 1.3, 1.4, 1.5, 1.6`) — `populate_scores` writes Excel rows positionally by dict key order, so an out-of-order merge silently misaligns every subsequent row.
- The 0.5-removal is a prompt-text-only change — `aggregate_category_scores`'s averaging logic is untouched.
- Every existing backend test that exercises `_run_review` end-to-end must explicitly mock `check_compile_warnings` (no test may depend on a real network call to a `compiler` host that doesn't exist outside Docker Compose).

---

### Task 1: New `compiler` service

**Files:**
- Create: `compiler/requirements.txt`, `compiler/requirements-dev.txt`, `compiler/pytest.ini`, `compiler/Dockerfile`
- Create: `compiler/app/__init__.py`, `compiler/app/lint_parser.py`, `compiler/app/lint_runner.py`
- Create: `compiler/main.py`
- Test: `compiler/tests/__init__.py`, `compiler/tests/test_lint_parser.py`, `compiler/tests/test_main.py`

**Interfaces:**
- Produces: `POST /lint` (multipart `project` file field) `-> 200 {status: "ok"|"build_failed", warning_count: int|null, issues: {severity, message, file, line}[]}`. `GET /health -> {status: "ok"}`.

- [ ] **Step 1: Scaffolding**

Create `compiler/requirements.txt`:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
```

Create `compiler/requirements-dev.txt`:

```
-r requirements.txt
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
```

Create `compiler/pytest.ini`:

```ini
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
```

Create empty `compiler/app/__init__.py` and `compiler/tests/__init__.py` (both empty files, matching the backend's package layout).

- [ ] **Step 2: Write the failing tests for `lint_parser.py`**

Create `compiler/tests/test_lint_parser.py`:

```python
from app.lint_parser import count_warnings, find_lint_report, parse_lint_report

LINT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<issues format="6" by="lint 8.1.0">
    <issue
        id="UnusedResources"
        severity="Warning"
        message="The resource `R.string.foo` appears to be unused"
        category="Performance">
        <location file="/project/app/src/main/res/values/strings.xml" line="3" column="13"/>
    </issue>
    <issue
        id="HardcodedText"
        severity="Informational"
        message="Hardcoded string, consider using @string resource">
        <location file="/project/app/src/main/res/layout/activity_main.xml" line="10"/>
    </issue>
    <issue
        id="MissingPermission"
        severity="Error"
        message="Missing permission check">
        <location file="/project/app/src/main/java/Main.java" line="42"/>
    </issue>
</issues>
"""


def test_parse_lint_report_extracts_every_issue(tmp_path):
    report_path = tmp_path / "lint-results-debug.xml"
    report_path.write_text(LINT_XML)

    issues = parse_lint_report(report_path)

    assert issues == [
        {"severity": "Warning", "message": "The resource `R.string.foo` appears to be unused",
         "file": "/project/app/src/main/res/values/strings.xml", "line": 3},
        {"severity": "Informational", "message": "Hardcoded string, consider using @string resource",
         "file": "/project/app/src/main/res/layout/activity_main.xml", "line": 10},
        {"severity": "Error", "message": "Missing permission check",
         "file": "/project/app/src/main/java/Main.java", "line": 42},
    ]


def test_count_warnings_only_counts_warning_and_error_severity():
    issues = [
        {"severity": "Warning", "message": "a", "file": "f", "line": 1},
        {"severity": "Informational", "message": "b", "file": "f", "line": 2},
        {"severity": "Error", "message": "c", "file": "f", "line": 3},
    ]
    assert count_warnings(issues) == 2


def test_find_lint_report_searches_anywhere_in_the_tree(tmp_path):
    nested = tmp_path / "app" / "build" / "reports"
    nested.mkdir(parents=True)
    report_path = nested / "lint-results-debug.xml"
    report_path.write_text(LINT_XML)

    found = find_lint_report(tmp_path)

    assert found == report_path


def test_find_lint_report_returns_none_when_absent(tmp_path):
    assert find_lint_report(tmp_path) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd compiler && python3 -m venv venv && source venv/bin/activate && pip install -r requirements-dev.txt && pytest tests/test_lint_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.lint_parser'`.

- [ ] **Step 4: Implement `lint_parser.py`**

Create `compiler/app/lint_parser.py`:

```python
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

COUNTED_SEVERITIES = {"Warning", "Error"}


def find_lint_report(project_dir: Path) -> Optional[Path]:
    project_dir = Path(project_dir)
    for path in project_dir.rglob("lint-results*.xml"):
        return path
    return None


def parse_lint_report(report_path: Path) -> list:
    tree = ET.parse(report_path)
    root = tree.getroot()
    issues = []
    for issue_el in root.findall("issue"):
        severity = issue_el.get("severity", "")
        message = issue_el.get("message", "")
        location_el = issue_el.find("location")
        file_path = location_el.get("file") if location_el is not None else ""
        line = location_el.get("line") if location_el is not None else None
        issues.append({
            "severity": severity,
            "message": message,
            "file": file_path,
            "line": int(line) if line else None,
        })
    return issues


def count_warnings(issues: list) -> int:
    return sum(1 for issue in issues if issue["severity"] in COUNTED_SEVERITIES)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_lint_parser.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Write the failing tests for the `/lint` endpoint**

Create `compiler/app/lint_runner.py` with just the `extract_zip` helper first (needed by the test's zip fixture builder and by `main.py`):

```python
import zipfile
from pathlib import Path

SDK_DIR = "/opt/android-sdk"
GRADLE_TIMEOUT_SECONDS = 280  # leaves headroom under the caller's 5-minute HTTP timeout


def extract_zip(zip_bytes: bytes, dest_dir: Path) -> None:
    zip_path = dest_dir / "project.zip"
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


async def run_lint(project_dir: Path) -> None:
    """Runs `sh ./gradlew lint` (or the preinstalled fallback Gradle if no
    wrapper is present) inside project_dir. Does not raise on a non-zero
    exit code -- Android Lint's own Gradle task exits non-zero whenever
    there's an Error-severity finding, which is not the same as the build
    failing to compile; the caller decides success/failure by checking
    whether a lint report was produced, not the exit code.
    """
    import asyncio

    (project_dir / "local.properties").write_text(f"sdk.dir={SDK_DIR}\n")

    gradlew = project_dir / "gradlew"
    command = ["sh", "gradlew", "lint"] if gradlew.exists() else ["gradle", "lint"]

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(process.communicate(), timeout=GRADLE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
```

Create `compiler/tests/test_main.py`:

```python
import io
import zipfile

from fastapi.testclient import TestClient

import main as main_module
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("gradlew", "#!/bin/sh\necho fake gradlew")
        zf.writestr("build.gradle", "// stub")
    return buffer.getvalue()


def test_lint_endpoint_returns_ok_with_parsed_issues(monkeypatch):
    async def fake_run_lint(project_dir):
        reports_dir = project_dir / "build" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "lint-results-debug.xml").write_text(
            '<issues format="6"><issue severity="Warning" message="m">'
            '<location file="f.java" line="1"/></issue></issues>'
        )

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
    }


def test_lint_endpoint_returns_build_failed_when_no_report_produced(monkeypatch):
    async def fake_run_lint(project_dir):
        return None  # simulates a build that never got far enough to produce a report

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {"status": "build_failed", "warning_count": None, "issues": []}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'` (doesn't exist yet).

- [ ] **Step 8: Implement `main.py`**

Create `compiler/main.py`:

```python
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile

from app.lint_parser import count_warnings, find_lint_report, parse_lint_report
from app.lint_runner import extract_zip, run_lint

app = FastAPI(title="Android Compile/Lint Service")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/lint")
async def lint(project: UploadFile = File(...)):
    work_dir = Path(tempfile.mkdtemp(prefix="lint_"))
    try:
        extract_zip(await project.read(), work_dir)
        await run_lint(work_dir)

        report_path = find_lint_report(work_dir)
        if report_path is None:
            return {"status": "build_failed", "warning_count": None, "issues": []}

        issues = parse_lint_report(report_path)
        return {"status": "ok", "warning_count": count_warnings(issues), "issues": issues}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_main.py tests/test_lint_parser.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 10: Create the Dockerfile**

Create `compiler/Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jdk-jammy

ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH="${PATH}:${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Android command-line tools.
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools \
    && curl -sSL -o /tmp/cmdline-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    && unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_SDK_ROOT}/cmdline-tools \
    && mv ${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools ${ANDROID_SDK_ROOT}/cmdline-tools/latest \
    && rm /tmp/cmdline-tools.zip

RUN yes | sdkmanager --licenses --sdk_root=${ANDROID_SDK_ROOT} \
    && sdkmanager --sdk_root=${ANDROID_SDK_ROOT} "platform-tools" "platforms;android-34" "build-tools;34.0.0"

# Fallback Gradle, used only for uploaded projects with no gradlew wrapper.
RUN curl -sSL -o /tmp/gradle.zip https://services.gradle.org/distributions/gradle-8.5-bin.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s /opt/gradle-8.5/bin/gradle /usr/local/bin/gradle \
    && rm /tmp/gradle.zip

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: this Dockerfile is a best-effort starting point — the exact Android cmdline-tools/SDK/Gradle version pins may need adjusting once actually built, since Google periodically rotates the cmdline-tools download URL.

- [ ] **Step 11: Commit**

```bash
git add compiler/
git commit -m "feat: add standalone compiler service for real Gradle Lint checks"
```

---

### Task 2: Wire the `compiler` service into `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `backend` service gains `COMPILER_SERVICE_URL=http://compiler:8000` env var and a `depends_on: compiler` entry; a new `compiler` service builds from `./compiler`, internal-only (no host port mapping needed).

- [ ] **Step 1: Update `docker-compose.yml`**

Replace `docker-compose.yml` entirely:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_BASE=${OPENAI_API_BASE:-}
      - OPENAI_API_VERSION=${OPENAI_API_VERSION:-}
      - OPENAI_DEPLOYMENT_NAME=${OPENAI_DEPLOYMENT_NAME:-}
      - AZURE_OPENAI_KEY=${AZURE_OPENAI_KEY:-}
      - COMPILER_SERVICE_URL=http://compiler:8000
    depends_on:
      - compiler
    networks:
      - review-network

  compiler:
    build: ./compiler
    networks:
      - review-network

  frontend:
    build:
      context: ./frontend
      args:
        REACT_APP_API_URL: http://localhost:8000/api
    ports:
      - "3000:3000"
    depends_on:
      - backend
    networks:
      - review-network

networks:
  review-network:
    driver: bridge
```

- [ ] **Step 2: Verify**

Run: `docker compose config` (validates the compose file without starting anything)
Expected: prints the resolved config with no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: wire the compiler service into docker-compose"
```

---

### Task 3: Backend — binary scoring rubric (drop 0.5)

**Files:**
- Modify: `backend/app/analyzer/openai_client.py`
- Test: `backend/tests/test_openai_client.py`

**Interfaces:**
- No signature changes — `_category_instructions`'s returned text changes.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_openai_client.py`, add this test after `test_live_mode_grounds_the_prompt_with_real_descriptions`:

```python
@pytest.mark.asyncio
async def test_live_mode_rubric_is_binary_no_partial_credit(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")

    instructions = captured["json"]["messages"][1]["content"]
    assert "0.5" not in instructions
    assert "0 (fails)" in instructions
    assert "1 (meets it)" in instructions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && pytest tests/test_openai_client.py -v -k binary`
Expected: FAIL — the current rubric text still contains `"0.5 (partial)"`.

- [ ] **Step 3: Update the rubric text**

In `backend/app/analyzer/openai_client.py`, change `_category_instructions`:

```python
def _category_instructions(category_name: str, sub_criteria: list, descriptions: dict) -> str:
    criteria_lines = "\n".join(f"{sub_id}: {descriptions.get(sub_id, '')}" for sub_id in sub_criteria)
    return (
        f"Score the following {category_name} sub-criteria based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_openai_client.py -v`
Expected: all tests PASS (including the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: drop 0.5 partial-credit option, binary 0/1 scoring rubric"
```

---

### Task 4: Backend — `compile_checker.py` HTTP client

**Files:**
- Create: `backend/app/analyzer/compile_checker.py`
- Test: `backend/tests/test_compile_checker.py`

**Interfaces:**
- Produces: `async def check_compile_warnings(zip_path: Path) -> dict` returning `{"status": "ok"|"build_failed"|"unavailable", "warning_count": int|None, "issues": list}` — whatever the compiler service's JSON body was on success, or the `"unavailable"` shape on any connection error/timeout. Consumed by `reviews.py` (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_compile_checker.py`:

```python
import httpx
import pytest

from app.analyzer import compile_checker


@pytest.mark.asyncio
async def test_returns_parsed_result_on_success(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "status": "ok",
                "warning_count": 1,
                "issues": [{"severity": "Warning", "message": "m", "file": "f", "line": 1}],
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await compile_checker.check_compile_warnings(zip_path)

    assert result == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f", "line": 1}],
    }


@pytest.mark.asyncio
async def test_returns_unavailable_on_connection_error(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await compile_checker.check_compile_warnings(zip_path)

    assert result == {"status": "unavailable", "warning_count": None, "issues": []}


@pytest.mark.asyncio
async def test_returns_unavailable_on_non_2xx_response(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=500, json={"error": "boom"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await compile_checker.check_compile_warnings(zip_path)

    assert result == {"status": "unavailable", "warning_count": None, "issues": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_compile_checker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analyzer.compile_checker'`.

- [ ] **Step 3: Implement `compile_checker.py`**

Create `backend/app/analyzer/compile_checker.py`:

```python
import os
from pathlib import Path

import httpx

DEFAULT_COMPILER_SERVICE_URL = "http://compiler:8000"
TIMEOUT_SECONDS = 300.0


async def check_compile_warnings(zip_path: Path) -> dict:
    base_url = os.environ.get("COMPILER_SERVICE_URL", DEFAULT_COMPILER_SERVICE_URL)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            with open(zip_path, "rb") as f:
                response = await client.post(
                    f"{base_url.rstrip('/')}/lint",
                    files={"project": ("project.zip", f, "application/zip")},
                )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, OSError):
        return {"status": "unavailable", "warning_count": None, "issues": []}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_compile_checker.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/compile_checker.py backend/tests/test_compile_checker.py
git commit -m "feat: add compile_checker HTTP client for the compiler service"
```

---

### Task 5: Backend — wire the compiling phase and 1.4 scoring into `_run_review`

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: `backend/tests/test_reviews_create.py`, `backend/tests/test_reviews_progress.py`, `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `check_compile_warnings(zip_path) -> dict` (Task 4).
- Produces: `GET /progress` gains `lint_issues: {severity, message, file, line}[]` and `compile_status: "ok"|"build_failed"|"unavailable"|null`. New pure helpers `_compile_result_to_sub_score(compile_result: dict) -> dict` and `_merge_compile_result_into_category_1(sub_results: dict, compile_sub_result: dict) -> dict`, both usable/testable directly from `reviews_module`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_create.py`, update the two existing `score_category` fakes to also mock `check_compile_warnings` (both currently reach the new compiling phase and would otherwise attempt a real network call). Update `test_run_review_updates_message_per_category_during_scoring`:

```python
async def test_run_review_updates_message_per_category_during_scoring(monkeypatch):
    review_id = "progress-message-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    seen_messages = []

    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        seen_messages.append(_reviews[review_id]["message"])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert seen_messages == [
        "Evaluating Code naming conventions / Code Structure...",
        "Evaluating Reliability, Security & Observability...",
        "Evaluating Delivery Discipline & Architecture...",
        "Evaluating AI Usage & Code Ownership...",
        "Evaluating Safe & Integrated AI Code...",
    ]

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert state["message"] == "Review complete"
```

Apply the same `_fake_check_compile_warnings` mock to `test_run_review_updates_category_scores_progressively` (add the `async def _fake_check_compile_warnings` function and its `monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)` call, right alongside its existing `score_category` mock).

Add `monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)` (with the same fake, defined inline) to `test_run_review_builds_prompt_log_and_code_context` too, right after its `monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)` line:

```python
    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)
```

Now add new tests after `test_run_review_builds_prompt_log_and_code_context`:

```python
def test_compile_result_to_sub_score_ok_zero_warnings():
    result = reviews_module._compile_result_to_sub_score({"status": "ok", "warning_count": 0, "issues": []})
    assert result == {"score": 1, "remark": "No Lint warnings or errors found."}


def test_compile_result_to_sub_score_ok_with_warnings():
    result = reviews_module._compile_result_to_sub_score({"status": "ok", "warning_count": 3, "issues": []})
    assert result == {"score": 0, "remark": "3 Lint warning(s)/error(s) found."}


def test_compile_result_to_sub_score_build_failed():
    result = reviews_module._compile_result_to_sub_score(
        {"status": "build_failed", "warning_count": None, "issues": []}
    )
    assert result == {"score": 0, "remark": "Project failed to compile."}


def test_compile_result_to_sub_score_unavailable():
    result = reviews_module._compile_result_to_sub_score(
        {"status": "unavailable", "warning_count": None, "issues": []}
    )
    assert result == {"score": None, "remark": "Compile check unavailable (compiler service unreachable)."}


def test_merge_compile_result_into_category_1_preserves_declared_order():
    llm_sub_results = {
        "1.1": {"score": 1, "remark": ""},
        "1.2": {"score": 1, "remark": ""},
        "1.3": {"score": 1, "remark": ""},
        "1.5": {"score": 1, "remark": ""},
        "1.6": {"score": 1, "remark": ""},
    }
    compile_sub_result = {"score": 0, "remark": "2 Lint warning(s)/error(s) found."}

    merged = reviews_module._merge_compile_result_into_category_1(llm_sub_results, compile_sub_result)

    assert list(merged.keys()) == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
    assert merged["1.4"] == compile_sub_result


async def test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm(monkeypatch):
    review_id = "compile-check-1-4"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_sub_criteria = {}

    async def fake_score_category(category_name, sub_criteria, descriptions, code_snippets):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_compile_warnings(zip_path_arg):
        return {
            "status": "ok", "warning_count": 2,
            "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
        }

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    # "1.4" must never be sent to the LLM -- it's scored deterministically.
    assert "1.4" not in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "ok"
    assert state["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}]

    # Category 1: 5 LLM sub-criteria stubbed at score 1, plus 1.4 scored 0
    # (2 Lint warnings) -> (5*1 + 0) / 6 = 0.8333 -> rounds to 83.0%. Proves
    # the real 1.4 score is actually folded into the average, not dropped.
    assert state["category_scores"][0]["percent_points"] == 83.0
```

In `backend/tests/test_reviews_progress.py`, extend `test_progress_reflects_stored_state`'s stored state and assertions:

```python
        "code_context": "class MainActivity {}",
        "prompt_log": [
            {
                "label": "Code naming conventions / Code Structure",
                "prompt_text": "Score the following...",
                "tokens": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None},
            },
        ],
        "lint_issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
        "compile_status": "ok",
    }
```

and add, right after the existing `assert body["prompt_log"] == [...]` assertion:

```python
    assert body["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}]
    assert body["compile_status"] == "ok"
```

Extend `test_progress_defaults_detection_fields_when_absent`:

```python
    assert body["code_context"] is None
    assert body["prompt_log"] == []
    assert body["lint_issues"] == []
    assert body["compile_status"] is None
```

In `backend/tests/test_reviews_integration.py`, add a mock for `check_compile_warnings` (this test currently reaches the real pipeline with no compile-check mock, which would otherwise attempt a real network call to the nonexistent `compiler` host). Add right before the `with TestClient(app) as client:` block:

```python
    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)
```

And add an assertion after the existing `assert final_state["total_score_pct"] == 100.0` line:

```python
        assert final_state["compile_status"] == "ok"
        assert final_state["lint_issues"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_reviews_create.py tests/test_reviews_progress.py tests/test_reviews_integration.py -v`
Expected: the new pure-function tests FAIL with `AttributeError: module 'app.api.reviews' has no attribute '_compile_result_to_sub_score'` (etc.); the new `_run_review`-level test and the two progress tests FAIL on the new field assertions.

- [ ] **Step 3: Implement the wiring**

In `backend/app/api/reviews.py`, add the import:

```python
from app.analyzer.compile_checker import check_compile_warnings
```

Add the two new fields to `_new_review_state`:

```python
        "code_context": None,
        "prompt_log": [],
        "lint_issues": [],
        "compile_status": None,
    }
```

Add the two pure helper functions, right after `_new_review_state`:

```python
def _compile_result_to_sub_score(compile_result: dict) -> dict:
    status = compile_result["status"]
    warning_count = compile_result["warning_count"]
    if status == "unavailable":
        return {"score": None, "remark": "Compile check unavailable (compiler service unreachable)."}
    if status == "build_failed":
        return {"score": 0, "remark": "Project failed to compile."}
    if warning_count == 0:
        return {"score": 1, "remark": "No Lint warnings or errors found."}
    return {"score": 0, "remark": f"{warning_count} Lint warning(s)/error(s) found."}


def _merge_compile_result_into_category_1(sub_results: dict, compile_sub_result: dict) -> dict:
    merged = {**sub_results, "1.4": compile_sub_result}
    return {sub_id: merged[sub_id] for sub_id in CATEGORIES["1"]["sub_criteria"]}
```

Add the new `"compiling"` phase right after the analyzing phase's `stats["analysis_time_ms"]` line and before the scoring loop (i.e. right after `state["progress"] = 50` following the analyzing block — replace that `50` with `35`, matching the shifted progress checkpoints below):

```python
        code_context = gather_code_context(extract_dir)
        state["code_context"] = code_context
        template_ws = load_workbook(template_path).active
        sub_criteria_descriptions = extract_sub_criteria_descriptions(template_ws, CATEGORIES)
        stats["analysis_time_ms"] = int((time.monotonic() - t1) * 1000)
        state["progress"] = 35

        t1b = time.monotonic()
        state["phase"] = "compiling"
        state["message"] = "Compiling and running Lint checks..."
        compile_result = await check_compile_warnings(zip_path)
        state["lint_issues"] = compile_result["issues"]
        state["compile_status"] = compile_result["status"]
        compile_sub_result = _compile_result_to_sub_score(compile_result)
        stats["compile_time_ms"] = int((time.monotonic() - t1b) * 1000)
        state["progress"] = 55
```

Update the scoring loop to exclude `"1.4"` from what's sent to the LLM for category 1, and merge the real result back in order:

```python
        t2 = time.monotonic()
        state["phase"] = "scoring"
        scores_by_category = {}
        category_count = len(CATEGORIES)
        for index, (category_id, category) in enumerate(CATEGORIES.items()):
            state["message"] = f"Evaluating {category['name']}..."
            llm_sub_criteria = (
                [sub_id for sub_id in category["sub_criteria"] if sub_id != "1.4"]
                if category_id == "1" else category["sub_criteria"]
            )
            sub_results, prompt_info = await score_category(
                category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context
            )
            if category_id == "1":
                sub_results = _merge_compile_result_into_category_1(sub_results, compile_sub_result)
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
            state["category_scores"][index]["percent_points"] = scores_by_category[category_id]["percent_points"]
            state["prompt_log"].append(prompt_info)
            state["progress"] = 55 + int(30 * (index + 1) / category_count)
        stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)
        state["total_score_pct"] = compute_total_score_pct(scores_by_category)
```

Update the generating phase's progress checkpoints:

```python
        t3 = time.monotonic()
        state["phase"] = "generating"
        state["message"] = "Generating overall summary..."
        general_remarks, remarks_prompt_info = await generate_general_remarks(scores_by_category)
        state["prompt_log"].append(remarks_prompt_info)
        state["progress"] = 95
```

(The `state["message"] = "Populating review document..."` line right after keeps its existing position and text — only the progress number above it changes from 90 to 95.)

Add the two fields to `get_progress`'s response:

```python
        "code_context": state.get("code_context"),
        "prompt_log": state.get("prompt_log", []),
        "lint_issues": state.get("lint_issues", []),
        "compile_status": state.get("compile_status"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest -v`
Expected: all tests PASS (full backend suite).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_progress.py backend/tests/test_reviews_integration.py
git commit -m "feat: score clause 1.4 from a real compile/lint check instead of the LLM"
```

---

### Task 6: Frontend — 5th progress step ("Compiling & linting")

**Files:**
- Modify: `frontend/src/components/ProgressTracker.jsx`
- Test: `frontend/src/components/ProgressTracker.test.jsx`

**Interfaces:**
- No prop-shape change — `STEPS` gains one entry; `stepIndexForPhase`'s generic `findIndex`/`length` logic needs no changes.

- [ ] **Step 1: Write the failing test update**

In `frontend/src/components/ProgressTracker.test.jsx`, update the first test:

```jsx
test("shows all five steps before the first poll resolves", () => {
  getProgress.mockReturnValue(new Promise(() => {}));

  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);

  expect(screen.getByText("Extracting archive")).toBeInTheDocument();
  expect(screen.getByText("Analyzing code")).toBeInTheDocument();
  expect(screen.getByText("Compiling & linting")).toBeInTheDocument();
  expect(screen.getByText("Scoring with AI")).toBeInTheDocument();
  expect(screen.getByText("Generating report")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- ProgressTracker --watchAll=false`
Expected: FAIL — `Unable to find an element with the text: Compiling & linting`.

- [ ] **Step 3: Add the step**

In `frontend/src/components/ProgressTracker.jsx`, update `STEPS`:

```jsx
const STEPS = [
  { phase: "extracting", label: "Extracting archive" },
  { phase: "analyzing", label: "Analyzing code" },
  { phase: "compiling", label: "Compiling & linting" },
  { phase: "scoring", label: "Scoring with AI" },
  { phase: "generating", label: "Generating report" },
];
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- ProgressTracker --watchAll=false`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressTracker.jsx frontend/src/components/ProgressTracker.test.jsx
git commit -m "feat: add Compiling & linting step to ProgressTracker"
```

---

### Task 7: Frontend — 4th findings card ("Lint issues")

**Files:**
- Modify: `frontend/src/components/FindingsPanel.jsx`
- Test: `frontend/src/components/FindingsPanel.test.jsx`

**Interfaces:**
- Produces: `FindingsPanel` gains two new props, `lintIssues: {severity, message, file, line}[]` and `compileStatus: "ok"|"build_failed"|"unavailable"|null`. Consumed by `App.jsx` (Task 8).

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/FindingsPanel.test.jsx` entirely:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings at all", () => {
  const { container } = render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus={null} />
  );
  expect(container.firstChild).toBeNull();
});

test("shows all four cards once any finding is present, with placeholders for absent ones", () => {
  render(
    <FindingsPanel
      warnings={["Missing AndroidManifest.xml"]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[]}
      compileStatus={null}
    />
  );

  expect(screen.getByText("Warnings")).toBeInTheDocument();
  expect(screen.getByText("Test coverage")).toBeInTheDocument();
  expect(screen.getByText("No coverage report found.")).toBeInTheDocument();
  expect(screen.getByText("Secrets found")).toBeInTheDocument();
  expect(screen.getByText("No secrets found.")).toBeInTheDocument();
  expect(screen.getByText("Lint issues")).toBeInTheDocument();
  expect(screen.getByText("Not yet checked.")).toBeInTheDocument();
});

test("shows the coverage percentage and secret summary when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
      lintIssues={[]}
      compileStatus={null}
    />
  );
  expect(screen.getByText("82.5%")).toBeInTheDocument();
  expect(screen.getByText("1 possible secret found")).toBeInTheDocument();
});

test("expands the warnings card to list every warning on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={["Missing AndroidManifest.xml", "Outdated Gradle plugin"]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[]}
      compileStatus={null}
    />
  );

  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
  await user.click(screen.getByText("2 issues found"));
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByText("Outdated Gradle plugin")).toBeInTheDocument();
});

test("expands the secrets card to list file:line (pattern) for every secret on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={null}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
      lintIssues={[]}
      compileStatus={null}
    />
  );

  await user.click(screen.getByText("1 possible secret found"));
  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});

test("shows a clean caption when the compile check succeeds with no issues", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="ok" />
  );
  expect(screen.getByText("No Lint warnings or errors found.")).toBeInTheDocument();
});

test("expands the Lint issues card to list every issue on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[{ file: "Main.java", line: 10, severity: "Warning", message: "Unused import" }]}
      compileStatus="ok"
    />
  );

  expect(screen.queryByText("Main.java:10 (Warning): Unused import")).not.toBeInTheDocument();
  await user.click(screen.getByText("1 issue found"));
  expect(screen.getByText("Main.java:10 (Warning): Unused import")).toBeInTheDocument();
});

test("shows a build-failed caption when the project could not compile", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="build_failed" />
  );
  expect(screen.getByText("Project failed to compile.")).toBeInTheDocument();
});

test("shows an unavailable caption when the compile check couldn't run", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="unavailable" />
  );
  expect(screen.getByText("Compile check unavailable.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- FindingsPanel --watchAll=false`
Expected: FAIL — the current component doesn't accept `lintIssues`/`compileStatus` and has no "Lint issues" card.

- [ ] **Step 3: Implement the 4th card**

Replace `frontend/src/components/FindingsPanel.jsx` entirely:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";

function FindingCard({ kicker, value, caption, expandable, expanded, onToggle, children }) {
  return (
    <div className="card blueprint" style={{ padding: "var(--space-4)" }}>
      <CornerMarks />
      <div className="card-kicker">{kicker}</div>
      <div className="card-title" style={{ fontSize: 32 }}>{value}</div>
      {expandable ? (
        <button
          type="button"
          className="card-body"
          style={{ textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit" }}
          onClick={onToggle}
        >
          {caption}
        </button>
      ) : (
        <p className="card-body">{caption}</p>
      )}
      {expanded && children}
    </div>
  );
}

function lintCardProps(compileStatus, lintIssues) {
  if (compileStatus === "ok") {
    return lintIssues.length > 0
      ? { value: lintIssues.length, caption: `${lintIssues.length} issue${lintIssues.length === 1 ? "" : "s"} found`, expandable: true }
      : { value: 0, caption: "No Lint warnings or errors found.", expandable: false };
  }
  if (compileStatus === "build_failed") {
    return { value: "—", caption: "Project failed to compile.", expandable: false };
  }
  if (compileStatus === "unavailable") {
    return { value: "—", caption: "Compile check unavailable.", expandable: false };
  }
  return { value: "—", caption: "Not yet checked.", expandable: false };
}

export default function FindingsPanel({ warnings, testCoverage, secretsFound, lintIssues, compileStatus }) {
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [secretsOpen, setSecretsOpen] = useState(false);
  const [lintOpen, setLintOpen] = useState(false);

  const hasWarnings = warnings && warnings.length > 0;
  const hasSecrets = secretsFound && secretsFound.length > 0;
  const hasCoverage = testCoverage !== null && testCoverage !== undefined;
  const hasLintStatus = compileStatus !== null && compileStatus !== undefined;

  if (!hasWarnings && !hasSecrets && !hasCoverage && !hasLintStatus) {
    return null;
  }

  const lint = lintCardProps(compileStatus, lintIssues || []);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "var(--space-4)" }}>
      <FindingCard
        kicker="Warnings"
        value={warnings.length}
        caption={hasWarnings ? `${warnings.length} issue${warnings.length === 1 ? "" : "s"} found` : "No warnings found."}
        expandable={hasWarnings}
        expanded={warningsOpen}
        onToggle={() => setWarningsOpen((open) => !open)}
      >
        <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.1em", fontSize: 13 }}>
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      </FindingCard>

      <FindingCard
        kicker="Test coverage"
        value={hasCoverage ? `${testCoverage}%` : "—"}
        caption={hasCoverage ? "Coverage report found." : "No coverage report found."}
        expandable={false}
      />

      <FindingCard
        kicker="Secrets found"
        value={secretsFound.length}
        caption={hasSecrets ? `${secretsFound.length} possible secret${secretsFound.length === 1 ? "" : "s"} found` : "No secrets found."}
        expandable={hasSecrets}
        expanded={secretsOpen}
        onToggle={() => setSecretsOpen((open) => !open)}
      >
        <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.1em", fontSize: 13 }}>
          {secretsFound.map((secret, index) => (
            <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
          ))}
        </ul>
      </FindingCard>

      <FindingCard
        kicker="Lint issues"
        value={lint.value}
        caption={lint.caption}
        expandable={lint.expandable}
        expanded={lintOpen}
        onToggle={() => setLintOpen((open) => !open)}
      >
        <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.1em", fontSize: 13 }}>
          {(lintIssues || []).map((issue, index) => (
            <li key={index}>{issue.file}:{issue.line} ({issue.severity}): {issue.message}</li>
          ))}
        </ul>
      </FindingCard>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- FindingsPanel --watchAll=false`
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FindingsPanel.jsx frontend/src/components/FindingsPanel.test.jsx
git commit -m "feat: add Lint issues card to FindingsPanel"
```

---

### Task 8: Frontend — wire `lintIssues`/`compileStatus` through `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: `FindingsPanel`'s new `lintIssues`/`compileStatus` props (Task 7).

- [ ] **Step 1: Write the failing test update**

In `frontend/src/App.test.jsx`, add `lint_issues`/`compile_status` to the happy-path mock:

```jsx
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    category_scores: [
      { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
    lint_issues: [],
    compile_status: "ok",
  });
```

and add an assertion right after the existing `getAllByText("Code naming conventions / Code Structure")` assertion:

```jsx
  expect(screen.getByText("No Lint warnings or errors found.")).toBeInTheDocument();
```

Add `lint_issues: [], compile_status: null,` to the other `getProgress.mockResolvedValue` call (the "review itself fails" test), for API-shape consistency — no new assertion needed there since that scenario never reaches the findings render (state flips to `"error"` before the 2-band layout renders).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- App.test --watchAll=false`
Expected: FAIL — the current `App.jsx` doesn't pass `lintIssues`/`compileStatus` to `FindingsPanel`, so it renders "Not yet checked." instead of "No Lint warnings or errors found."

- [ ] **Step 3: Wire the props**

In `frontend/src/App.jsx`, update the `<FindingsPanel>` call:

```jsx
                {progressData && (
                  <div style={{ marginTop: state === "polling" ? "var(--space-5)" : 0 }}>
                    <FindingsPanel
                      warnings={progressData.warnings}
                      testCoverage={progressData.test_coverage}
                      secretsFound={progressData.secrets_found}
                      lintIssues={progressData.lint_issues}
                      compileStatus={progressData.compile_status}
                    />
                  </div>
                )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- --watchAll=false`
Expected: the ENTIRE frontend suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: wire lint issues and compile status into App's FindingsPanel"
```

---

## Final Verification

```bash
cd backend && source venv/bin/activate && pytest -v
cd frontend && CI=true npm test -- --watchAll=false
cd compiler && source venv/bin/activate && pytest -v
```

All three must PASS with zero failures before considering this plan complete.

## Manual Check

The `compiler` service cannot be meaningfully exercised end-to-end by unit tests alone (no real Android SDK/Gradle in the test environment). After implementation, build and run it via `docker compose up -d --build compiler` and upload a real small Android project directly to `POST http://localhost:<mapped-port>/lint` (or through the full pipeline via the backend) to confirm: the image builds successfully, licenses are accepted non-interactively, a real project's `gradlew lint` actually runs, and the returned `warning_count`/`issues` match what a manual `./gradlew lint` run on that same project reports.
