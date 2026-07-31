# iOS Project Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the review pipeline a real iOS-aware analysis path (source detection, secrets scanning, version-freshness checks, test-coverage detection, LLM code-context gathering) so an iOS project can complete a review end to end instead of failing immediately with `"No source files found (.java/.kt)"`.

**Architecture:** A new `app/analyzer/ios_analyzer.py` module, structurally parallel to `android_analyzer.py`, sharing an `AnalysisResult` dataclass extracted into a new `app/analyzer/analysis_result.py`. `reviews.py` picks `ios_analyzer` vs `android_analyzer` with a simple `platform == "iOS"` conditional — the same style already used for compile-check gating. `secrets_scanner.py`'s extension allowlist is broadened since it's one shared, platform-agnostic scanner.

**Tech Stack:** Python 3.11, pytest (`asyncio_mode = auto`), regex-based text parsing (matches the existing `parse_gradle` approach — no XML/plist parser needed since `project.pbxproj` is old-style ASCII plist, not something `plistlib` can read).

## Global Constraints

- Every existing Android test must keep passing unchanged — zero behavior change for `platform="Android"` or the default.
- No class-based analyzer interface — `ios_analyzer.py` stays a plain function module, matching every other file in `app/analyzer/`.
- Version extraction reads only `project.pbxproj` (via regex, same simple-text-search style as `parse_gradle`). A pure Swift Package Manager project with no `project.pbxproj` gets zero version warnings — the same graceful fallback Android already has for a missing `build.gradle`.
- Test coverage is read only from a committed LCOV-format report (`lcov.info` or similar `*.info` file with `SF:`/`LF:` markers) — no `.xcresult` parsing, since that needs the Xcode toolchain, which won't exist in this Linux container.
- `AnalysisResult`'s `gradle_info` field is renamed to `build_info` (generic — shared by both platforms). This field is not read by `reviews.py` (only `.fatal_error`, `.structure_warnings`, `.test_coverage`, `.version_warnings`, `.secrets_found` cross that boundary), but it **is** read directly by two existing tests in `test_android_analyzer_orchestrator.py` — those two assertions must be updated to `result.build_info` as part of this rename.

---

## Task 1: Extract `AnalysisResult` into its own module, rename `gradle_info` → `build_info`

**Files:**
- Create: `backend/app/analyzer/analysis_result.py`
- Modify: `backend/app/analyzer/android_analyzer.py:1-9` (imports), `:122-124` (dataclass removal), `:133-157` (`analyze_project` body)
- Modify: `backend/tests/test_android_analyzer_orchestrator.py:25`, `:55-58`

**Interfaces:**
- Produces: `AnalysisResult` dataclass with fields `build_info: dict`, `structure_warnings: list`, `fatal_error: Optional[str]`, `source_stats: dict`, `test_coverage: Optional[float]`, `version_warnings: list`, `secrets_found: list` — importable from `app.analyzer.analysis_result`.

- [ ] **Step 1: Write the failing test**

Update `backend/tests/test_android_analyzer_orchestrator.py`'s two `result.gradle_info[...]` assertion blocks to use `result.build_info` instead:

```python
def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.build_info["compile_sdk"] == 30
    assert result.source_stats["java_count"] == 1
    assert result.test_coverage is None
    assert any("compileSdkVersion 30" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("android {}")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.java/.kt)"


def test_analyze_project_handles_directory_named_build_gradle(tmp_path: Path):
    """Test that a directory literally named build.gradle doesn't crash analyze_project."""
    # Create a directory named build.gradle (will be found by rglob but can't be read as a file)
    (tmp_path / "build.gradle").mkdir()
    # Add required files
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Main.java").write_text("class Main {}")

    # This should not raise IsADirectoryError; should degrade gracefully
    result = analyze_project(tmp_path)

    # Should complete without error
    assert result is not None
    assert result.fatal_error is None
    # build_info should have empty values since the gradle_content was empty
    assert result.build_info["compile_sdk"] is None
    assert result.build_info["target_sdk"] is None
    assert result.build_info["gradle_version"] is None
    assert result.build_info["kotlin_version"] is None
    assert result.build_info["dependencies"] == []
```

