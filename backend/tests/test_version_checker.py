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


def test_malformed_string_sdk_value_does_not_crash():
    """Reproduce crash scenario: compile_sdk as string instead of int"""
    gradle_info = {
        "compile_sdk": "30",  # Malformed: string instead of int
        "target_sdk": None,
        "gradle_version": None,
        "kotlin_version": None,
    }
    # Should not raise TypeError, should return empty list (value skipped)
    result = compare_versions(gradle_info)
    assert result == []


def test_malformed_float_version_value_does_not_crash():
    """Reproduce crash scenario: gradle_version as float instead of string"""
    gradle_info = {
        "compile_sdk": None,
        "target_sdk": None,
        "gradle_version": 8.0,  # Malformed: float instead of string
        "kotlin_version": None,
    }
    # Should not raise AttributeError, should return empty list (value skipped)
    result = compare_versions(gradle_info)
    assert result == []


def test_malformed_mixed_types_does_not_crash():
    """Test multiple malformed types together"""
    gradle_info = {
        "compile_sdk": "30",  # String instead of int
        "target_sdk": 25.5,  # Float instead of int
        "gradle_version": 8.0,  # Float instead of string
        "kotlin_version": ["1", "6"],  # List instead of string
    }
    # Should not raise any exception, should return empty list
    result = compare_versions(gradle_info)
    assert result == []
