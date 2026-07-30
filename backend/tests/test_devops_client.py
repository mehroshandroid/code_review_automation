import httpx
import pytest

from app.analyzer import devops_client


def test_parse_repo_url_extracts_org_project_repo():
    result = devops_client.parse_repo_url("https://dev.azure.com/myorg/MyProject/_git/my-repo")
    assert result == {"organization": "myorg", "project": "MyProject", "repository": "my-repo", "username": None}


def test_parse_repo_url_accepts_trailing_slash():
    result = devops_client.parse_repo_url("https://dev.azure.com/myorg/MyProject/_git/my-repo/")
    assert result == {"organization": "myorg", "project": "MyProject", "repository": "my-repo", "username": None}


def test_parse_repo_url_extracts_embedded_username():
    # Azure DevOps's own "Clone" URL and the URL shown after "Generate Git
    # Credentials" both embed the username as user@dev.azure.com.
    result = devops_client.parse_repo_url("https://myteo@dev.azure.com/myteo/MyMasjid/_git/My_Masjid_Android")
    assert result == {
        "organization": "myteo", "project": "MyMasjid", "repository": "My_Masjid_Android", "username": "myteo",
    }


def test_parse_repo_url_returns_none_for_unrecognized_url():
    assert devops_client.parse_repo_url("https://github.com/myorg/my-repo") is None
    assert devops_client.parse_repo_url("https://myorg.visualstudio.com/MyProject/_git/my-repo") is None
    assert devops_client.parse_repo_url("not a url") is None


@pytest.mark.asyncio
async def test_fetch_repo_zip_returns_invalid_url_status_without_making_a_request(monkeypatch):
    called = []

    async def fake_get(self, url, auth=None):
        called.append(url)
        raise AssertionError("should not be called for an invalid URL")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("not a url", "fake-pat")

    assert result == {"status": "invalid_url", "content": None, "message": "Not a recognized Azure DevOps repo URL."}
    assert called == []


@pytest.mark.asyncio
async def test_fetch_repo_zip_success_returns_zip_bytes(monkeypatch):
    captured = {}

    async def fake_get(self, url, auth=None):
        captured["url"] = url
        captured["auth"] = auth
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=200, content=b"PK\x03\x04fakezipbytes", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat")

    assert result == {"status": "ok", "content": b"PK\x03\x04fakezipbytes", "message": None}
    assert captured["url"] == (
        "https://dev.azure.com/myorg/MyProject/_apis/git/repositories/my-repo/items"
        "?scopePath=/&download=true&$format=zip&api-version=7.0&recursionLevel=full"
    )
    assert captured["auth"] == ("", "fake-pat")


@pytest.mark.asyncio
async def test_fetch_repo_zip_uses_the_url_embedded_username_for_basic_auth_when_present(monkeypatch):
    captured = {}

    async def fake_get(self, url, auth=None):
        captured["url"] = url
        captured["auth"] = auth
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=200, content=b"zipbytes", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip(
        "https://myteo@dev.azure.com/myteo/MyMasjid/_git/My_Masjid_Android", "fake-pat"
    )

    assert result["status"] == "ok"
    assert captured["auth"] == ("myteo", "fake-pat")
    assert captured["url"] == (
        "https://dev.azure.com/myteo/MyMasjid/_apis/git/repositories/My_Masjid_Android/items"
        "?scopePath=/&download=true&$format=zip&api-version=7.0&recursionLevel=full"
    )


@pytest.mark.asyncio
async def test_fetch_repo_zip_appends_branch_when_provided(monkeypatch):
    captured = {}

    async def fake_get(self, url, auth=None):
        captured["url"] = url
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=200, content=b"zipbytes", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await devops_client.fetch_repo_zip(
        "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", branch="release/1.0"
    )

    assert captured["url"].endswith("&versionDescriptor.version=release/1.0")


@pytest.mark.asyncio
async def test_fetch_repo_zip_returns_unauthorized_on_401(monkeypatch):
    async def fake_get(self, url, auth=None):
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=401, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "bad-pat")

    assert result == {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}


@pytest.mark.asyncio
async def test_fetch_repo_zip_returns_not_found_on_404(monkeypatch):
    async def fake_get(self, url, auth=None):
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=404, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip(
        "https://dev.azure.com/myorg/MyProject/_git/nonexistent-repo", "fake-pat"
    )

    assert result == {"status": "not_found", "content": None, "message": "Repository or branch not found."}


@pytest.mark.asyncio
async def test_fetch_repo_zip_returns_unauthorized_on_403(monkeypatch):
    # Azure DevOps commonly returns 403 (not 401) when a PAT / alternate
    # credential lacks the required scope, rather than being simply invalid.
    async def fake_get(self, url, auth=None):
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=403, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "scoped-pat")

    assert result == {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}


@pytest.mark.asyncio
async def test_fetch_repo_zip_includes_the_actual_status_code_for_unexpected_responses(monkeypatch):
    async def fake_get(self, url, auth=None):
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=500, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat")

    assert result["status"] == "error"
    assert result["content"] is None
    assert "500" in result["message"]


@pytest.mark.asyncio
async def test_fetch_repo_zip_includes_azure_devops_own_error_text_when_present(monkeypatch):
    async def fake_get(self, url, auth=None):
        request = httpx.Request("GET", url)
        return httpx.Response(
            status_code=400,
            content=b'{"message": "TF401019: The Git repository does not contain any commits."}',
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat")

    assert result["status"] == "error"
    assert "400" in result["message"]
    assert "TF401019" in result["message"]


@pytest.mark.asyncio
async def test_fetch_repo_zip_returns_error_on_network_failure(monkeypatch):
    async def fake_get(self, url, auth=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat")

    assert result == {"status": "error", "content": None, "message": "Could not reach Azure DevOps."}
