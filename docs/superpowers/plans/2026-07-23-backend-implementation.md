# Android Code Review Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that ingests an Android project ZIP + Excel review template, analyzes the code, scores it via Azure OpenAI (or a stub), and returns a populated Excel file — fully testable via pytest, with no frontend required.

**Architecture:** Five focused modules under `backend/app/analyzer/` (gradle/source parsing, secrets scanning, version checking, Excel population, Azure OpenAI scoring) composed by a single orchestration function per review, exposed through three FastAPI endpoints backed by an in-memory review-state store. Progress is polled, not pushed.

**Tech Stack:** Python 3.11, FastAPI, httpx, openpyxl, pytest, pytest-asyncio.

## Global Constraints

- Python 3.11; FastAPI async endpoints throughout.
- No WebSocket — progress is polling-only (`GET /api/reviews/{id}/progress`).
- Excel: update `.value` on data cells only; never touch font/fill/border/merge objects; never overwrite formula cells; resolve columns dynamically from the header row, never hardcode column letters.
- Non-fatal errors (missing build.gradle, no coverage report found, version-parse failure, Azure OpenAI timeout/error) → continue processing, leave that value `None`/blank, do not stop the review.
- Fatal errors (invalid ZIP structure, Excel template missing expected columns, no `.java`/`.kt` source files found) → stop the review, set `status: "error"`.
- All three API endpoints return HTTP 200 on success; processing errors are carried in the JSON body (`status`, `message`/`error`, `phase`), never as a 4xx/5xx from `/api/reviews`.
- No secrets or API keys ever appear in logs or error messages.
- Stub mode: when `AZURE_OPENAI_KEY` is unset or empty, `openai_client.score_category` returns deterministic `[STUB]`-prefixed scores instead of calling Azure or failing. No separate code path is needed later — setting a real key switches to live calls automatically.
- Temp files: one `tempfile.mkdtemp()` directory per review; uploaded ZIP/template and the extracted tree are deleted immediately once scoring finishes (success or error); the output `.xlsx` is kept until downloaded, then deleted via a `BackgroundTask`.
- Category IDs are exactly `"1"`, `"2"`, `"3"`, `"4"`, `"6"` (there is no category `"5"` — the 5th category's code is `"6"` per the source template), with sub-criteria `1.1-1.6`, `2.1-2.4`, `3.1-3.4`, `4.1-4.3`, `6.1-6.3`.

---

### Task 1: Backend scaffolding and health endpoint

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/pytest.ini`
- Create: `backend/main.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/analyzer/__init__.py`
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/logger.py`
- Test: `backend/tests/__init__.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.utils.logger.get_logger(name: str) -> logging.Logger`, used by later tasks for structured logging.
- Produces: `main.app` — the FastAPI instance later tasks attach routers to.

- [ ] **Step 1: Create the backend directory skeleton and empty package files**

```bash
mkdir -p backend/app/api backend/app/analyzer backend/app/utils backend/tests
touch backend/app/__init__.py backend/app/api/__init__.py backend/app/analyzer/__init__.py backend/app/utils/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: Write requirements files**

`backend/requirements.txt`:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
httpx==0.25.2
openpyxl==3.1.2
python-multipart==0.0.6
python-dotenv==1.0.0
packaging==23.2
```

`backend/requirements-dev.txt`:
```
-r requirements.txt
pytest==7.4.3
pytest-asyncio==0.21.1
```

`backend/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
```

- [ ] **Step 3: Write the logger utility**

`backend/app/utils/logger.py`:
```python
import logging


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

- [ ] **Step 4: Write the failing test for the health endpoint**

`backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok_and_stub_mode_when_no_key(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["azure_openai_connected"] is False
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd backend && pip install -r requirements-dev.txt && python -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 6: Write main.py**

`backend/main.py`:
```python
from fastapi import FastAPI

from app.analyzer.openai_client import is_stub_mode

app = FastAPI(title="Android Code Review Automation")


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}
```

This imports `is_stub_mode` from `app.analyzer.openai_client`, which does not exist yet. Create a minimal placeholder so this task is self-contained (Task 8 will replace it with the full implementation):

`backend/app/analyzer/openai_client.py`:
```python
import os


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/pytest.ini backend/main.py backend/app backend/tests
git commit -m "feat: scaffold backend with health endpoint"
```

---

### Task 2: Version checker

**Files:**
- Create: `backend/app/analyzer/version_checker.py`
- Test: `backend/tests/test_version_checker.py`

**Interfaces:**
- Consumes: nothing (pure function module).
- Produces: `compare_versions(gradle_info: dict) -> list[dict]`, consumed by Task 6 (`analyze_project`). `gradle_info` keys used: `compile_sdk` (int|None), `target_sdk` (int|None), `gradle_version` (str|None), `kotlin_version` (str|None). Each returned warning is `{"issue": str}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_version_checker.py`:
```python
from app.analyzer.version_checker import compare_versions


def test_flags_outdated_versions():
    gradle_info = {
        "compile_sdk": 30,
        "target_sdk": 30,
        "gradle_version": "7.0",
        "kotlin_version": "1.6.0",
    }
    warnings = compare_versions(gradle_info)
    issues = [w["issue"] for w in warnings]
    assert any("compileSdkVersion 30" in i for i in issues)
    assert any("targetSdkVersion 30" in i for i in issues)
    assert any("Gradle version 7.0" in i for i in issues)
    assert any("Kotlin version 1.6.0" in i for i in issues)
    assert len(warnings) == 4


def test_no_warnings_when_up_to_date():
    gradle_info = {
        "compile_sdk": 34,
        "target_sdk": 34,
        "gradle_version": "8.2",
        "kotlin_version": "1.9.20",
    }
    assert compare_versions(gradle_info) == []


def test_missing_values_are_skipped_not_flagged():
    gradle_info = {"compile_sdk": None, "target_sdk": None, "gradle_version": None, "kotlin_version": None}
    assert compare_versions(gradle_info) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_version_checker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.version_checker'`

- [ ] **Step 3: Implement version_checker.py**

`backend/app/analyzer/version_checker.py`:
```python
from typing import Optional

LATEST_VERSIONS = {
    "compile_sdk": 34,
    "target_sdk": 34,
    "gradle": (8, 0),
    "kotlin": (1, 9),
}


def _parse_version_tuple(version_str: Optional[str]):
    if not version_str:
        return None
    nums = []
    for part in version_str.split("."):
        digits = "".join(c for c in part if c.isdigit())
        if digits == "":
            break
        nums.append(int(digits))
    return tuple(nums) if nums else None


def compare_versions(gradle_info: dict) -> list:
    warnings = []

    compile_sdk = gradle_info.get("compile_sdk")
    if compile_sdk is not None and compile_sdk < LATEST_VERSIONS["compile_sdk"]:
        warnings.append(
            {"issue": f"compileSdkVersion {compile_sdk} is outdated, latest is {LATEST_VERSIONS['compile_sdk']}"}
        )

    target_sdk = gradle_info.get("target_sdk")
    if target_sdk is not None and target_sdk < LATEST_VERSIONS["target_sdk"]:
        warnings.append(
            {"issue": f"targetSdkVersion {target_sdk} is outdated, latest is {LATEST_VERSIONS['target_sdk']}"}
        )

    gradle_version = _parse_version_tuple(gradle_info.get("gradle_version"))
    if gradle_version is not None and gradle_version < LATEST_VERSIONS["gradle"]:
        warnings.append(
            {"issue": f"Gradle version {gradle_info.get('gradle_version')} is outdated, latest is 8.0+"}
        )

    kotlin_version = _parse_version_tuple(gradle_info.get("kotlin_version"))
    if kotlin_version is not None and kotlin_version < LATEST_VERSIONS["kotlin"]:
        warnings.append(
            {"issue": f"Kotlin version {gradle_info.get('kotlin_version')} is outdated, latest is 1.9+"}
        )

    return warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_version_checker.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/version_checker.py backend/tests/test_version_checker.py
git commit -m "feat: add gradle/SDK version checker"
```

---

### Task 3: Secrets scanner

**Files:**
- Create: `backend/app/analyzer/secrets_scanner.py`
- Test: `backend/tests/test_secrets_scanner.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `scan_directory(project_dir: Path) -> list[dict]`, consumed by Task 6. Each finding is `{"file": str, "line": int, "pattern": str}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_secrets_scanner.py`:
```python
from pathlib import Path

from app.analyzer.secrets_scanner import scan_directory


def test_finds_hardcoded_api_key(tmp_path: Path):
    java_file = tmp_path / "Constants.java"
    java_file.write_text(
        'public class Constants {\n'
        '    public static final String API_KEY = "ab12cd34ef56gh78ij90kl12mn34op56";\n'
        '}\n'
    )
    findings = scan_directory(tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == str(java_file)
    assert findings[0]["line"] == 2
    assert findings[0]["pattern"] == "api_key"


def test_finds_firebase_key(tmp_path: Path):
    xml_file = tmp_path / "google-services.json.xml"
    xml_file.write_text('"key": "AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY"\n')
    findings = scan_directory(tmp_path)
    assert any(f["pattern"] == "firebase_key" for f in findings)


def test_no_findings_in_clean_code(tmp_path: Path):
    java_file = tmp_path / "MainActivity.java"
    java_file.write_text('public class MainActivity {\n    void onCreate() {}\n}\n')
    assert scan_directory(tmp_path) == []


def test_ignores_non_source_extensions(tmp_path: Path):
    binary_like = tmp_path / "notes.txt"
    binary_like.write_text('api_key = "ab12cd34ef56gh78ij90kl12mn34op56"\n')
    assert scan_directory(tmp_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_secrets_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.secrets_scanner'`

- [ ] **Step 3: Implement secrets_scanner.py**

`backend/app/analyzer/secrets_scanner.py`:
```python
import re
from pathlib import Path

SECRET_PATTERNS = {
    "api_key": re.compile(r'api[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{20,}["\']?', re.IGNORECASE),
    "aws_secret": re.compile(
        r'aws[_-]?secret[_-]?(access[_-]?)?key\s*[:=]\s*["\']?[a-zA-Z0-9/+=]{20,}["\']?', re.IGNORECASE
    ),
    "generic_token": re.compile(r'(token|secret|password)\s*[:=]\s*["\'][a-zA-Z0-9_\-]{20,}["\']', re.IGNORECASE),
    "firebase_key": re.compile(r'"key"\s*:\s*"AIza[0-9a-zA-Z_\-]{35}"'),
}

SCAN_EXTENSIONS = {".java", ".kt", ".xml", ".properties", ".gradle", ".kts"}


def scan_file(file_path: Path) -> list:
    findings = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern_name, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append({"file": str(file_path), "line": line_no, "pattern": pattern_name})
                break
    return findings


def scan_directory(project_dir: Path) -> list:
    findings = []
    for path in Path(project_dir).rglob("*"):
        if path.is_file() and path.suffix in SCAN_EXTENSIONS:
            findings.extend(scan_file(path))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_secrets_scanner.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/secrets_scanner.py backend/tests/test_secrets_scanner.py
git commit -m "feat: add hardcoded secrets scanner"
```

---

### Task 4: Gradle parsing and project structure validation

**Files:**
- Create: `backend/app/analyzer/android_analyzer.py`
- Test: `backend/tests/test_android_analyzer_gradle.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_gradle(content: str) -> dict` with keys `compile_sdk`, `target_sdk`, `gradle_version`, `kotlin_version`, `dependencies`, `has_jacoco`, `has_kover` — consumed by Task 6 and by `version_checker.compare_versions`.
  - `validate_project_structure(project_dir: Path) -> dict` with keys `warnings` (list[str]) and `fatal_error` (str|None) — consumed by Task 6.
  - `find_gradle_file(project_dir: Path) -> Path | None` — consumed by Task 6 and reused by Task 5.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_android_analyzer_gradle.py`:
```python
from pathlib import Path

from app.analyzer.android_analyzer import find_gradle_file, parse_gradle, validate_project_structure

GROOVY_GRADLE = """
buildscript {
    ext.kotlin_version = '1.6.0'
    dependencies {
        classpath 'com.android.tools.build:gradle:7.0.0'
    }
}
apply plugin: 'jacoco'
android {
    compileSdkVersion 30
    defaultConfig {
        targetSdkVersion 30
    }
}
dependencies {
    implementation 'androidx.core:core-ktx:1.9.0'
    testImplementation 'junit:junit:4.13.2'
}
"""

KOTLIN_DSL_GRADLE = """
plugins {
    id("com.android.application") version "8.1.0"
    id("org.jetbrains.kotlin.android") version "1.9.0"
}
android {
    compileSdk = 34
    defaultConfig {
        targetSdk = 34
    }
}
dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
}
"""


def test_parse_groovy_gradle():
    info = parse_gradle(GROOVY_GRADLE)
    assert info["compile_sdk"] == 30
    assert info["target_sdk"] == 30
    assert info["gradle_version"] == "7.0.0"
    assert info["kotlin_version"] == "1.6.0"
    assert "androidx.core:core-ktx:1.9.0" in info["dependencies"]
    assert info["has_jacoco"] is True
    assert info["has_kover"] is False


def test_parse_kotlin_dsl_gradle():
    info = parse_gradle(KOTLIN_DSL_GRADLE)
    assert info["compile_sdk"] == 34
    assert info["target_sdk"] == 34
    assert info["gradle_version"] == "8.1.0"
    assert info["kotlin_version"] == "1.9.0"
    assert info["has_jacoco"] is False


def test_parse_gradle_missing_fields_are_none():
    info = parse_gradle("android {}\n")
    assert info["compile_sdk"] is None
    assert info["gradle_version"] is None
    assert info["dependencies"] == []


def test_find_gradle_file_prefers_app_module(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("// root")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("android {}")
    found = find_gradle_file(tmp_path)
    assert found == app_dir / "build.gradle"


def test_validate_project_structure_happy_path(tmp_path: Path):
    (tmp_path / "build.gradle").write_text(GROOVY_GRADLE)
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Main.java").write_text("class Main {}")
    result = validate_project_structure(tmp_path)
    assert result["warnings"] == []
    assert result["fatal_error"] is None


def test_validate_project_structure_flags_missing_files_non_fatally(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Main.java").write_text("class Main {}")
    result = validate_project_structure(tmp_path)
    assert "Missing build.gradle" in result["warnings"]
    assert "Missing AndroidManifest.xml" in result["warnings"]
    assert result["fatal_error"] is None


def test_validate_project_structure_fatal_when_no_source(tmp_path: Path):
    (tmp_path / "build.gradle").write_text(GROOVY_GRADLE)
    result = validate_project_structure(tmp_path)
    assert result["fatal_error"] == "No source files found (.java/.kt)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_android_analyzer_gradle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.android_analyzer'`

- [ ] **Step 3: Implement the gradle parsing and structure validation portion of android_analyzer.py**

`backend/app/analyzer/android_analyzer.py`:
```python
import re
from pathlib import Path
from typing import Optional

_COMPILE_SDK_RE = re.compile(r'compileSdk(?:Version)?\s*[= ]\s*(\d+)')
_TARGET_SDK_RE = re.compile(r'targetSdk(?:Version)?\s*[= ]\s*(\d+)')


def _extract_gradle_version(content: str) -> Optional[str]:
    match = re.search(r'com\.android\.tools\.build:gradle:([0-9.]+)', content)
    if match:
        return match.group(1)
    match = re.search(r'com\.android\.(?:application|library)"\)?\s*version\s*"([0-9.]+)"', content)
    if match:
        return match.group(1)
    return None


def _extract_kotlin_version(content: str) -> Optional[str]:
    match = re.search(r'kotlin_version\s*=\s*[\'"]([0-9.]+)[\'"]', content, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'kotlin\.android"\)?\s*version\s*"([0-9.]+)"', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_gradle(content: str) -> dict:
    compile_sdk_match = _COMPILE_SDK_RE.search(content)
    target_sdk_match = _TARGET_SDK_RE.search(content)
    dependency_re = re.compile(
        r'(?:implementation|api|testImplementation|androidTestImplementation)\s*[\("\']\s*["\']?'
        r'([a-zA-Z0-9_.\-]+:[a-zA-Z0-9_.\-]+:[a-zA-Z0-9_.\-]+)'
    )
    return {
        "compile_sdk": int(compile_sdk_match.group(1)) if compile_sdk_match else None,
        "target_sdk": int(target_sdk_match.group(1)) if target_sdk_match else None,
        "gradle_version": _extract_gradle_version(content),
        "kotlin_version": _extract_kotlin_version(content),
        "dependencies": dependency_re.findall(content),
        "has_jacoco": "jacoco" in content.lower(),
        "has_kover": "kover" in content.lower(),
    }


def find_gradle_file(project_dir: Path) -> Optional[Path]:
    project_dir = Path(project_dir)
    candidates = list(project_dir.rglob("build.gradle")) + list(project_dir.rglob("build.gradle.kts"))
    app_candidates = [c for c in candidates if c.parent.name == "app"]
    if app_candidates:
        return app_candidates[0]
    return candidates[0] if candidates else None


def validate_project_structure(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    warnings = []

    if find_gradle_file(project_dir) is None:
        warnings.append("Missing build.gradle")

    if not any(project_dir.rglob("AndroidManifest.xml")):
        warnings.append("Missing AndroidManifest.xml")

    has_source = any(project_dir.rglob("*.java")) or any(project_dir.rglob("*.kt"))
    fatal_error = None if has_source else "No source files found (.java/.kt)"

    return {"warnings": warnings, "fatal_error": fatal_error}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_android_analyzer_gradle.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/android_analyzer.py backend/tests/test_android_analyzer_gradle.py
git commit -m "feat: add gradle parsing and project structure validation"
```

---

### Task 5: Source file stats and test coverage detection

**Files:**
- Modify: `backend/app/analyzer/android_analyzer.py` (append to the file created in Task 4)
- Test: `backend/tests/test_android_analyzer_source.py`

**Interfaces:**
- Consumes: `find_gradle_file` (Task 4, same module — used internally is not required here, coverage detection takes `gradle_info` as a parameter).
- Produces:
  - `count_source_files(project_dir: Path) -> dict` with keys `java_count`, `kotlin_count`, `test_file_count` — consumed by Task 6.
  - `detect_test_coverage(project_dir: Path, gradle_info: dict) -> float | None` — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_android_analyzer_source.py`:
```python
from pathlib import Path

from app.analyzer.android_analyzer import count_source_files, detect_test_coverage

JACOCO_REPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="INSTRUCTION" missed="20" covered="80"/>
    <counter type="LINE" missed="10" covered="40"/>
</report>
"""


def test_count_source_files_counts_and_flags_tests(tmp_path: Path):
    main_dir = tmp_path / "src" / "main" / "java"
    main_dir.mkdir(parents=True)
    (main_dir / "MainActivity.java").write_text("class MainActivity {}")
    (main_dir / "Util.kt").write_text("class Util")
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "MainActivityTest.java").write_text("class MainActivityTest {}")

    stats = count_source_files(tmp_path)
    assert stats["java_count"] == 2
    assert stats["kotlin_count"] == 1
    assert stats["test_file_count"] == 1


def test_detect_test_coverage_returns_none_without_jacoco_or_kover(tmp_path: Path):
    gradle_info = {"has_jacoco": False, "has_kover": False}
    assert detect_test_coverage(tmp_path, gradle_info) is None


def test_detect_test_coverage_parses_jacoco_report(tmp_path: Path):
    report_dir = tmp_path / "build" / "reports" / "jacoco"
    report_dir.mkdir(parents=True)
    (report_dir / "jacocoTestReport.xml").write_text(JACOCO_REPORT_XML)
    gradle_info = {"has_jacoco": True, "has_kover": False}
    coverage = detect_test_coverage(tmp_path, gradle_info)
    assert coverage == 80.0


def test_detect_test_coverage_none_when_report_missing(tmp_path: Path):
    gradle_info = {"has_jacoco": True, "has_kover": False}
    assert detect_test_coverage(tmp_path, gradle_info) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_android_analyzer_source.py -v`
Expected: FAIL with `ImportError: cannot import name 'count_source_files'`

- [ ] **Step 3: Append source stats and coverage detection to android_analyzer.py**

Add to `backend/app/analyzer/android_analyzer.py` (below the code from Task 4):
```python
import xml.etree.ElementTree as ET


def count_source_files(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    java_files = list(project_dir.rglob("*.java"))
    kotlin_files = list(project_dir.rglob("*.kt"))
    all_files = java_files + kotlin_files
    test_files = [
        f for f in all_files
        if any("test" in part.lower() for part in f.parts) or f.stem.endswith("Test")
    ]
    return {
        "java_count": len(java_files),
        "kotlin_count": len(kotlin_files),
        "test_file_count": len(test_files),
    }


def _parse_jacoco_xml(report_path: Path) -> Optional[float]:
    try:
        tree = ET.parse(report_path)
    except ET.ParseError:
        return None
    root = tree.getroot()
    for counter in root.findall("counter"):
        if counter.get("type") == "INSTRUCTION":
            missed = int(counter.get("missed", "0"))
            covered = int(counter.get("covered", "0"))
            total = missed + covered
            if total == 0:
                return None
            return round(covered / total * 100, 1)
    return None


def detect_test_coverage(project_dir: Path, gradle_info: dict) -> Optional[float]:
    if not (gradle_info.get("has_jacoco") or gradle_info.get("has_kover")):
        return None
    project_dir = Path(project_dir)
    for report_path in project_dir.rglob("*.xml"):
        if "jacoco" in report_path.name.lower():
            coverage = _parse_jacoco_xml(report_path)
            if coverage is not None:
                return coverage
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_android_analyzer_source.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/android_analyzer.py backend/tests/test_android_analyzer_source.py
git commit -m "feat: add source file stats and JaCoCo coverage detection"
```

---

### Task 6: analyze_project orchestrator

**Files:**
- Modify: `backend/app/analyzer/android_analyzer.py` (append)
- Test: `backend/tests/test_android_analyzer_orchestrator.py`

**Interfaces:**
- Consumes: `parse_gradle`, `find_gradle_file`, `validate_project_structure`, `count_source_files`, `detect_test_coverage` (Task 4/5, same module); `compare_versions` (Task 2); `scan_directory` (Task 3).
- Produces: `AnalysisResult` dataclass with fields `gradle_info: dict`, `structure_warnings: list[str]`, `fatal_error: str | None`, `source_stats: dict`, `test_coverage: float | None`, `version_warnings: list[dict]`, `secrets_found: list[dict]`, and `analyze_project(project_dir: Path) -> AnalysisResult` — consumed by Task 9 (`_run_review`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_android_analyzer_orchestrator.py`:
```python
from pathlib import Path

from app.analyzer.android_analyzer import analyze_project


def _build_minimal_project(tmp_path: Path) -> Path:
    (tmp_path / "build.gradle").write_text(
        "android { compileSdkVersion 30\n defaultConfig { targetSdkVersion 30 } }\n"
        "dependencies { implementation 'androidx.core:core-ktx:1.9.0' }\n"
    )
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Constants.java").write_text(
        'class Constants { static final String API_KEY = "ab12cd34ef56gh78ij90kl12mn34op56"; }'
    )
    return tmp_path


def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.gradle_info["compile_sdk"] == 30
    assert result.source_stats["java_count"] == 1
    assert result.test_coverage is None
    assert any("compileSdkVersion 30" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("android {}")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.java/.kt)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_android_analyzer_orchestrator.py -v`
Expected: FAIL with `ImportError: cannot import name 'analyze_project'`

- [ ] **Step 3: Append the orchestrator to android_analyzer.py**

Add to `backend/app/analyzer/android_analyzer.py` (below the code from Task 5), and add the two new imports at the top of the file alongside the existing `re`/`Path`/`Optional`/`ET` imports:
```python
from dataclasses import dataclass

from app.analyzer.secrets_scanner import scan_directory
from app.analyzer.version_checker import compare_versions


@dataclass
class AnalysisResult:
    gradle_info: dict
    structure_warnings: list
    fatal_error: Optional[str]
    source_stats: dict
    test_coverage: Optional[float]
    version_warnings: list
    secrets_found: list


def analyze_project(project_dir: Path) -> AnalysisResult:
    project_dir = Path(project_dir)
    structure = validate_project_structure(project_dir)

    gradle_path = find_gradle_file(project_dir)
    gradle_content = gradle_path.read_text(encoding="utf-8", errors="ignore") if gradle_path else ""
    gradle_info = parse_gradle(gradle_content)

    source_stats = count_source_files(project_dir)
    test_coverage = detect_test_coverage(project_dir, gradle_info)
    version_warnings = compare_versions(gradle_info)
    secrets_found = scan_directory(project_dir)

    return AnalysisResult(
        gradle_info=gradle_info,
        structure_warnings=structure["warnings"],
        fatal_error=structure["fatal_error"],
        source_stats=source_stats,
        test_coverage=test_coverage,
        version_warnings=version_warnings,
        secrets_found=secrets_found,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_android_analyzer_orchestrator.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full analyzer test suite to check nothing regressed**

Run: `cd backend && python -m pytest tests/test_android_analyzer_gradle.py tests/test_android_analyzer_source.py tests/test_android_analyzer_orchestrator.py -v`
Expected: PASS (13 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/analyzer/android_analyzer.py backend/tests/test_android_analyzer_orchestrator.py
git commit -m "feat: add analyze_project orchestrator tying analyzer modules together"
```

---

### Task 7: Excel handler

**Files:**
- Create: `backend/app/analyzer/excel_handler.py`
- Test: `backend/tests/test_excel_handler.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `aggregate_category_scores(sub_scores: dict) -> dict` returning `{"avg_points", "final_points", "percent_points", "sub_scores"}` — consumed by Task 9.
  - `populate_scores(template_path: Path, output_path: Path, category_results: dict) -> None`, where `category_results` is keyed by category id (`"1"`..`"6"`) with values shaped like `aggregate_category_scores`'s return — consumed by Task 9.

**Excel row model:** row 1 is headers. Data rows are either a *category row* (id column holds `"1"`, `"2"`, `"3"`, `"4"`, or `"6"`) carrying `Avg Points`/`Final Points`/`% Points`, or a *sub-criterion row* (id column holds `"1.1"`, `"2.3"`, etc.) carrying `Score`/`Remarks`. Header text is matched case-insensitively against these aliases: `id`→["category","sub-criterion","criterion"], `avg_points`→["avg points","average points"], `final_points`→["final points"], `percent_points`→["% points","percent points"], `score`→["score"], `remarks`→["remarks"].

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_excel_handler.py`:
```python
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.analyzer.excel_handler import aggregate_category_scores, populate_scores


def _build_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    headers = ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    ws.append(["1", "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.append(["1.1", "Clear and consistent naming", None, None, None, None, None])
    ws.append(["1.2", "Clean structure and formatting", None, None, None, None, None])
    wb.save(path)


def test_aggregate_category_scores_computes_mean_and_percent():
    sub_scores = {
        "1.1": {"score": 1, "remark": "Good naming"},
        "1.2": {"score": 0.5, "remark": "Some issues"},
    }
    result = aggregate_category_scores(sub_scores)
    assert result["avg_points"] == 0.75
    assert result["final_points"] == 0.75
    assert result["percent_points"] == 75.0
    assert result["sub_scores"] == sub_scores


def test_aggregate_category_scores_all_none_stays_none():
    sub_scores = {"1.1": {"score": None, "remark": ""}}
    result = aggregate_category_scores(sub_scores)
    assert result["avg_points"] is None
    assert result["final_points"] is None
    assert result["percent_points"] is None


def test_populate_scores_writes_values_and_preserves_formatting(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "output.xlsx"
    _build_template(template_path)

    category_results = {
        "1": aggregate_category_scores(
            {
                "1.1": {"score": 1, "remark": "Good naming"},
                "1.2": {"score": 0.5, "remark": "Some issues"},
            }
        )
    }
    populate_scores(template_path, output_path, category_results)

    wb = load_workbook(output_path)
    ws = wb.active

    header_row = [c.value for c in ws[1]]
    assert header_row == ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    assert ws["A1"].font.bold is True

    category_row = ws[2]
    assert category_row[3].value == 0.75
    assert category_row[4].value == 0.75
    assert category_row[5].value == 75.0

    sub_row_1_1 = ws[3]
    assert sub_row_1_1[2].value == 1
    assert sub_row_1_1[6].value == "Good naming"

    sub_row_1_2 = ws[4]
    assert sub_row_1_2[2].value == 0.5
    assert sub_row_1_2[6].value == "Some issues"


def test_populate_scores_raises_on_missing_columns(tmp_path: Path):
    template_path = tmp_path / "bad_template.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description"])
    wb.save(template_path)

    output_path = tmp_path / "output.xlsx"
    try:
        populate_scores(template_path, output_path, {})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing" in str(exc).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_excel_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.excel_handler'`

- [ ] **Step 3: Implement excel_handler.py**

`backend/app/analyzer/excel_handler.py`:
```python
from pathlib import Path

from openpyxl import load_workbook

HEADER_ALIASES = {
    "id": ["category", "sub-criterion", "sub criterion", "criterion"],
    "avg_points": ["avg points", "average points"],
    "final_points": ["final points"],
    "percent_points": ["% points", "percent points"],
    "score": ["score"],
    "remarks": ["remarks"],
}


def aggregate_category_scores(sub_scores: dict) -> dict:
    values = [v["score"] for v in sub_scores.values() if v.get("score") is not None]
    if not values:
        avg_points = final_points = percent_points = None
    else:
        avg_points = round(sum(values) / len(values), 2)
        final_points = avg_points
        percent_points = round(final_points * 100, 1)
    return {
        "avg_points": avg_points,
        "final_points": final_points,
        "percent_points": percent_points,
        "sub_scores": sub_scores,
    }


def _resolve_columns(ws) -> dict:
    columns = {}
    for cell in ws[1]:
        if cell.value is None:
            continue
        header_text = str(cell.value).strip().lower()
        for key, aliases in HEADER_ALIASES.items():
            if header_text in aliases:
                columns[key] = cell.column
    missing = [key for key in HEADER_ALIASES if key not in columns]
    if missing:
        raise ValueError(f"Excel template missing expected columns: {missing}")
    return columns


def populate_scores(template_path: Path, output_path: Path, category_results: dict) -> None:
    wb = load_workbook(template_path)
    ws = wb.active
    columns = _resolve_columns(ws)

    for row in ws.iter_rows(min_row=2):
        id_cell = row[columns["id"] - 1]
        if id_cell.value is None:
            continue
        row_id = str(id_cell.value).strip()
        row_idx = id_cell.row

        if row_id in category_results:
            cat = category_results[row_id]
            ws.cell(row=row_idx, column=columns["avg_points"]).value = cat["avg_points"]
            ws.cell(row=row_idx, column=columns["final_points"]).value = cat["final_points"]
            ws.cell(row=row_idx, column=columns["percent_points"]).value = cat["percent_points"]
            continue

        for cat in category_results.values():
            sub = cat["sub_scores"].get(row_id)
            if sub is not None:
                ws.cell(row=row_idx, column=columns["score"]).value = sub.get("score")
                ws.cell(row=row_idx, column=columns["remarks"]).value = sub.get("remark")
                break

    wb.save(output_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_excel_handler.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/excel_handler.py backend/tests/test_excel_handler.py
git commit -m "feat: add Excel handler with dynamic column resolution"
```

---

### Task 8: Azure OpenAI client (with stub mode)

**Files:**
- Modify: `backend/app/analyzer/openai_client.py` (replace the Task 1 placeholder with the full implementation)
- Test: `backend/tests/test_openai_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_stub_mode() -> bool` (already used by Task 1's `main.py`); `async score_category(category_name: str, sub_criteria: list[str], code_snippets: str) -> dict[str, dict]` where each value is `{"score": float | None, "remark": str}` — consumed by Task 9.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_openai_client.py`:
```python
import httpx
import pytest

from app.analyzer import openai_client


@pytest.mark.asyncio
async def test_stub_mode_returns_placeholder_scores(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    result = await openai_client.score_category("Code Structure", ["1.1", "1.2"], "code here")
    assert set(result.keys()) == {"1.1", "1.2"}
    for sub in result.values():
        assert sub["score"] == 1
        assert sub["remark"].startswith("[STUB]")


@pytest.mark.asyncio
async def test_live_mode_calls_azure_endpoint_and_parses_response(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "Well named"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await openai_client.score_category("Code Structure", ["1.1"], "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}
    assert captured["headers"]["api-key"] == "test-key"
    assert "gpt-4o-mini" in captured["url"]
    assert captured["json"]["temperature"] == 0.3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_openai_client.py -v`
Expected: FAIL — `test_stub_mode_returns_placeholder_scores` fails with `AttributeError: module 'app.analyzer.openai_client' has no attribute 'score_category'`

- [ ] **Step 3: Implement the full openai_client.py**

`backend/app/analyzer/openai_client.py`:
```python
import asyncio
import json
import os

import httpx

STUB_PREFIX = "[STUB]"


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")


async def score_category(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    if is_stub_mode():
        return _stub_score(sub_criteria)
    return await _live_score(category_name, sub_criteria, code_snippets)


def _stub_score(sub_criteria: list) -> dict:
    return {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }


async def _live_score(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    api_base = os.environ["OPENAI_API_BASE"].rstrip("/")
    deployment = os.environ["OPENAI_DEPLOYMENT_NAME"]
    api_version = os.environ["OPENAI_API_VERSION"]
    url = f"{api_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    headers = {"api-key": os.environ["AZURE_OPENAI_KEY"], "Content-Type": "application/json"}
    system_prompt = (
        f"You are an expert Android code reviewer. Score {category_name} sub-criteria "
        f"{', '.join(sub_criteria)} on a scale of 0, 0.5, 1, or null if you cannot evaluate. "
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": code_snippets},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }

    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = None
        for attempt in range(3):
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            break
        if response is None or response.status_code == 429:
            return fallback
        response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except ValueError:
        return fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_openai_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the health test to confirm the Task 1 placeholder swap didn't break it**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/analyzer/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: add Azure OpenAI scoring client with stub mode"
```

---

### Task 9: POST /api/reviews and background review pipeline

**Files:**
- Create: `backend/app/api/reviews.py`
- Modify: `backend/main.py` (register the router)
- Test: `backend/tests/test_reviews_create.py`

**Interfaces:**
- Consumes: `analyze_project` (Task 6), `aggregate_category_scores`/`populate_scores` (Task 7), `score_category` (Task 8).
- Produces: `router` (FastAPI `APIRouter`), module-level `_reviews: dict` review-state store, `CATEGORIES` constant — consumed by Tasks 10, 11, 12. State dict shape: `{"status": "processing"|"completed"|"error", "phase": str, "progress": int, "message": str, "stats": dict, "download_path": str|None, "error": str|None}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reviews_create.py`:
```python
import io
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.reviews import _reviews
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("build.gradle", "android { compileSdkVersion 34 }")
        zf.writestr("AndroidManifest.xml", "<manifest />")
        zf.writestr("src/main/java/Main.java", "class Main {}")
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"])
    wb.save(buffer)
    return buffer.getvalue()


def test_create_review_returns_id_and_creates_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "processing"
        assert body["review_id"] in _reviews
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reviews_create.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.reviews'`

- [ ] **Step 3: Implement app/api/reviews.py**

`backend/app/api/reviews.py`:
```python
import asyncio
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.analyzer.android_analyzer import analyze_project
from app.analyzer.excel_handler import aggregate_category_scores, populate_scores
from app.analyzer.openai_client import score_category
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

CATEGORIES = {
    "1": {"name": "Code naming conventions / Code Structure", "sub_criteria": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]},
    "2": {"name": "Reliability, Security & Observability", "sub_criteria": ["2.1", "2.2", "2.3", "2.4"]},
    "3": {"name": "Delivery Discipline & Architecture", "sub_criteria": ["3.1", "3.2", "3.3", "3.4"]},
    "4": {"name": "AI Usage & Code Ownership", "sub_criteria": ["4.1", "4.2", "4.3"]},
    "6": {"name": "Safe & Integrated AI Code", "sub_criteria": ["6.1", "6.2", "6.3"]},
}

_reviews: dict = {}


def _new_review_state() -> dict:
    return {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
    }


@router.post("/api/reviews")
async def create_review(androidZip: UploadFile = File(...), excelTemplate: UploadFile = File(...)):
    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(await androidZip.read())
    template_path.write_bytes(await excelTemplate.read())

    zip_valid = (androidZip.filename or "").endswith(".zip")
    template_valid = (excelTemplate.filename or "").endswith(".xlsx")

    _reviews[review_id] = _new_review_state()
    asyncio.create_task(_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid))
    return {"review_id": review_id, "status": "processing"}


async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
) -> None:
    state = _reviews[review_id]
    extract_dir = work_dir / "extracted"
    stats = {}
    try:
        if not zip_valid or not template_valid:
            state["status"] = "error"
            state["phase"] = "error"
            state["error"] = "androidZip must be a .zip file and excelTemplate must be a .xlsx file"
            return

        t0 = time.monotonic()
        state["phase"] = "extracting"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        stats["ingest_time_ms"] = int((time.monotonic() - t0) * 1000)
        state["progress"] = 20

        t1 = time.monotonic()
        state["phase"] = "analyzing"
        analysis = analyze_project(extract_dir)
        if analysis.fatal_error:
            state["status"] = "error"
            state["phase"] = "error"
            state["error"] = analysis.fatal_error
            return
        state["warnings"] = analysis.structure_warnings + [w["issue"] for w in analysis.version_warnings]
        state["test_coverage"] = analysis.test_coverage
        state["secrets_found"] = analysis.secrets_found
        stats["analysis_time_ms"] = int((time.monotonic() - t1) * 1000)
        state["progress"] = 50

        t2 = time.monotonic()
        state["phase"] = "scoring"
        scores_by_category = {}
        for category_id, category in CATEGORIES.items():
            sub_results = await score_category(category["name"], category["sub_criteria"], "")
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
        stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)
        state["progress"] = 80

        t3 = time.monotonic()
        state["phase"] = "generating"
        output_path = work_dir / "output.xlsx"
        populate_scores(template_path, output_path, scores_by_category)
        stats["generation_time_ms"] = int((time.monotonic() - t3) * 1000)
        stats["total_time_ms"] = sum(stats.values())

        state["status"] = "completed"
        state["phase"] = "completed"
        state["progress"] = 100
        state["message"] = "Review complete"
        state["stats"] = stats
        state["download_path"] = str(output_path)
    except Exception as exc:
        logger.exception("Review %s failed", review_id)
        state["status"] = "error"
        state["phase"] = "error"
        state["error"] = str(exc)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        template_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Register the router in main.py**

Replace the contents of `backend/main.py` with:
```python
from fastapi import FastAPI

from app.analyzer.openai_client import is_stub_mode
from app.api.reviews import router as reviews_router

app = FastAPI(title="Android Code Review Automation")
app.include_router(reviews_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_reviews_create.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `cd backend && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/reviews.py backend/main.py backend/tests/test_reviews_create.py
git commit -m "feat: add POST /api/reviews with background review pipeline"
```

---

### Task 10: GET /api/reviews/{id}/progress

**Files:**
- Modify: `backend/app/api/reviews.py` (append endpoint)
- Test: `backend/tests/test_reviews_progress.py`

**Interfaces:**
- Consumes: `_reviews` store (Task 9, same module).
- Produces: `GET /api/reviews/{review_id}/progress` route. Response includes the Smart Detection findings (`warnings`, `test_coverage`, `secrets_found`) that `analyze_project` (Task 6) computes but that Task 9 would otherwise compute and discard.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_reviews_progress.py`:
```python
from fastapi.testclient import TestClient

from app.api.reviews import _reviews
from main import app

client = TestClient(app)


def test_progress_returns_404_for_unknown_id():
    response = client.get("/api/reviews/does-not-exist/progress")
    assert response.status_code == 404


def test_progress_reflects_stored_state():
    _reviews["fixed-id"] = {
        "status": "processing",
        "phase": "scoring",
        "progress": 60,
        "message": "Scoring category 2",
        "stats": {"ingest_time_ms": 120},
        "download_path": None,
        "error": None,
        "warnings": ["Missing AndroidManifest.xml"],
        "test_coverage": 82.5,
        "secrets_found": [{"file": "Constants.java", "line": 42, "pattern": "api_key"}],
    }
    response = client.get("/api/reviews/fixed-id/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["phase"] == "scoring"
    assert body["progress"] == 60
    assert body["download_url"] is None
    assert body["error"] is None
    assert body["warnings"] == ["Missing AndroidManifest.xml"]
    assert body["test_coverage"] == 82.5
    assert body["secrets_found"] == [{"file": "Constants.java", "line": 42, "pattern": "api_key"}]


def test_progress_defaults_detection_fields_when_absent():
    _reviews["legacy-id"] = {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
    }
    response = client.get("/api/reviews/legacy-id/progress")
    body = response.json()
    assert body["warnings"] == []
    assert body["test_coverage"] is None
    assert body["secrets_found"] == []


def test_progress_includes_download_url_when_completed():
    _reviews["done-id"] = {
        "status": "completed",
        "phase": "completed",
        "progress": 100,
        "message": "Review complete",
        "stats": {"total_time_ms": 500},
        "download_path": "/tmp/whatever/output.xlsx",
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
    }
    response = client.get("/api/reviews/done-id/progress")
    body = response.json()
    assert body["download_url"] == "/api/reviews/done-id/download"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_progress.py -v`
Expected: FAIL with 404 on all requests (`test_progress_returns_404_for_unknown_id` passes accidentally, the other two fail with 404 instead of 200)

- [ ] **Step 3: Append the progress endpoint**

Add to `backend/app/api/reviews.py` (below `_run_review`), with a new import at the top: `from fastapi import HTTPException` (add `HTTPException` to the existing `from fastapi import APIRouter, File, UploadFile` line):
```python
@router.get("/api/reviews/{review_id}/progress")
async def get_progress(review_id: str):
    state = _reviews.get(review_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown review_id")
    return {
        "status": state["status"],
        "phase": state["phase"],
        "progress": state["progress"],
        "message": state["message"],
        "stats": state["stats"],
        "download_url": f"/api/reviews/{review_id}/download" if state["status"] == "completed" else None,
        "error": state["error"],
        "warnings": state.get("warnings", []),
        "test_coverage": state.get("test_coverage"),
        "secrets_found": state.get("secrets_found", []),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reviews_progress.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_progress.py
git commit -m "feat: add GET /api/reviews/{id}/progress"
```

---

### Task 11: GET /api/reviews/{id}/download

**Files:**
- Modify: `backend/app/api/reviews.py` (append endpoint)
- Test: `backend/tests/test_reviews_download.py`

**Interfaces:**
- Consumes: `_reviews` store (Task 9, same module).
- Produces: `GET /api/reviews/{review_id}/download` route.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_reviews_download.py`:
```python
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.reviews import _reviews
from main import app

client = TestClient(app)


def test_download_returns_404_when_no_result():
    response = client.get("/api/reviews/no-such-review/download")
    assert response.status_code == 404


def test_download_returns_file_and_deletes_it_after(tmp_path: Path):
    output_file = tmp_path / "output.xlsx"
    output_file.write_bytes(b"fake xlsx bytes")
    _reviews["download-ready"] = {
        "status": "completed",
        "phase": "completed",
        "progress": 100,
        "message": "Review complete",
        "stats": {},
        "download_path": str(output_file),
        "error": None,
    }

    response = client.get("/api/reviews/download-ready/download")
    assert response.status_code == 200
    assert response.content == b"fake xlsx bytes"
    assert not output_file.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reviews_download.py -v`
Expected: FAIL — both requests return 404 (route doesn't exist yet, so the second assertion never gets there / first test also 404 but for the wrong reason until the route exists — run to confirm no 200 responses occur)

- [ ] **Step 3: Append the download endpoint**

Add to `backend/app/api/reviews.py` (below `get_progress`), adding two new imports at the top of the file: `from fastapi.responses import FileResponse` and `from starlette.background import BackgroundTask`:
```python
@router.get("/api/reviews/{review_id}/download")
async def download_review(review_id: str):
    state = _reviews.get(review_id)
    if state is None or state["download_path"] is None:
        raise HTTPException(status_code=404, detail="Result not available")
    path = Path(state["download_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result already downloaded or expired")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="review_result.xlsx",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reviews_download.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_download.py
git commit -m "feat: add GET /api/reviews/{id}/download with post-download cleanup"
```

---

### Task 12: End-to-end integration test

**Files:**
- Test: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: the full `POST /api/reviews` → `GET .../progress` → `GET .../download` flow (Tasks 9-11).
- Produces: nothing new — this task only adds a test that exercises the whole backend pipeline in stub mode.

- [ ] **Step 1: Write the integration test**

`backend/tests/test_reviews_integration.py`:
```python
import io
import time
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from main import app

JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="INSTRUCTION" missed="10" covered="90"/>
</report>
"""


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "app/build.gradle",
            "apply plugin: 'jacoco'\n"
            "android { compileSdkVersion 34\n defaultConfig { targetSdkVersion 34 } }\n",
        )
        zf.writestr("AndroidManifest.xml", "<manifest />")
        zf.writestr("src/main/java/com/example/MainActivity.java", "class MainActivity {}")
        zf.writestr("build/reports/jacoco/jacocoTestReport.xml", JACOCO_XML)
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append(["1", "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.append(["1.1", "Clear and consistent naming", None, None, None, None, None])
    ws.append(["2", "Reliability, Security & Observability", None, None, None, None, None])
    ws.append(["2.1", "Proper exception handling", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


def test_full_review_pipeline_in_stub_mode(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx",
                    _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert create_response.status_code == 200
        review_id = create_response.json()["review_id"]

        final_state = None
        for _ in range(50):
            progress_response = client.get(f"/api/reviews/{review_id}/progress")
            body = progress_response.json()
            if body["status"] in ("completed", "error"):
                final_state = body
                break
            time.sleep(0.05)

        assert final_state is not None, "review did not finish in time"
        assert final_state["status"] == "completed"
        assert final_state["download_url"] == f"/api/reviews/{review_id}/download"
        assert "total_time_ms" in final_state["stats"]
        assert final_state["test_coverage"] == 90.0
        assert final_state["secrets_found"] == []
        assert final_state["warnings"] == []

        download_response = client.get(final_state["download_url"])
        assert download_response.status_code == 200

        workbook = load_workbook(io.BytesIO(download_response.content))
        ws = workbook.active
        category_1_row = ws[2]
        assert category_1_row[3].value == 1
        sub_1_1_row = ws[3]
        assert sub_1_1_row[2].value == 1
        assert sub_1_1_row[6].value.startswith("[STUB]")
```

- [ ] **Step 2: Run the test**

Run: `cd backend && python -m pytest tests/test_reviews_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run the entire backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: All tests PASS (35 tests across all files)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_reviews_integration.py
git commit -m "test: add end-to-end review pipeline integration test"
```

---

### Task 13: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: `backend/requirements.txt` (Task 1), `backend/main.py` (Task 9).
- Produces: a buildable Docker image for the backend service — consumed by the frontend/Docker-Compose plan (next plan).

- [ ] **Step 1: Write the Dockerfile**

`backend/Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write .dockerignore**

`backend/.dockerignore`:
```
venv/
__pycache__/
*.pyc
.env
tests/
.pytest_cache/
```

- [ ] **Step 3: Build the image to verify the Dockerfile is correct**

Run: `docker build -t android-review-backend backend/`
Expected: Build completes successfully (exit code 0). If Docker is not installed/available in this environment, skip this verification step and note it as unverified.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "chore: add backend Dockerfile"
```
