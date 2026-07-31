from app.dotnet_build_parser import count_warnings, parse_build_output

BUILD_OUTPUT = """
Restore complete (1.2s)
  MyApp succeeded with 2 warning(s) (3.4s)
/src/MyApp/Program.cs(10,5): warning CS0168: The variable 'e' is declared but never used [/src/MyApp/MyApp.csproj]
/src/MyApp/PaymentService.cs(42,13): error CS0103: The name 'foo' does not exist in the current context [/src/MyApp/MyApp.csproj]
Build succeeded.
"""


def test_parse_build_output_extracts_every_diagnostic():
    issues = parse_build_output(BUILD_OUTPUT)

    assert issues == [
        {
            "severity": "Warning",
            "message": "The variable 'e' is declared but never used",
            "file": "/src/MyApp/Program.cs",
            "line": 10,
        },
        {
            "severity": "Error",
            "message": "The name 'foo' does not exist in the current context",
            "file": "/src/MyApp/PaymentService.cs",
            "line": 42,
        },
    ]


def test_parse_build_output_returns_empty_list_when_no_diagnostics():
    assert parse_build_output("Build succeeded.\n") == []


def test_count_warnings_only_counts_warning_and_error_severity():
    issues = [
        {"severity": "Warning", "message": "a", "file": "f", "line": 1},
        {"severity": "Error", "message": "b", "file": "f", "line": 2},
    ]
    assert count_warnings(issues) == 2
