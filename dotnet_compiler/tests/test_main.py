import io
import zipfile

from fastapi.testclient import TestClient

import main as main_module
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.sln", "stub")
        zf.writestr("MyApp/MyApp.csproj", "stub")
        zf.writestr("MyApp/Program.cs", "class Program {}")
    return buffer.getvalue()


def test_lint_endpoint_returns_ok_with_parsed_issues(monkeypatch):
    async def fake_run_build(project_dir):
        return {
            "returncode": 0,
            "stdout": "/src/MyApp/Program.cs(10,5): warning CS0168: The variable 'e' is declared but never used [/src/MyApp/MyApp.csproj]",
            "stderr": "",
        }

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{
            "severity": "Warning", "message": "The variable 'e' is declared but never used",
            "file": "/src/MyApp/Program.cs", "line": 10,
        }],
    }


def test_lint_endpoint_returns_ok_with_zero_warnings_on_a_clean_build(monkeypatch):
    async def fake_run_build(project_dir):
        return {"returncode": 0, "stdout": "Build succeeded.", "stderr": ""}

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "warning_count": 0, "issues": []}


def test_lint_endpoint_returns_ok_with_error_diagnostics_from_a_failed_build(monkeypatch):
    # A dotnet build that fails specifically due to real compiler errors
    # still produces parseable diagnostic lines -- those become real
    # "Error"-severity issues rather than a generic build_failed dead end.
    async def fake_run_build(project_dir):
        return {
            "returncode": 1,
            "stdout": "/src/MyApp/PaymentService.cs(42,13): error CS0103: The name 'foo' does not exist in the current context [/src/MyApp/MyApp.csproj]",
            "stderr": "",
        }

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["warning_count"] == 1
    assert body["issues"] == [{
        "severity": "Error", "message": "The name 'foo' does not exist in the current context",
        "file": "/src/MyApp/PaymentService.cs", "line": 42,
    }]


def test_lint_endpoint_returns_build_failed_with_the_captured_output_when_no_diagnostics_parsed(monkeypatch):
    async def fake_run_build(project_dir):
        return {"returncode": None, "stdout": "", "stderr": "No .sln or .csproj found."}

    monkeypatch.setattr(main_module, "run_build", fake_run_build)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "build_failed"
    assert body["warning_count"] is None
    assert body["issues"] == []
    assert "No .sln or .csproj found" in body["log"]


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
