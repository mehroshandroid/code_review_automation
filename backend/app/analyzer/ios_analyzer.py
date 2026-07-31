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
