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
