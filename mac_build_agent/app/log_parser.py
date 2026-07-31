import re

_DIAGNOSTIC_RE = re.compile(
    r'^(?P<file>/\S+):(?P<line>\d+):\d+:\s+(?P<severity>warning|error):\s+(?P<message>.+)$',
    re.MULTILINE,
)

COUNTED_SEVERITIES = {"Warning", "Error"}


def parse_build_log(log_text: str) -> list:
    issues = []
    for match in _DIAGNOSTIC_RE.finditer(log_text):
        issues.append({
            "severity": match.group("severity").capitalize(),
            "message": match.group("message").strip(),
            "file": match.group("file"),
            "line": int(match.group("line")),
        })
    return issues


def count_warnings(issues: list) -> int:
    return sum(1 for issue in issues if issue["severity"] in COUNTED_SEVERITIES)