(Only the `.gradle_info` → `.build_info` renames changed; everything else in the file is untouched.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/python -m pytest tests/test_android_analyzer_orchestrator.py -v`
Expected: FAIL — `AttributeError: 'AnalysisResult' object has no attribute 'build_info'` (the dataclass still only has `gradle_info` at this point).

- [ ] **Step 3: Write the implementation**

Create `backend/app/analyzer/analysis_result.py`:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalysisResult:
    build_info: dict
    structure_warnings: list
    fatal_error: Optional[str]
    source_stats: dict
    test_coverage: Optional[float]
    version_warnings: list
    secrets_found: list
```

In `backend/app/analyzer/android_analyzer.py`, replace the imports block (currently lines 1-8):

```python
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from app.analyzer.analysis_result import AnalysisResult
from app.analyzer.secrets_scanner import scan_directory
from app.analyzer.version_checker import compare_versions
```

(Drops the now-unused `from dataclasses import dataclass` import since the dataclass moved out.)

Remove the `@dataclass` / `class AnalysisResult` block (currently lines 122-130) entirely — it now lives in `analysis_result.py`.

Replace `analyze_project`'s body (currently lines 133-157) with the renamed local variable:

```python
def analyze_project(project_dir: Path) -> AnalysisResult:
    project_dir = Path(project_dir)
    structure = validate_project_structure(project_dir)

    gradle_path = find_gradle_file(project_dir)
    try:
        gradle_content = gradle_path.read_text(encoding="utf-8", errors="ignore") if gradle_path else ""
    except OSError:
        gradle_content = ""
    build_info = parse_gradle(gradle_content)

    source_stats = count_source_files(project_dir)
    test_coverage = detect_test_coverage(project_dir, build_info)
    version_warnings = compare_versions(build_info)
    secrets_found = scan_directory(project_dir)

    return AnalysisResult(
        build_info=build_info,
        structure_warnings=structure["warnings"],
        fatal_error=structure["fatal_error"],
        source_stats=source_stats,
        test_coverage=test_coverage,
        version_warnings=version_warnings,
        secrets_found=secrets_found,
    )
```

(`detect_test_coverage`'s own parameter is still named `gradle_info` internally — it's a private, Android-specific helper reading `has_jacoco`/`has_kover` keys, so its signature doesn't need to change. Only the local variable in `analyze_project` and the dataclass field are renamed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/python -m pytest tests/test_android_analyzer_orchestrator.py tests/test_android_analyzer_gradle.py tests/test_android_analyzer_source.py tests/test_android_analyzer_context.py -v`
Expected: PASS (all tests in all four Android analyzer test files)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/analysis_result.py backend/app/analyzer/android_analyzer.py backend/tests/test_android_analyzer_orchestrator.py
git commit -m "refactor: extract AnalysisResult into its own module, rename gradle_info to build_info"
```

---

## Task 2: `version_checker.py` — `compare_ios_versions`

**Files:**
- Modify: `backend/app/analyzer/version_checker.py`
- Test: `backend/tests/test_version_checker.py`

**Interfaces:**
- Consumes: `_parse_version_tuple` (already defined in this file, unchanged).
- Produces: `compare_ios_versions(build_info: dict) -> list`, each warning shaped `{"issue": str}` (same shape as `compare_versions`'s output).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_version_checker.py`:

```python
from app.analyzer.version_checker import compare_ios_versions, compare_versions


def test_ios_flags_outdated_versions():
    build_info = {"deployment_target": "14.0", "swift_version": "5.5"}
    warnings = compare_ios_versions(build_info)
    issues = [w["issue"] for w in warnings]
    assert any("deployment target 14.0" in i for i in issues)
    assert any("Swift version 5.5" in i for i in issues)
    assert len(warnings) == 2


def test_ios_no_warnings_when_up_to_date():
    build_info = {"deployment_target": "17.0", "swift_version": "5.9"}
    assert compare_ios_versions(build_info) == []


def test_ios_missing_values_are_skipped_not_flagged():
    build_info = {"deployment_target": None, "swift_version": None}
    assert compare_ios_versions(build_info) == []
```

(Update the existing `from app.analyzer.version_checker import compare_versions` line at the top of the file to also import `compare_ios_versions`, as shown above — replacing rather than duplicating the import line.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_version_checker.py -v`
Expected: FAIL with `ImportError: cannot import name 'compare_ios_versions'`

- [ ] **Step 3: Write the implementation**

Append to `backend/app/analyzer/version_checker.py`:

```python
IOS_LATEST_VERSIONS = {
    "deployment_target": (17, 0),
    "swift_version": (5, 9),
}


def compare_ios_versions(build_info: dict) -> list:
    warnings = []

    deployment_target = _parse_version_tuple(build_info.get("deployment_target"))
    if deployment_target is not None and deployment_target < IOS_LATEST_VERSIONS["deployment_target"]:
        warnings.append(
            {"issue": f"iOS deployment target {build_info.get('deployment_target')} is outdated, latest is 17.0+"}
        )

    swift_version = _parse_version_tuple(build_info.get("swift_version"))
    if swift_version is not None and swift_version < IOS_LATEST_VERSIONS["swift_version"]:
        warnings.append(
            {"issue": f"Swift version {build_info.get('swift_version')} is outdated, latest is 5.9+"}
        )

    return warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_version_checker.py -v`
Expected: PASS (all tests, including the pre-existing Android ones — unaffected)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/version_checker.py backend/tests/test_version_checker.py
git commit -m "feat: add compare_ios_versions for iOS deployment target/Swift version freshness checks"
```

---

## Task 3: `secrets_scanner.py` — broaden scan extensions

**Files:**
- Modify: `backend/app/analyzer/secrets_scanner.py:13`
- Test: `backend/tests/test_secrets_scanner.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SCAN_EXTENSIONS` now includes `.swift`, `.m`, `.h`, `.mm`, `.plist` alongside the existing Android extensions.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_secrets_scanner.py`:

```python
def test_finds_secret_in_swift_file(tmp_path: Path):
    swift_file = tmp_path / "Constants.swift"
    swift_file.write_text('let apiKey = "ab12cd34ef56gh78ij90kl12mn34op56"\n')
    findings = scan_directory(tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == str(swift_file)
    assert findings[0]["pattern"] == "api_key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/python -m pytest tests/test_secrets_scanner.py::test_finds_secret_in_swift_file -v`
Expected: FAIL — `assert len(findings) == 1` fails with `findings == []` (`.swift` isn't in `SCAN_EXTENSIONS` yet).

- [ ] **Step 3: Write the implementation**

In `backend/app/analyzer/secrets_scanner.py`, replace line 13:

```python
SCAN_EXTENSIONS = {".java", ".kt", ".xml", ".properties", ".gradle", ".kts", ".swift", ".m", ".h", ".mm", ".plist"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_secrets_scanner.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/secrets_scanner.py backend/tests/test_secrets_scanner.py
git commit -m "feat: scan Swift/Objective-C/plist files for secrets, not just Android extensions"
```

---

## Task 4: `ios_analyzer.py`

**Files:**
- Create: `backend/app/analyzer/ios_analyzer.py`
- Test: `backend/tests/test_ios_analyzer_project.py`
- Test: `backend/tests/test_ios_analyzer_source.py`
- Test: `backend/tests/test_ios_analyzer_orchestrator.py`
- Test: `backend/tests/test_ios_analyzer_context.py`

**Interfaces:**
- Consumes: `AnalysisResult` (Task 1), `compare_ios_versions` (Task 2), `scan_directory` from `secrets_scanner.py` (unchanged import, now scans the broadened extension set from Task 3).
- Produces: `find_project_config(project_dir) -> Path | None`, `parse_xcode_project(content: str) -> dict` (keys `deployment_target`, `swift_version`), `validate_project_structure(project_dir) -> dict` (keys `warnings`, `fatal_error`), `count_source_files(project_dir) -> dict` (keys `swift_count`, `objc_count`, `test_file_count`), `detect_test_coverage(project_dir) -> float | None`, `analyze_project(project_dir) -> AnalysisResult`, `gather_code_context(project_dir, max_chars=32000) -> str`. These four function names exactly match `android_analyzer.py`'s public surface so Task 5's dispatch can call either module interchangeably.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ios_analyzer_project.py`:

```python
from pathlib import Path

from app.analyzer.ios_analyzer import find_project_config, parse_xcode_project, validate_project_structure

PBXPROJ_CONTENT = """// !$*UTF8*$!
{
	archiveVersion = 1;
	objects = {
		ABC123 /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				IPHONEOS_DEPLOYMENT_TARGET = 15.0;
				SWIFT_VERSION = 5.0;
			};
			name = Debug;
		};
	};
}
"""


def test_parse_xcode_project_extracts_deployment_target_and_swift_version():
    info = parse_xcode_project(PBXPROJ_CONTENT)
    assert info["deployment_target"] == "15.0"
    assert info["swift_version"] == "5.0"


def test_parse_xcode_project_missing_fields_are_none():
    info = parse_xcode_project("{ archiveVersion = 1; }\n")
    assert info["deployment_target"] is None
    assert info["swift_version"] is None


def test_find_project_config_prefers_the_app_xcodeproj_over_a_nested_dependency(tmp_path: Path):
    pods_dir = tmp_path / "Pods" / "SomeDependency.xcodeproj"
    pods_dir.mkdir(parents=True)
    (pods_dir / "project.pbxproj").write_text("// dependency project")

    app_dir = tmp_path / "MyApp.xcodeproj"
    app_dir.mkdir()
    (app_dir / "project.pbxproj").write_text(PBXPROJ_CONTENT)

    found = find_project_config(tmp_path)
    assert found == app_dir / "project.pbxproj"


def test_find_project_config_returns_none_when_absent(tmp_path: Path):
    assert find_project_config(tmp_path) is None


def test_validate_project_structure_happy_path(tmp_path: Path):
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()
    (xcodeproj / "project.pbxproj").write_text(PBXPROJ_CONTENT)
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")

    result = validate_project_structure(tmp_path)
    assert result["warnings"] == []
    assert result["fatal_error"] is None


def test_validate_project_structure_flags_missing_files_non_fatally(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")

    result = validate_project_structure(tmp_path)
    assert "Missing Xcode project (.xcodeproj/.xcworkspace) or Package.swift" in result["warnings"]
    assert "Missing Info.plist" in result["warnings"]
    assert result["fatal_error"] is None


def test_validate_project_structure_accepts_package_swift_as_a_project_file(tmp_path: Path):
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9")
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "Lib.swift").write_text("struct Lib {}")

    result = validate_project_structure(tmp_path)
    assert "Missing Xcode project (.xcodeproj/.xcworkspace) or Package.swift" not in result["warnings"]


def test_validate_project_structure_fatal_when_no_source(tmp_path: Path):
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    result = validate_project_structure(tmp_path)
    assert result["fatal_error"] == "No source files found (.swift/.m/.mm)"
```

Create `backend/tests/test_ios_analyzer_source.py`:

```python
from pathlib import Path

from app.analyzer.ios_analyzer import count_source_files, detect_test_coverage

LCOV_REPORT = """TN:
SF:/project/Sources/File.swift
DA:1,1
DA:2,0
DA:3,1
LF:3
LH:2
end_of_record
SF:/project/Sources/Other.swift
DA:1,1
DA:2,1
LF:2
LH:2
end_of_record
"""


def test_count_source_files_counts_and_flags_tests(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")
    (src / "Legacy.m").write_text("@implementation Legacy @end")
    test_dir = tmp_path / "MyAppTests"
    test_dir.mkdir()
    (test_dir / "AppDelegateTests.swift").write_text("class AppDelegateTests {}")

    stats = count_source_files(tmp_path)
    assert stats["swift_count"] == 2
    assert stats["objc_count"] == 1
    assert stats["test_file_count"] == 1


def test_detect_test_coverage_returns_none_without_a_report(tmp_path: Path):
    assert detect_test_coverage(tmp_path) is None


def test_detect_test_coverage_parses_lcov_report(tmp_path: Path):
    (tmp_path / "lcov.info").write_text(LCOV_REPORT)
    coverage = detect_test_coverage(tmp_path)
    assert coverage == 80.0


def test_detect_test_coverage_ignores_unrelated_info_files(tmp_path: Path):
    (tmp_path / "notes.info").write_text("just some unrelated notes\n")
    assert detect_test_coverage(tmp_path) is None
```

Create `backend/tests/test_ios_analyzer_orchestrator.py`:

```python
from pathlib import Path

from app.analyzer.ios_analyzer import analyze_project


def _build_minimal_project(tmp_path: Path) -> Path:
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()
    (xcodeproj / "project.pbxproj").write_text(
        "buildSettings = { IPHONEOS_DEPLOYMENT_TARGET = 14.0; SWIFT_VERSION = 5.5; };"
    )
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Constants.swift").write_text(
        'let apiKey = "ab12cd34ef56gh78ij90kl12mn34op56"'
    )
    return tmp_path


def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.build_info["deployment_target"] == "14.0"
    assert result.source_stats["swift_count"] == 1
    assert result.test_coverage is None
    assert any("deployment target 14.0" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.swift/.m/.mm)"


def test_analyze_project_gracefully_degrades_with_no_pbxproj(tmp_path: Path):
    """A pure Swift Package Manager project (no project.pbxproj) must not crash --
    it just gets zero version warnings, same as Android's missing-build.gradle fallback."""
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9")
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "Lib.swift").write_text("struct Lib {}")

    result = analyze_project(tmp_path)

    assert result.fatal_error is None
    assert result.build_info["deployment_target"] is None
    assert result.build_info["swift_version"] is None
    assert result.version_warnings == []
```

Create `backend/tests/test_ios_analyzer_context.py`:

```python
from pathlib import Path

from app.analyzer.ios_analyzer import gather_code_context


def test_gather_code_context_includes_swift_objc_and_header_content(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")
    (src / "Legacy.m").write_text("@implementation Legacy @end")
    (src / "Legacy.h").write_text("@interface Legacy : NSObject @end")

    context = gather_code_context(tmp_path)
    assert "AppDelegate.swift" in context
    assert "class AppDelegate {}" in context
    assert "@implementation Legacy @end" in context
    assert "@interface Legacy : NSObject @end" in context


def test_gather_code_context_returns_empty_string_when_no_source(tmp_path: Path):
    assert gather_code_context(tmp_path) == ""


def test_gather_code_context_respects_max_chars_budget(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Big.swift").write_text("x" * 1000)
    (src / "AlsoBig.swift").write_text("y" * 1000)
    context = gather_code_context(tmp_path, max_chars=500)
    assert len(context) <= 500 + 200
    assert "y" * 1000 not in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_ios_analyzer_project.py tests/test_ios_analyzer_source.py tests/test_ios_analyzer_orchestrator.py tests/test_ios_analyzer_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.ios_analyzer'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/analyzer/ios_analyzer.py`:

```python
import re
from pathlib import Path
from typing import Optional

from app.analyzer.analysis_result import AnalysisResult
from app.analyzer.secrets_scanner import scan_directory
from app.analyzer.version_checker import compare_ios_versions

_DEPLOYMENT_TARGET_RE = re.compile(r'IPHONEOS_DEPLOYMENT_TARGET\s*=\s*([0-9.]+)\s*;')
_SWIFT_VERSION_RE = re.compile(r'SWIFT_VERSION\s*=\s*([0-9.]+)\s*;')

SOURCE_EXTENSIONS = (".swift", ".m", ".mm")


def find_project_config(project_dir: Path) -> Optional[Path]:
    """Finds project.pbxproj, preferring one that lives directly inside an
    .xcodeproj bundle at a shallow path (mirrors android_analyzer's
    find_gradle_file preferring the app/ module's build.gradle over a
    dependency's, e.g. CocoaPods' own generated Pods.xcodeproj)."""
    project_dir = Path(project_dir)
    candidates = list(project_dir.rglob("project.pbxproj"))
    if not candidates:
        return None
    xcodeproj_candidates = [c for c in candidates if c.parent.suffix == ".xcodeproj"]
    return min(xcodeproj_candidates or candidates, key=lambda p: len(p.parts))


def parse_xcode_project(content: str) -> dict:
    deployment_match = _DEPLOYMENT_TARGET_RE.search(content)
    swift_version_match = _SWIFT_VERSION_RE.search(content)
    return {
        "deployment_target": deployment_match.group(1) if deployment_match else None,
        "swift_version": swift_version_match.group(1) if swift_version_match else None,
    }


def validate_project_structure(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    warnings = []

    has_project_file = (
        any(project_dir.rglob("*.xcodeproj")) or any(project_dir.rglob("*.xcworkspace"))
        or any(project_dir.rglob("Package.swift"))
    )
    if not has_project_file:
        warnings.append("Missing Xcode project (.xcodeproj/.xcworkspace) or Package.swift")

    if not any(project_dir.rglob("Info.plist")):
        warnings.append("Missing Info.plist")

    has_source = any(f for ext in SOURCE_EXTENSIONS for f in project_dir.rglob(f"*{ext}"))
    fatal_error = None if has_source else "No source files found (.swift/.m/.mm)"

    return {"warnings": warnings, "fatal_error": fatal_error}


def count_source_files(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    swift_files = list(project_dir.rglob("*.swift"))
    objc_files = list(project_dir.rglob("*.m")) + list(project_dir.rglob("*.mm"))
    all_files = swift_files + objc_files
    test_files = [
        f for f in all_files
        if any("test" in part.lower() for part in f.relative_to(project_dir).parts)
        or f.stem.endswith(("Test", "Tests"))
    ]
    return {
        "swift_count": len(swift_files),
        "objc_count": len(objc_files),
        "test_file_count": len(test_files),
    }


def _parse_lcov(report_path: Path) -> Optional[float]:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    total_found = total_hit = 0
    for line in text.splitlines():
        if line.startswith("LF:"):
            total_found += int(line[3:])
        elif line.startswith("LH:"):
            total_hit += int(line[3:])
    if total_found == 0:
        return None
    return round(total_hit / total_found * 100, 1)


def detect_test_coverage(project_dir: Path) -> Optional[float]:
    project_dir = Path(project_dir)
    for report_path in project_dir.rglob("*.info"):
        text_start = report_path.read_text(encoding="utf-8", errors="ignore")[:200] if report_path.is_file() else ""
        if "SF:" in text_start or "LF:" in text_start:
            coverage = _parse_lcov(report_path)
            if coverage is not None:
                return coverage
    return None


def analyze_project(project_dir: Path) -> AnalysisResult:
    project_dir = Path(project_dir)
    structure = validate_project_structure(project_dir)

    config_path = find_project_config(project_dir)
    try:
        config_content = config_path.read_text(encoding="utf-8", errors="ignore") if config_path else ""
    except OSError:
        config_content = ""
    build_info = parse_xcode_project(config_content)

    source_stats = count_source_files(project_dir)
    test_coverage = detect_test_coverage(project_dir)
    version_warnings = compare_ios_versions(build_info)
    secrets_found = scan_directory(project_dir)

    return AnalysisResult(
        build_info=build_info,
        structure_warnings=structure["warnings"],
        fatal_error=structure["fatal_error"],
        source_stats=source_stats,
        test_coverage=test_coverage,
        version_warnings=version_warnings,
        secrets_found=secrets_found,
    )


def gather_code_context(project_dir: Path, max_chars: int = 32000) -> str:
    project_dir = Path(project_dir)
    source_files = sorted(
        [f for ext in SOURCE_EXTENSIONS + (".h",) for f in project_dir.rglob(f"*{ext}")],
        key=lambda f: str(f.relative_to(project_dir)),
    )
    parts = []
    remaining = max_chars
    for f in source_files:
        if remaining <= 0:
            break
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        header = f"--- {f.relative_to(project_dir)} ---\n"
        chunk = header + content + "\n"
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        parts.append(chunk)
        remaining -= len(chunk)
    return "".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_ios_analyzer_project.py tests/test_ios_analyzer_source.py tests/test_ios_analyzer_orchestrator.py tests/test_ios_analyzer_context.py -v`
Expected: PASS (all tests across all four files)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/ios_analyzer.py backend/tests/test_ios_analyzer_project.py backend/tests/test_ios_analyzer_source.py backend/tests/test_ios_analyzer_orchestrator.py backend/tests/test_ios_analyzer_context.py
git commit -m "feat: add ios_analyzer for iOS project structural analysis"
```

---

## Task 5: `reviews.py` — platform-based analyzer dispatch

**Files:**
- Modify: `backend/app/api/reviews.py:15` (import), `:199` (`analyze_project` call), `:209` (`gather_code_context` call)
- Test: `backend/tests/test_reviews_create.py`
- Test: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `ios_analyzer` module (Task 4) and the existing `android_analyzer` module — both expose `analyze_project(project_dir) -> AnalysisResult` and `gather_code_context(project_dir, max_chars=32000) -> str` with identical signatures.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_reviews_create.py` (near the other `_run_review` tests):

```python
async def test_run_review_uses_ios_analyzer_for_ios_platform(monkeypatch):
    # Forces the real (Azure) LLM client's own built-in stub mode for both
    # score_category and generate_general_remarks -- neither is monkeypatched
    # here, so without this, a real AZURE_OPENAI_KEY (loaded from the repo's
    # .env by main.py's load_dotenv() at import time) would trigger a real,
    # slow network call instead of the deterministic stub path.
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "ios-analyzer-dispatch-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.xcodeproj/project.pbxproj", "buildSettings = { SWIFT_VERSION = 5.9; };")
        zf.writestr("Info.plist", "<plist></plist>")
        zf.writestr("MyApp/AppDelegate.swift", "class AppDelegate {}")
    zip_path.write_bytes(buffer.getvalue())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="MyApp",
        platform="iOS",
    )

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert "AppDelegate.swift" in state["code_context"]
```

(`io` and `zipfile` are already imported at the top of `test_reviews_create.py` — no new imports needed.)

Add to `backend/tests/test_reviews_integration.py` (after `test_full_review_pipeline_non_android_platform_skips_compile_check`):

```python
async def test_full_review_pipeline_for_a_real_ios_project(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    ios_zip_buffer = io.BytesIO()
    with zipfile.ZipFile(ios_zip_buffer, "w") as zf:
        zf.writestr("MyApp.xcodeproj/project.pbxproj", "buildSettings = { IPHONEOS_DEPLOYMENT_TARGET = 17.0; SWIFT_VERSION = 5.9; };")
        zf.writestr("Info.plist", "<plist></plist>")
        zf.writestr("MyApp/AppDelegate.swift", "class AppDelegate {}")

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "androidZip": ("MyApp.zip", ios_zip_buffer.getvalue(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={"platform": "iOS"},
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
        assert final_state["compile_status"] is None

        category_1 = next(c for c in final_state["category_scores"] if c["id"] == "1")
        sub_1_1 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.1")
        assert sub_1_1["score"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_create.py::test_run_review_uses_ios_analyzer_for_ios_platform tests/test_reviews_integration.py::test_full_review_pipeline_for_a_real_ios_project -v`
Expected: FAIL — `state["status"] == "error"` (both currently error with `"No source files found (.java/.kt)"` since `_run_review` still unconditionally uses `android_analyzer`).

- [ ] **Step 3: Write the implementation**

In `backend/app/api/reviews.py`, replace the import at line 15:

```python
from app.analyzer import android_analyzer, ios_analyzer
```

(This replaces `from app.analyzer.android_analyzer import analyze_project, gather_code_context` — the two call sites below now go through whichever module is selected.)

Replace the call at line 199 (`analysis = analyze_project(extract_dir)`) — insert the dispatch line immediately before it and use `analyzer.` prefix:

```python
        analyzer = ios_analyzer if platform == "iOS" else android_analyzer
        analysis = analyzer.analyze_project(extract_dir)
```

Replace the call at line 209 (`code_context = gather_code_context(extract_dir)`):

```python
        code_context = analyzer.gather_code_context(extract_dir)
```

(`analyzer` is assigned once, right before its first use at the `analyze_project` call, and reused for the `gather_code_context` call a few lines later — both calls are inside the same `try` block with `platform` already in scope as a parameter.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: PASS (all tests in both files, including every pre-existing Android test — unaffected since `platform` defaults to `"Android"`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: dispatch to ios_analyzer for iOS-platform reviews"
```

---

## Final Verification

After all five tasks:

- [ ] Run the full backend suite: `cd backend && venv/bin/python -m pytest -v` — expect all tests passing, zero failures.
- [ ] Run the full frontend suite: `cd frontend && npx react-scripts test --watchAll=false` — expect all tests passing, zero failures (no frontend files change in this plan, but confirms nothing else regressed).
- [ ] Rebuild the backend docker container; if a real iOS DevOps repo + iOS scoring template are available, run a real review end to end and confirm it completes instead of failing on `"No source files found"`.
