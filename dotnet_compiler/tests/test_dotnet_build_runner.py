import pytest

from app.dotnet_build_runner import _run_subprocess, find_project


def test_find_project_prefers_a_sln_over_a_csproj(tmp_path):
    csproj = tmp_path / "MyApp" / "MyApp.csproj"
    csproj.parent.mkdir(parents=True)
    csproj.write_text("stub")

    sln = tmp_path / "MyApp.sln"
    sln.write_text("stub")

    assert find_project(tmp_path) == sln


def test_find_project_falls_back_to_a_csproj_when_no_sln(tmp_path):
    csproj = tmp_path / "MyApp" / "MyApp.csproj"
    csproj.parent.mkdir(parents=True)
    csproj.write_text("stub")

    assert find_project(tmp_path) == csproj


def test_find_project_returns_none_when_neither_exists(tmp_path):
    assert find_project(tmp_path) is None


@pytest.mark.asyncio
async def test_run_subprocess_collects_full_stdout_and_stderr(tmp_path):
    result = await _run_subprocess(
        ["sh", "-c", "echo out-line-1; echo out-line-2; echo err-line-1 1>&2"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert result["returncode"] == 0
    assert result["stdout"] == "out-line-1\nout-line-2"
    assert result["stderr"] == "err-line-1"


@pytest.mark.asyncio
async def test_run_subprocess_reports_nonzero_exit_code(tmp_path):
    result = await _run_subprocess(["sh", "-c", "exit 3"], cwd=tmp_path, timeout_seconds=10)
    assert result["returncode"] == 3


@pytest.mark.asyncio
async def test_run_subprocess_times_out(tmp_path):
    result = await _run_subprocess(["sh", "-c", "sleep 5"], cwd=tmp_path, timeout_seconds=0.2)
    assert result == {"returncode": None, "stdout": "", "stderr": "dotnet build process timed out."}
