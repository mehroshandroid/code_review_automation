import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.analyzer.secrets_scanner import scan_directory
from app.analyzer.version_checker import compare_versions

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


def count_source_files(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    java_files = list(project_dir.rglob("*.java"))
    kotlin_files = list(project_dir.rglob("*.kt"))
    all_files = java_files + kotlin_files
    test_files = [
        f for f in all_files
        if any("test" in part.lower() for part in f.relative_to(project_dir).parts) or f.stem.endswith("Test")
    ]
    return {
        "java_count": len(java_files),
        "kotlin_count": len(kotlin_files),
        "test_file_count": len(test_files),
    }


def _parse_jacoco_xml(report_path: Path) -> Optional[float]:
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
        for counter in root.findall("counter"):
            if counter.get("type") == "INSTRUCTION":
                missed = int(counter.get("missed", "0"))
                covered = int(counter.get("covered", "0"))
                total = missed + covered
                if total == 0:
                    return None
                return round(covered / total * 100, 1)
    except (ET.ParseError, ValueError, AttributeError, TypeError, OSError):
        return None
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
