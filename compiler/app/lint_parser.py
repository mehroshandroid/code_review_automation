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
