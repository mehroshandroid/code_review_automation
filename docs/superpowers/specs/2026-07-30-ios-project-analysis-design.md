# iOS Project Analysis Design Spec

**Status:** Approved
**Date:** 2026-07-30
**Source:** A real iOS project, cloned via the (working) Azure DevOps integration and scored against a real iOS template, failed immediately with `"No source files found (.java/.kt)"` — `android_analyzer.py`'s structural analysis is entirely Android/Gradle-specific and has no concept of Swift/Objective-C projects at all, even though compile-check gating and category/sub-criteria discovery are already platform-agnostic from earlier rounds.

## Purpose

Give the review pipeline a real iOS-aware analysis path so an iOS project can complete a review end to end: source-file detection, secrets scanning, version-freshness checks, test-coverage detection, and LLM code-context gathering all currently assume Java/Kotlin/Gradle and need an iOS equivalent.

## Out of Scope

- Any project-file format beyond `project.pbxproj` for version extraction — pure Swift Package Manager projects (`Package.swift`, no `.xcodeproj`) get zero version warnings, gracefully, the same way a missing `build.gradle` already produces zero warnings for Android today.
- Parsing Xcode's native `.xcresult` test-result format — it requires the actual Xcode toolchain (`xcrun xccov`), which will never exist in this Linux backend container. Test coverage is read from a committed LCOV-format report (`lcov.info`) instead.
- A class-based analyzer interface — this codebase's analyzer layer (`compile_checker.py`, `secrets_scanner.py`, `version_checker.py`, `excel_handler.py`, `devops_client.py`) is entirely function-based modules; iOS support follows that same convention rather than introducing the first class hierarchy.
- Any change to Android's own behavior, output shape, or code path. Every existing Android test must keep passing unchanged.
- The `ProgressTracker` "fetching" step UI gap (noticed during this same conversation) — tracked as a separate, unrelated frontend fix.

## 1. Shared `AnalysisResult` extraction

`android_analyzer.py` currently defines and returns its own `AnalysisResult` dataclass. Since `ios_analyzer.py` needs to return the same shape (so `reviews.py` doesn't need per-platform branching beyond picking which module to call), the dataclass moves to a new `app/analyzer/analysis_result.py`:

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

The one field rename from today's `gradle_info` to `build_info` is safe: `reviews.py` never reads that field directly (only `.fatal_error`, `.structure_warnings`, `.test_coverage`, `.version_warnings`, `.secrets_found` cross that boundary) — it's purely internal to each analyzer's own `analyze_project()`, which passes it straight into that platform's own version-comparison function. `android_analyzer.py` imports `AnalysisResult` from the new module instead of defining it, and renames its own internal `gradle_info` local variable to `build_info` for consistency (no behavior change).

## 2. `ios_analyzer.py`

New module, structurally parallel to `android_analyzer.py`:

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
    find_gradle_file preferring the app/ module's build.gradle)."""
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

    has_source = any(
        f for ext in SOURCE_EXTENSIONS for f in project_dir.rglob(f"*{ext}")
    )
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

## 3. `version_checker.py`: `compare_ios_versions`

Added alongside the existing `compare_versions` (Android) in the same file:

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

Reuses the existing `_parse_version_tuple` helper unchanged.

## 4. `secrets_scanner.py`: extension broadening

```python
SCAN_EXTENSIONS = {".java", ".kt", ".xml", ".properties", ".gradle", ".kts", ".swift", ".m", ".h", ".mm", ".plist"}
```

One shared, platform-agnostic scanner — no per-platform branching needed since secret-pattern matching itself doesn't care what language it's looking at.

## 5. `reviews.py`: platform-based analyzer dispatch

```python
from app.analyzer import android_analyzer, ios_analyzer
...
        analyzer = ios_analyzer if platform == "iOS" else android_analyzer
        analysis = analyzer.analyze_project(extract_dir)
        ...
        code_context = analyzer.gather_code_context(extract_dir)
```

Replaces the current direct `analyze_project`/`gather_code_context` imports from `android_analyzer`. Every other platform value (including the default `"Android"` and any not-yet-supported platform string) falls through to `android_analyzer`, preserving today's behavior exactly.

## Testing

- New `test_ios_analyzer.py` mirroring `test_android_analyzer.py`'s fixtures and structure: fatal error on zero source files; non-fatal warnings for missing project file / missing `Info.plist`; `project.pbxproj` version extraction; graceful zero-warnings fallback for a pure-SPM project with no `project.pbxproj`; `lcov.info`-based coverage percentage; `gather_code_context` picking up `.swift`/`.m`/`.mm`/`.h` content.
- `test_version_checker.py`: new tests for `compare_ios_versions` (outdated deployment target, outdated Swift version, missing values skipped not flagged) mirroring the existing Android tests' shape.
- `test_secrets_scanner.py`: one new test proving a secret embedded in a `.swift` file is now found.
- `test_reviews_create.py` / `test_reviews_integration.py`: a new iOS-platform end-to-end case using a real iOS-shaped project fixture, asserting the review completes successfully (existing tests already prove the compile-check is *skipped* for iOS; this proves the *analysis* phase itself succeeds).
- Full existing Android test suite must pass unchanged — proves zero behavior change for `platform="Android"` (or the default).

## Ambiguity resolved during self-review

- `find_project_config`'s tie-breaking rule (shallowest path, preferring one inside an actual `.xcodeproj` bundle) mirrors `find_gradle_file`'s existing "prefer the `app/` module" preference for the same reason: real projects can have multiple `project.pbxproj` files (e.g. from nested example/demo targets or CocoaPods' own generated `Pods.xcodeproj`), and the shallowest one under a genuine `.xcodeproj` is the most likely to be the actual app target rather than a dependency's.
- `detect_test_coverage` only treats a `*.info` file as an LCOV report if its first 200 characters contain `SF:` or `LF:` markers, to avoid misreading an unrelated `.info` file that might exist in a repo for other reasons.
