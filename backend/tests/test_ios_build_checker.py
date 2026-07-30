import httpx
import pytest

from app.analyzer import ios_build_checker


@pytest.mark.asyncio
async def test_returns_parsed_result_on_success(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "status": "ok",
                "warning_count": 1,
                "issues": [{"severity": "Warning", "message": "m", "file": "f", "line": 1}],
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ios_build_checker.check_ios_build_warnings(zip_path)

    assert result == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f", "line": 1}],
    }


@pytest.mark.asyncio
async def test_returns_unavailable_on_connection_error(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ios_build_checker.check_ios_build_warnings(zip_path)

    assert result == {"status": "unavailable", "warning_count": None, "issues": []}


@pytest.mark.asyncio
async def test_returns_unavailable_on_non_2xx_response(monkeypatch, tmp_path):
    zip_path = tmp_path / "project.zip"
    zip_path.write_bytes(b"fake zip bytes")

    async def fake_post(self, url, files=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=500, json={"error": "boom"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ios_build_checker.check_ios_build_warnings(zip_path)

    assert result == {"status": "unavailable", "warning_count": None, "issues": []}
