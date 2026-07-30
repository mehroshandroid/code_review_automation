from app.log_parser import count_warnings, parse_build_log

BUILD_LOG = """
CompileSwift normal arm64 /project/Sources/AppDelegate.swift
/project/Sources/AppDelegate.swift:12:5: warning: variable 'foo' was never used; consider replacing with '_'
/project/Sources/AppDelegate.swift:20:1: error: cannot find 'bar' in scope
** BUILD FAILED **
"""


def test_parse_build_log_extracts_every_diagnostic():
    issues = parse_build_log(BUILD_LOG)

    assert issues == [
        {
            "severity": "Warning",
            "message": "variable 'foo' was never used; consider replacing with '_'",
            "file": "/project/Sources/AppDelegate.swift",
            "line": 12,
        },
        {
            "severity": "Error",
            "message": "cannot find 'bar' in scope",
            "file": "/project/Sources/AppDelegate.swift",
            "line": 20,
        },
    ]


def test_parse_build_log_returns_empty_list_when_no_diagnostics():
    assert parse_build_log("** BUILD SUCCEEDED **\n") == []


def test_count_warnings_only_counts_warning_and_error_severity():
    issues = [
        {"severity": "Warning", "message": "a", "file": "f", "line": 1},
        {"severity": "Error", "message": "b", "file": "f", "line": 2},
    ]
    assert count_warnings(issues) == 2
