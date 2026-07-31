import io
import zipfile

from fastapi.testclient import TestClient

import main as main_module
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.xcodeproj/project.pbxproj", "// stub")
        zf.writestr("MyApp/AppDelegate.swift", "class AppDelegate {}")
    return buffer.getvalue()


def _build_android_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("build.gradle", "android { compileSdkVersion 34 }")
        zf.writestr("src/main/java/Main.java", "class Main {}")
    return buffer.getvalue()


def test_lint_endpoint_returns_ok_with_parsed_issues(monkeypatch):
    async def fake_run_build(project_dir):
        return {
            "returncode": 0,
            "stdout": "/project/MyApp/AppDelegate.swift:12:5: warning: variable 'foo' was never used",
            "stderr": "",
        }

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{
            "severity": "Warning", "message": "variable 'foo' was never used",
            "file": "/project/MyApp/AppDelegate.swift", "line": 12,
        }],
    }


def test_lint_endpoint_returns_ok_with_zero_warnings_on_a_clean_build(monkeypatch):
    async def fake_run_build(project_dir):
        return {"returncode": 0, "stdout": "** BUILD SUCCEEDED **", "stderr": ""}

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "warning_count": 0, "issues": []}


def test_lint_endpoint_returns_build_failed_with_the_captured_xcodebuild_output(monkeypatch):
    async def fake_run_build(project_dir):
        # Simulates a failure with no parseable diagnostic (e.g. no scheme
        # could be discovered), proving the raw explanation is surfaced so
        # a failure is diagnosable instead of being a silent dead end.
        return {"returncode": None, "stdout": "", "stderr": "Could not discover a scheme via xcodebuild -list."}

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "build_failed"
    assert body["warning_count"] is None
    assert body["issues"] == []
    assert "Could not discover a scheme" in body["log"]


def test_android_lint_endpoint_returns_ok_with_parsed_issues(monkeypatch):
    async def fake_run_lint(project_dir):
        reports_dir = project_dir / "build" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "lint-results-debug.xml").write_text(
            '<issues format="6"><issue severity="Warning" message="m">'
            '<location file="f.java" line="1"/></issue></issues>'
        )
        return {"returncode": 0, "stdout": "BUILD SUCCESSFUL", "stderr": ""}

    monkeypatch.setattr(main_module, "run_android_lint", fake_run_lint)

    response = client.post(
        "/android-lint", files={"project": ("project.zip", _build_android_zip_bytes(), "application/zip")}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
    }


def test_android_lint_endpoint_returns_build_failed_with_the_captured_gradle_output(monkeypatch):
    async def fake_run_lint(project_dir):
        return {
            "returncode": 1,
            "stdout": "> Task :app:compileDebugJavaWithJavac FAILED",
            "stderr": "error: cannot find symbol",
        }

    monkeypatch.setattr(main_module, "run_android_lint", fake_run_lint)

    response = client.post(
        "/android-lint", files={"project": ("project.zip", _build_android_zip_bytes(), "application/zip")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "build_failed"
    assert body["warning_count"] is None
    assert body["issues"] == []
    assert "compileDebugJavaWithJavac FAILED" in body["log"]
    assert "cannot find symbol" in body["log"]


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
