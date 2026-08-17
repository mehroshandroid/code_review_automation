import io
import tempfile
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _resolve_excel_template
from main import app

client = TestClient(app)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _FakeTemplate:
    def __init__(self, file_path, filename):
        self.file_path = file_path
        self.filename = filename


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


async def test_resolve_excel_template_reads_the_uploaded_file_when_provided():
    class _FakeUpload:
        filename = "uploaded.xlsx"

        async def read(self):
            return b"uploaded bytes"

    template_bytes, filename = await _resolve_excel_template(_FakeUpload(), "Android")

    assert template_bytes == b"uploaded bytes"
    assert filename == "uploaded.xlsx"


async def test_resolve_excel_template_falls_back_to_stored_default_when_not_provided(tmp_path, monkeypatch):
    stored_path = tmp_path / "Android.xlsx"
    stored_path.write_bytes(b"stored default bytes")

    async def fake_get_sample_template(session, platform):
        assert platform == "Android"
        return _FakeTemplate(str(stored_path), "android-default.xlsx")

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "get_sample_template", fake_get_sample_template)

    template_bytes, filename = await _resolve_excel_template(None, "Android")

    assert template_bytes == b"stored default bytes"
    assert filename == "android-default.xlsx"


async def test_resolve_excel_template_returns_none_when_no_upload_and_no_stored_default(monkeypatch):
    async def fake_get_sample_template(session, platform):
        return None

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "get_sample_template", fake_get_sample_template)

    template_bytes, filename = await _resolve_excel_template(None, "Android")

    assert template_bytes is None
    assert filename is None


async def test_resolve_excel_template_returns_none_on_db_failure_without_raising(monkeypatch):
    async def fake_get_sample_template(session, platform):
        raise ConnectionError("could not connect to postgres")

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "get_sample_template", fake_get_sample_template)

    template_bytes, filename = await _resolve_excel_template(None, "Android")

    assert template_bytes is None
    assert filename is None


def test_create_review_without_excel_template_uses_stored_default(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    stored_path = tmp_path / "Android.xlsx"
    stored_path.write_bytes(_build_xlsx_bytes())

    async def fake_resolve_excel_template(excel_template, platform):
        assert excel_template is None
        return stored_path.read_bytes(), "android-default.xlsx"

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_resolve_excel_template)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={"androidZip": ("project.zip", _build_zip_bytes(), "application/zip")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["review_id"] in reviews_module._reviews


def test_create_review_without_excel_template_and_no_stored_default_returns_error(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    async def fake_resolve_excel_template(excel_template, platform):
        assert excel_template is None
        return None, None

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_resolve_excel_template)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={"androidZip": ("project.zip", _build_zip_bytes(), "application/zip")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"

    state = reviews_module._reviews[body["review_id"]]
    assert state["status"] == "error"
    assert "excelTemplate must be provided" in state["error"]
