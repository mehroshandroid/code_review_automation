import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.cycles as cycles_module
import app.api.projects as projects_module
import app.api.reviews as reviews_module
import app.automation.uploads as uploads_module
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.models import Base, User
from main import app

client = TestClient(app)
URL = "https://dev.azure.com/org/Proj/_git/repo"


def _zip_bytes(name="app/build.gradle", content=b"apply plugin: 'com.android.application'"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
async def db(monkeypatch, tmp_path):
    monkeypatch.setenv("CYCLE_UPLOADS_DIR", str(tmp_path / "uploads"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (cycles_module, reviews_module, projects_module):
        monkeypatch.setattr(module, "new_session", lambda: maker())
    async with maker() as s:
        for user_id, role in (("rev", "reviewer"), ("pm", "project_manager"), ("pm2", "project_manager")):
            await crud.create_user(s, user_id, f"{user_id}@example.com", "h", role)
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_project(s, "p2", "Beta")
        await crud.set_managers_for_project(s, "p1", ["pm"])
        await crud.set_managers_for_project(s, "p2", ["pm2"])
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev")])
        await crud.create_cycle(s, "c2", "p2", 2026, 4, None, [("Android", "rev")])
    yield maker
    await engine.dispose()


def _as(role, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)
    app.dependency_overrides[get_current_user] = lambda: user


def _upload(cycle="c1", data=None, filename="android-app.zip"):
    return client.put(
        f"/api/cycles/{cycle}/assignments/Android/zip",
        files={"file": (filename, data if data is not None else _zip_bytes(), "application/zip")},
    )


async def test_pm_uploads_a_zip_which_queues_the_review(db):
    _as("project_manager", "pm")
    body = _upload().json()
    assert (body["run_status"], body["source_type"], body["source_zip_name"], body["devops_url"]) == ("queued", "zip", "android-app.zip", None)
    assert body["url_submitted_at"] is not None
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
    assert Path(a.source_zip_path).read_bytes() == _zip_bytes()


async def test_zip_and_url_replace_each_other(db):
    _as("project_manager", "pm")
    client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL, "devops_branch": "main"})
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="url")
    body = _upload().json()
    assert body["devops_url"] is None and body["devops_branch"] is None and body["source_type"] == "zip"
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        zip_path = Path(a.source_zip_path)
        await crud.update_assignment(s, a, run_status="failed", failure_kind="url")
    body = client.put("/api/cycles/c1/assignments/Android/url", json={"devops_url": URL}).json()
    assert body["source_type"] == "devops" and body["source_zip_name"] is None
    assert not zip_path.exists()


def test_upload_validation(db):
    _as("project_manager", "pm")
    assert _upload(filename="code.tar.gz").status_code == 400
    assert _upload(data=b"not a zip").status_code == 400
    assert _upload(cycle="c2").status_code == 404
    assert _upload().status_code == 200
    assert _upload().status_code == 409  # already queued


def test_upload_size_limit(db, monkeypatch):
    monkeypatch.setattr(uploads_module, "MAX_ZIP_BYTES", 10)
    _as("project_manager", "pm")
    response = _upload()
    assert response.status_code == 400 and response.json()["detail"] == "The zip is too large (max 500 MB)."


def test_upload_permissions(db):
    _as("reviewer", "rev")
    assert _upload().status_code == 403
    _as("coordinator", "co")
    assert _upload().status_code == 200


async def test_rerun_with_a_zip(db):
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="completed", devops_url=URL, source_type="devops")
    _as("coordinator", "co")
    response = client.post("/api/cycles/c1/assignments/Android/rerun-zip", files={"file": ("fixed.zip", _zip_bytes(), "application/zip")})
    assert response.status_code == 200
    assert (response.json()["run_status"], response.json()["source_type"], response.json()["source_zip_name"]) == ("queued", "zip", "fixed.zip")
    _as("project_manager", "pm")
    assert client.post("/api/cycles/c1/assignments/Android/rerun-zip", files={"file": ("x.zip", _zip_bytes(), "application/zip")}).status_code == 403


async def test_approving_the_review_deletes_the_zip(db):
    _as("project_manager", "pm")
    _upload()
    async with db() as s:
        await crud.persist_review_result(
            s, review_id="r1", project_id="p1", platform="Android", status="pending_approval", project_name="Alpha",
            created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=80, llm_provider="azure",
            llm_model=None, compile_check_mode="compiler", source="upload", workbook_path=None, result_data={},
        )
        await crud.set_review_reviewer(s, "r1", "rev")
        a = await crud.get_assignment(s, "c1", "Android")
        zip_path = Path(a.source_zip_path)
        await crud.update_assignment(s, a, run_status="completed", review_id="r1")
    _as("reviewer", "rev")
    assert client.patch("/api/reviews/r1", json={"status": "approved"}).status_code == 200
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
    assert not zip_path.exists() and a.source_zip_path is None and a.source_zip_name == "android-app.zip"


async def test_deleting_a_project_removes_its_uploaded_zips(db):
    _as("project_manager", "pm")
    _upload()
    async with db() as s:
        zip_path = Path((await crud.get_assignment(s, "c1", "Android")).source_zip_path)
    _as("admin", "adm")
    assert client.delete("/api/projects/p1").status_code == 204
    assert not zip_path.exists() and not zip_path.parent.exists()
