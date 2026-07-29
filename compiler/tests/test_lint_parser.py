from app.lint_parser import count_warnings, find_lint_report, parse_lint_report

LINT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<issues format="6" by="lint 8.1.0">
    <issue
        id="UnusedResources"
        severity="Warning"
        message="The resource `R.string.foo` appears to be unused"
        category="Performance">
        <location file="/project/app/src/main/res/values/strings.xml" line="3" column="13"/>
    </issue>
    <issue
        id="HardcodedText"
        severity="Informational"
        message="Hardcoded string, consider using @string resource">
        <location file="/project/app/src/main/res/layout/activity_main.xml" line="10"/>
    </issue>
    <issue
        id="MissingPermission"
        severity="Error"
        message="Missing permission check">
        <location file="/project/app/src/main/java/Main.java" line="42"/>
    </issue>
</issues>
"""


def test_parse_lint_report_extracts_every_issue(tmp_path):
    report_path = tmp_path / "lint-results-debug.xml"
    report_path.write_text(LINT_XML)

    issues = parse_lint_report(report_path)

    assert issues == [
        {"severity": "Warning", "message": "The resource `R.string.foo` appears to be unused",
         "file": "/project/app/src/main/res/values/strings.xml", "line": 3},
        {"severity": "Informational", "message": "Hardcoded string, consider using @string resource",
         "file": "/project/app/src/main/res/layout/activity_main.xml", "line": 10},
        {"severity": "Error", "message": "Missing permission check",
         "file": "/project/app/src/main/java/Main.java", "line": 42},
    ]


def test_count_warnings_only_counts_warning_and_error_severity():
    issues = [
        {"severity": "Warning", "message": "a", "file": "f", "line": 1},
        {"severity": "Informational", "message": "b", "file": "f", "line": 2},
        {"severity": "Error", "message": "c", "file": "f", "line": 3},
    ]
    assert count_warnings(issues) == 2


def test_find_lint_report_searches_anywhere_in_the_tree(tmp_path):
    nested = tmp_path / "app" / "build" / "reports"
    nested.mkdir(parents=True)
    report_path = nested / "lint-results-debug.xml"
    report_path.write_text(LINT_XML)

    found = find_lint_report(tmp_path)

    assert found == report_path


def test_find_lint_report_returns_none_when_absent(tmp_path):
    assert find_lint_report(tmp_path) is None
