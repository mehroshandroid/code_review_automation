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
