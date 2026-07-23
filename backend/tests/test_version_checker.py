from app.analyzer.version_checker import compare_versions


def test_flags_outdated_versions():
    gradle_info = {
        "compile_sdk": 30,
        "target_sdk": 30,
        "gradle_version": "7.0",
        "kotlin_version": "1.6.0",
    }
    warnings = compare_versions(gradle_info)
    issues = [w["issue"] for w in warnings]
    assert any("compileSdkVersion 30" in i for i in issues)
    assert any("targetSdkVersion 30" in i for i in issues)
    assert any("Gradle version 7.0" in i for i in issues)
    assert any("Kotlin version 1.6.0" in i for i in issues)
    assert len(warnings) == 4


def test_no_warnings_when_up_to_date():
    gradle_info = {
        "compile_sdk": 34,
        "target_sdk": 34,
        "gradle_version": "8.2",
        "kotlin_version": "1.9.20",
    }
    assert compare_versions(gradle_info) == []


def test_missing_values_are_skipped_not_flagged():
    gradle_info = {"compile_sdk": None, "target_sdk": None, "gradle_version": None, "kotlin_version": None}
    assert compare_versions(gradle_info) == []
