from pathlib import Path

import pytest

from app.build_runner import _parse_scheme_from_list_output, _run_subprocess, find_project

XCODEBUILD_LIST_SINGLE_SCHEME = """Information about project "MyApp":
    Targets:
        MyApp

    Build Configurations:
        Debug
        Release

    Schemes:
        MyApp
"""

XCODEBUILD_LIST_MULTIPLE_SCHEMES = """Information about workspace "MyApp":
    Schemes:
        MyApp
        MyAppTests
        Pods-MyApp
"""


def test_parse_scheme_from_list_output_returns_the_only_scheme():
    assert _parse_scheme_from_list_output(XCODEBUILD_LIST_SINGLE_SCHEME) == "MyApp"


def test_parse_scheme_from_list_output_returns_the_first_of_several_schemes():
    assert _parse_scheme_from_list_output(XCODEBUILD_LIST_MULTIPLE_SCHEMES) == "MyApp"


def test_parse_scheme_from_list_output_returns_none_when_no_schemes_section():
    assert _parse_scheme_from_list_output("Information about project \"MyApp\":\n    Targets:\n        MyApp\n") is None


def test_find_project_prefers_workspace_over_project(tmp_path: Path):
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()
    workspace = tmp_path / "MyApp.xcworkspace"
    workspace.mkdir()

    found = find_project(tmp_path)

    assert found == (workspace, "-workspace")


def test_find_project_falls_back_to_xcodeproj_when_no_workspace(tmp_path: Path):
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()

    found = find_project(tmp_path)

    assert found == (xcodeproj, "-project")


def test_find_project_returns_none_when_neither_exists(tmp_path: Path):
    assert find_project(tmp_path) is None


@pytest.mark.asyncio
async def test_run_subprocess_collects_full_stdout_and_stderr(tmp_path):
    result = await _run_subprocess(
        ["sh", "-c", "echo out-line-1; echo out-line-2; echo err-line-1 1>&2"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert result["returncode"] == 0
    assert "out-line-1" in result["stdout"]
    assert "out-line-2" in result["stdout"]
    assert "err-line-1" in result["stderr"]


@pytest.mark.asyncio
async def test_run_subprocess_reports_nonzero_exit_code(tmp_path):
    result = await _run_subprocess(["sh", "-c", "exit 3"], cwd=tmp_path, timeout_seconds=10)
    assert result["returncode"] == 3


@pytest.mark.asyncio
async def test_run_subprocess_times_out(tmp_path):
    result = await _run_subprocess(["sh", "-c", "sleep 5"], cwd=tmp_path, timeout_seconds=0.2)
    assert result == {"returncode": None, "stdout": "", "stderr": "xcodebuild process timed out."}
