from pathlib import Path

import pytest

import app.claude_runner as claude_runner_module
from app.claude_runner import _parse_claude_output, _run_subprocess, run_claude


@pytest.mark.asyncio
async def test_run_subprocess_collects_stdout_and_exit_code(tmp_path):
    result = await _run_subprocess(["sh", "-c", "echo hello"], cwd=tmp_path, timeout_seconds=10)

    assert result["returncode"] == 0
    assert "hello" in result["stdout"]


@pytest.mark.asyncio
async def test_run_subprocess_reports_nonzero_exit_code_and_stderr(tmp_path):
    result = await _run_subprocess(["sh", "-c", "echo boom 1>&2; exit 1"], cwd=tmp_path, timeout_seconds=10)

    assert result["returncode"] == 1
    assert "boom" in result["stderr"]


@pytest.mark.asyncio
async def test_run_subprocess_times_out(tmp_path):
    result = await _run_subprocess(["sh", "-c", "sleep 5"], cwd=tmp_path, timeout_seconds=0.2)

    assert result == {"returncode": None, "stdout": "", "stderr": "claude CLI process timed out."}


@pytest.mark.asyncio
async def test_run_subprocess_returns_an_error_result_when_the_executable_does_not_exist(tmp_path):
    result = await _run_subprocess(["this-binary-does-not-exist-xyz"], cwd=tmp_path, timeout_seconds=10)

    assert result["returncode"] is None
    assert "Failed to start process" in result["stderr"]


def test_parse_claude_output_extracts_the_result_text_on_success():
    run_result = {"returncode": 0, "stdout": '{"is_error": false, "result": "the answer"}', "stderr": ""}

    assert _parse_claude_output(run_result) == {"status": "ok", "result": "the answer"}


def test_parse_claude_output_reports_error_on_nonzero_exit():
    run_result = {"returncode": 1, "stdout": "", "stderr": "auth failed"}

    assert _parse_claude_output(run_result) == {"status": "error", "message": "auth failed"}


def test_parse_claude_output_reports_a_generic_message_on_nonzero_exit_with_no_stderr():
    run_result = {"returncode": 1, "stdout": "", "stderr": ""}

    assert _parse_claude_output(run_result) == {"status": "error", "message": "claude CLI exited with a non-zero status."}


def test_parse_claude_output_reports_error_on_unparseable_json():
    run_result = {"returncode": 0, "stdout": "not json", "stderr": ""}

    assert _parse_claude_output(run_result) == {
        "status": "error", "message": "claude CLI returned output that wasn't valid JSON.",
    }


def test_parse_claude_output_reports_error_when_claude_itself_reports_is_error():
    run_result = {"returncode": 0, "stdout": '{"is_error": true, "result": "overloaded_error"}', "stderr": ""}

    assert _parse_claude_output(run_result) == {"status": "error", "message": "overloaded_error"}


async def test_run_claude_builds_the_expected_command_and_uses_an_empty_cwd(monkeypatch):
    captured = {}

    async def fake_run_subprocess(command, cwd, timeout_seconds):
        captured["command"] = command
        captured["cwd_is_dir"] = Path(cwd).is_dir()
        captured["cwd_is_empty"] = list(Path(cwd).iterdir()) == []
        return {"returncode": 0, "stdout": '{"is_error": false, "result": "ok"}', "stderr": ""}

    monkeypatch.setattr(claude_runner_module, "_run_subprocess", fake_run_subprocess)

    result = await run_claude("score this code")

    assert result == {"status": "ok", "result": "ok"}
    assert captured["command"] == [
        "claude", "--print", "--output-format", "json",
        "--max-turns", "1", "--restricted", "--permission-prompts", "none",
        "score this code",
    ]
    assert captured["cwd_is_dir"] is True
    assert captured["cwd_is_empty"] is True


async def test_run_claude_cleans_up_its_temp_directory_afterward(monkeypatch):
    captured_cwd = {}

    async def fake_run_subprocess(command, cwd, timeout_seconds):
        captured_cwd["path"] = Path(cwd)
        return {"returncode": 0, "stdout": '{"is_error": false, "result": "ok"}', "stderr": ""}

    monkeypatch.setattr(claude_runner_module, "_run_subprocess", fake_run_subprocess)

    await run_claude("score this code")

    assert not captured_cwd["path"].exists()
