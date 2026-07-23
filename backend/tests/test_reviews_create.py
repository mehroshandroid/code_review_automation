import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _reviews
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
