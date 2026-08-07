import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _new_review_state, _persist_review_result, _reviews, _run_review


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.fixture
def captured_crud_calls(monkeypatch):
    calls = []

    async def fake_persist_review_result(session, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "persist_review_result", fake_persist_review_result)
    return calls


@pytest.fixture
def artifacts_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_ARTIFACTS_DIR", str(tmp_path))
    return tmp_path


async def test_persists_a_completed_review_with_pending_approval_status(captured_crud_calls, artifacts_dir):
    state = _new_review_state()
    state["status"] = "completed"
    state["project_name"] = "Moove"
    state["source"] = "upload"
    state["total_score_pct"] = 82.5
    state["category_scores"] = [{"id": "1", "name": "Structure", "percent_points": 100, "sub_criteria": []}]
    state["warnings"] = ["Outdated SDK"]
    state["secrets_found"] = []
    state["lint_issues"] = []
    state["compile_status"] = "ok"
    state["stats"] = {"total_time_ms": 1000}

    work_dir = Path(tempfile.mkdtemp())
    output_path = work_dir / "output.xlsx"
    output_path.write_bytes(b"fake xlsx bytes")
    state["download_path"] = str(output_path)

    await _persist_review_result(
        "review-1", None, "Moove", ".NET", "azure", None, "compiler", state,
    )

    assert len(captured_crud_calls) == 1
    call = captured_crud_calls[0]
    assert call["review_id"] == "review-1"
    assert call["project_id"] is None
    assert call["status"] == "pending_approval"
    assert call["platform"] == ".NET"
    assert call["project_name"] == "Moove"
    assert call["total_score_pct"] == 82.5
    assert call["llm_provider"] == "azure"
    assert call["compile_check_mode"] == "compiler"
    assert call["source"] == "upload"
    assert call["result_data"]["warnings"] == ["Outdated SDK"]
    assert call["result_data"]["category_scores"] == state["category_scores"]
    assert "code_context" not in call["result_data"]
    assert "prompt_log" not in call["result_data"]

    # The workbook was copied to the persistent artifacts dir, not just
    # referenced from the (about-to-be-deleted) temp work dir.
    assert call["workbook_path"] is not None
    persisted_workbook = Path(call["workbook_path"])
    assert persisted_workbook.exists()
    assert persisted_workbook.read_bytes() == b"fake xlsx bytes"
    assert persisted_workbook.parent == artifacts_dir


async def test_persists_an_errored_review_with_error_status_and_no_workbook(captured_crud_calls, artifacts_dir):
    state = _new_review_state()
    state["status"] = "error"
    state["error"] = "Ollama request timed out"
    state["project_name"] = "MyApp"
    state["source"] = "upload"

    await _persist_review_result(
        "review-2", None, "MyApp", "iOS", "azure", None, "compiler", state,
    )

    assert len(captured_crud_calls) == 1
    call = captured_crud_calls[0]
    assert call["status"] == "error"
    assert call["workbook_path"] is None
    assert call["result_data"] == {"error": "Ollama request timed out"}


async def test_persists_with_the_given_project_id_when_provided(captured_crud_calls, artifacts_dir):
    state = _new_review_state()
    state["status"] = "error"
    state["error"] = "boom"
    state["project_name"] = "MyApp"
    state["source"] = "upload"

    await _persist_review_result(
        "review-3", "project-42", "MyApp", "Android", "azure", None, "compiler", state,
    )

    assert captured_crud_calls[0]["project_id"] == "project-42"


async def test_a_db_failure_is_logged_and_swallowed_not_raised(artifacts_dir, monkeypatch):
    async def fake_persist_review_result(session, **kwargs):
        raise ConnectionError("could not connect to postgres")

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "persist_review_result", fake_persist_review_result)

    state = _new_review_state()
    state["status"] = "error"
    state["error"] = "boom"
    state["project_name"] = "MyApp"
    state["source"] = "upload"

    # Must not raise -- persistence is best-effort and must never affect the
    # in-memory review outcome already shown to the current user.
    await _persist_review_result("review-4", None, "MyApp", "Android", "azure", None, "compiler", state)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("build.gradle", "android { compileSdkVersion 34 }")
        zf.writestr("AndroidManifest.xml", "<manifest />")
        zf.writestr("src/main/java/Main.java", "class Main {}")
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D2:D2)", "=D1*C1", "=E1/C1", None])
    ws.append([1.1, "Clear and consistent naming conventions", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


async def test_run_review_threads_project_id_through_to_persistence(monkeypatch):
    # End-to-end wiring check: create_review's projectId form field ->
    # _run_review's project_id param -> _persist_review_result's call to
    # crud.persist_review_result. Isolated unit tests above already cover
    # _persist_review_result's own logic in detail; this proves the plumbing
    # between it and the rest of the pipeline is actually connected.
    review_id = "wiring-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured = {}

    async def fake_persist_review_result(review_id_arg, project_id_arg, *args, **kwargs):
        captured["review_id"] = review_id_arg
        captured["project_id"] = project_id_arg

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "_persist_review_result", fake_persist_review_result)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        project_id="proj-1",
    )

    assert captured == {"review_id": "wiring-check", "project_id": "proj-1"}
