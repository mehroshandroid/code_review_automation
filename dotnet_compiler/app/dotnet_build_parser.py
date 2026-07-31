import re

_DIAGNOSTIC_RE = re.compile(
    r'^(?P<file>.+?)\((?P<line>\d+),\d+\): (?P<severity>warning|error) \w+: (?P<message>.+?) \[.+\]$',
    re.MULTILINE,
)

COUNTED_SEVERITIES = {"Warning", "Error"}


def parse_build_output(text: str) -> list:
    issues = []
    for match in _DIAGNOSTIC_RE.finditer(text):
        issues.append({
            "severity": match.group("severity").capitalize(),
            "message": match.group("message").strip(),
            "file": match.group("file").strip(),
            "line": int(match.group("line")),
        })
    return issues


def count_warnings(issues: list) -> int:
    return sum(1 for issue in issues if issue["severity"] in COUNTED_SEVERITIES)
