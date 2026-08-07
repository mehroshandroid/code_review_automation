import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from app.analyzer.analysis_result import AnalysisResult
from app.analyzer.secrets_scanner import scan_directory
from app.analyzer.version_checker import compare_dotnet_versions

_TARGET_FRAMEWORK_RE = re.compile(r'<TargetFramework>([^<]+)</TargetFramework>')
_TARGET_FRAMEWORK_VERSION_RE = re.compile(r'<TargetFrameworkVersion>([^<]+)</TargetFrameworkVersion>')


def find_project_config(project_dir: Path) -> Optional[Path]:
    """Finds a .csproj to read the TargetFramework from -- a .sln file is
    only an index of project references and carries no build settings of
    its own, so this always targets a .csproj regardless of whether a .sln
    also exists (see validate_project_structure for the broader "has some
    recognizable project file" structural check, which accepts either)."""
    project_dir = Path(project_dir)
    candidates = list(project_dir.rglob("*.csproj"))
    if not candidates:
        return None
    return min(candidates, key=lambda p: len(p.parts))


def parse_dotnet_project(content: str) -> dict:
    framework_match = _TARGET_FRAMEWORK_RE.search(content)
    if framework_match:
        return {"target_framework": framework_match.group(1)}
    legacy_match = _TARGET_FRAMEWORK_VERSION_RE.search(content)
    if legacy_match:
        return {"target_framework": legacy_match.group(1)}
    return {"target_framework": None}


def validate_project_structure(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    warnings = []

    has_project_file = any(project_dir.rglob("*.sln")) or any(project_dir.rglob("*.csproj"))
    if not has_project_file:
        warnings.append("Missing .sln or .csproj")

    has_source = any(project_dir.rglob("*.cs"))
    fatal_error = None if has_source else "No source files found (.cs)"

    return {"warnings": warnings, "fatal_error": fatal_error}


def count_source_files(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    cs_files = list(project_dir.rglob("*.cs"))
    test_files = [
        f for f in cs_files
        if any("test" in part.lower() for part in f.relative_to(project_dir).parts)
        or f.stem.endswith(("Test", "Tests"))
    ]
    return {
        "cs_count": len(cs_files),
        "test_file_count": len(test_files),
    }


def _parse_cobertura(report_path: Path) -> Optional[float]:
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
        if root.tag != "coverage":
            return None
        line_rate = root.get("line-rate")
        if line_rate is None:
            return None
        return round(float(line_rate) * 100, 1)
    except (ET.ParseError, ValueError, OSError, TypeError):
        return None


def detect_test_coverage(project_dir: Path) -> Optional[float]:
    project_dir = Path(project_dir)
    for report_path in project_dir.rglob("*cobertura*.xml"):
        coverage = _parse_cobertura(report_path)
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
    build_info = parse_dotnet_project(config_content)

    source_stats = count_source_files(project_dir)
    test_coverage = detect_test_coverage(project_dir)
    version_warnings = compare_dotnet_versions(build_info)
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


_PRIORITY_ENTRYPOINTS = {"Program.cs", "Startup.cs"}


def _priority_tier(filename: str) -> int:
    """Lower tiers are placed first when gather_code_context's max_chars
    budget can't fit every file. Program.cs/Startup.cs (JWT/auth middleware
    configuration) and *Controller.cs (per-endpoint [Authorize]/
    [AllowAnonymous] usage) are exactly the files a security-focused review
    clause like "Authentication and authorization correctly enforced" needs
    to see -- plain alphabetical order could truncate them out of a large
    multi-project solution before the LLM ever sees them."""
    if filename in _PRIORITY_ENTRYPOINTS:
        return 0
    if filename.endswith("Controller.cs"):
        return 1
    return 2


def gather_code_context(project_dir: Path, max_chars: int = 32000) -> str:
    project_dir = Path(project_dir)
    source_files = sorted(
        project_dir.rglob("*.cs"),
        key=lambda f: (_priority_tier(f.name), str(f.relative_to(project_dir))),
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
