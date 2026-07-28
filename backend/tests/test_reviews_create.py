import io
import tempfile
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _new_review_state, _reviews, _run_review
from main import app

client = TestClient(app)


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
    ws.append(["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"])
    wb.save(buffer)
    return buffer.getvalue()


def test_create_review_returns_id_and_creates_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "processing"
        assert body["review_id"] in _reviews


def test_create_review_write_failure_returns_200_with_error_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    created_tasks = []
    original_create_task = reviews_module.asyncio.create_task

    def _tracking_create_task(coro, *args, **kwargs):
        created_tasks.append(coro)
        return original_create_task(coro, *args, **kwargs)

    def _raise_write_bytes(self, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(reviews_module.asyncio, "create_task", _tracking_create_task)
    monkeypatch.setattr(Path, "write_bytes", _raise_write_bytes)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )

        # No exception propagated out of the endpoint; FastAPI still answers 200.
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "error"

        review_id = body["review_id"]
        assert review_id in _reviews
        state = _reviews[review_id]
        assert state["status"] == "error"
        assert state["phase"] == "error"
        assert state["error"]

        # _run_review must never have been scheduled for this review.
        assert created_tasks == []


async def test_run_review_removes_work_dir_when_no_output_produced():
    review_id = "leak-check-invalid-inputs"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(b"not really a zip")
    template_path.write_bytes(b"not really an xlsx")

    _reviews[review_id] = _new_review_state()

    # zip_valid=False takes the early-return error branch inside the try block,
    # so no output.xlsx is ever written and download_path stays None.
    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=False, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["download_path"] is None
    assert not work_dir.exists()


async def test_run_review_updates_message_per_category_during_scoring(monkeypatch):
    review_id = "progress-message-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    seen_messages = []

    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        seen_messages.append(_reviews[review_id]["message"])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert seen_messages == [
        "Evaluating Code naming conventions / Code Structure...",
        "Evaluating Reliability, Security & Observability...",
        "Evaluating Delivery Discipline & Architecture...",
        "Evaluating AI Usage & Code Ownership...",
        "Evaluating Safe & Integrated AI Code...",
    ]

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert state["message"] == "Review complete"


async def test_run_review_updates_category_scores_progressively(monkeypatch):
    review_id = "category-scores-progress-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    assert _reviews[review_id]["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": None},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
        {"id": "3", "name": "Delivery Discipline & Architecture", "percent_points": None},
        {"id": "4", "name": "AI Usage & Code Ownership", "percent_points": None},
        {"id": "6", "name": "Safe & Integrated AI Code", "percent_points": None},
    ]

    snapshots = []

    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    # Snapshot taken right before each category is scored: earlier categories
    # already show their resolved percent_points (stub mode always scores 1,
    # i.e. 100.0%), later ones are still None -- proves updates land in place
    # without disturbing sibling entries.
    assert snapshots[0] == [("1", None), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[1] == [("1", 100.0), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[4] == [("1", 100.0), ("2", 100.0), ("3", 100.0), ("4", 100.0), ("6", None)]

    final_scores = _reviews[review_id]["category_scores"]
    assert all(entry["percent_points"] == 100.0 for entry in final_scores)


async def test_run_review_builds_prompt_log_and_code_context(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "prompt-log-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()
    assert _reviews[review_id]["code_context"] is None
    assert _reviews[review_id]["prompt_log"] == []

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert "class Main {}" in state["code_context"]
    # 5 category calls + 1 general-remarks call, in that order.
    assert [entry["label"] for entry in state["prompt_log"]] == [
        "Code naming conventions / Code Structure",
        "Reliability, Security & Observability",
        "Delivery Discipline & Architecture",
        "AI Usage & Code Ownership",
        "Safe & Integrated AI Code",
        "General remarks",
    ]
    assert all(
        entry["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
        for entry in state["prompt_log"]
    )


async def test_run_review_updates_message_on_error_paths(monkeypatch):
    review_id = "progress-message-error-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(reviews_module, "analyze_project", _boom)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert _reviews[review_id]["message"] == "Review failed"


async def test_run_review_removes_work_dir_on_unexpected_exception(monkeypatch):
    review_id = "leak-check-exception"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated analysis crash")

    monkeypatch.setattr(reviews_module, "analyze_project", _boom)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["error"] == "simulated analysis crash"
    assert state["download_path"] is None
    assert not work_dir.exists()
