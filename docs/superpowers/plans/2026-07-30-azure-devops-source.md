# Azure DevOps Repo as a Project Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reviewer supply the Android project either by uploading a `.zip` (today's only option) or by giving an Azure DevOps repo URL + Personal Access Token (PAT), with the backend fetching the repo directly from Azure DevOps's REST API and feeding it into the existing review pipeline unchanged from the "extracting" phase onward.

**Architecture:** A new `backend/app/analyzer/devops_client.py` module does one authenticated GET to Azure DevOps's Items REST API and returns the whole repo as zip bytes (no `git` binary needed). `reviews.py`'s `create_review` endpoint accepts three new optional form fields (`devopsRepoUrl`, `devopsPat`, `devopsBranch`) alongside making `androidZip` itself optional, validates that exactly one input method was given, and `_run_review` gains a new `"fetching"` phase (before `"extracting"`) that calls the new client and writes its result to the same `zip_path` used by the zip-upload path today. On the frontend, `UploadForm` gains a local, non-persisted toggle between "Upload files" and "Clone from Azure DevOps" that swaps the zip picker for three text fields, and its `onSubmit` contract changes to a single options object that `AndroidReviewFlow` and `services/api.js` thread straight through as new trailing multipart fields.

**Tech Stack:** FastAPI, httpx (async, already a dependency via `ollama_client.py`), pytest/pytest-asyncio (`asyncio_mode = auto`), React 19, Jest/React Testing Library.

## Global Constraints

- Only `https://dev.azure.com/{org}/{project}/_git/{repo}` URLs are supported this round — the older `https://{org}.visualstudio.com/...` form is out of scope; `parse_repo_url` returns `None` for it, same as any other unrecognized string.
- No `git clone`, no `git` binary in the backend container — fetch via the Items REST API's zip export only.
- The PAT is never persisted (no `localStorage`, no `state[...]`, no log line) anywhere, at any point — every field is entered fresh per review, exactly like today's file uploads.
- "Both provided" (zip file **and** DevOps fields on the same request) is a hard validation error, not a silent precedence rule.
- Validation error messages, verbatim: `"Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."` and `"Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."`
- The Excel template picker is unaffected by the source-mode toggle either way — a template is always required.
- Once `zip_path` holds real zip bytes (from either source), the `"extracting"` phase onward runs byte-for-byte the same code that runs today, with no awareness of which input method produced them.

---

## Task 1: `devops_client.py` — parse repo URLs and fetch a repo as a zip

**Files:**
- Create: `backend/app/analyzer/devops_client.py`
- Test: `backend/tests/test_devops_client.py`

**Interfaces:**
- Produces: `parse_repo_url(url: str) -> dict | None` returning `{"organization": str, "project": str, "repository": str}` or `None`.
- Produces: `async fetch_repo_zip(repo_url: str, pat: str, branch: str | None = None) -> dict` returning `{"status": "ok"|"invalid_url"|"unauthorized"|"not_found"|"error", "content": bytes|None, "message": str|None}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_devops_client.py`:

```python
import httpx
import pytest

from app.analyzer import devops_client


def test_parse_repo_url_extracts_org_project_repo():
    result = devops_client.parse_repo_url("https://dev.azure.com/myorg/MyProject/_git/my-repo")
    assert result == {"organization": "myorg", "project": "MyProject", "repository": "my-repo"}


def test_parse_repo_url_accepts_trailing_slash():
    result = devops_client.parse_repo_url("https://dev.azure.com/myorg/MyProject/_git/my-repo/")
    assert result == {"organization": "myorg", "project": "MyProject", "repository": "my-repo"}


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
        "?path=/&download=true&$format=zip&api-version=7.0&recursionLevel=full"
    )
    assert captured["auth"] == ("", "fake-pat")


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
async def test_fetch_repo_zip_returns_error_on_network_failure(monkeypatch):
    async def fake_get(self, url, auth=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await devops_client.fetch_repo_zip("https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat")

    assert result == {"status": "error", "content": None, "message": "Could not reach Azure DevOps."}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_devops_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analyzer.devops_client'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/analyzer/devops_client.py`:

```python
import re

import httpx

REPO_URL_RE = re.compile(r"^https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/?$")


def parse_repo_url(url: str) -> dict | None:
    """Extracts {organization, project, repository} from an Azure DevOps repo
    URL of the form https://dev.azure.com/{org}/{project}/_git/{repo}.
    Returns None if the URL doesn't match this shape.
    """
    match = REPO_URL_RE.match(url.strip())
    if not match:
        return None
    organization, project, repository = match.groups()
    return {"organization": organization, "project": project, "repository": repository}


async def fetch_repo_zip(repo_url: str, pat: str, branch: str | None = None) -> dict:
    """Downloads the given Azure DevOps repo (optionally at a specific branch)
    as a zip archive via one authenticated GET to the Items REST API -- no
    git binary needed. Returns {"status": "ok"|"invalid_url"|"unauthorized"|
    "not_found"|"error", "content": bytes|None, "message": str|None}. The PAT
    is used only for this one request's Basic auth header -- it never appears
    in the return value, in an exception message, or in a log line.
    """
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        return {"status": "invalid_url", "content": None, "message": "Not a recognized Azure DevOps repo URL."}

    url = (
        f"https://dev.azure.com/{parsed['organization']}/{parsed['project']}"
        f"/_apis/git/repositories/{parsed['repository']}/items"
        "?path=/&download=true&$format=zip&api-version=7.0&recursionLevel=full"
    )
    if branch:
        url += f"&versionDescriptor.version={branch}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, auth=("", pat))
        if response.status_code == 401:
            return {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}
        if response.status_code == 404:
            return {"status": "not_found", "content": None, "message": "Repository or branch not found."}
        response.raise_for_status()
        return {"status": "ok", "content": response.content, "message": None}
    except httpx.HTTPError:
        return {"status": "error", "content": None, "message": "Could not reach Azure DevOps."}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_devops_client.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/devops_client.py backend/tests/test_devops_client.py
git commit -m "feat: add devops_client for fetching Azure DevOps repos as zips"
```

---

## Task 2: `reviews.py` — exactly-one-input-method validation and the "fetching" phase

**Files:**
- Modify: `backend/app/api/reviews.py:1-131` (imports, `create_review`)
- Modify: `backend/app/api/reviews.py:134-146` (`_run_review` signature and body)
- Test: `backend/tests/test_reviews_create.py`

**Interfaces:**
- Consumes: `parse_repo_url(url: str) -> dict | None` and `async fetch_repo_zip(repo_url: str, pat: str, branch: str | None = None) -> dict` from Task 1.
- Produces: `create_review` now accepts `androidZip: UploadFile | None`, `devopsRepoUrl: str | None`, `devopsPat: str | None`, `devopsBranch: str | None`.
- Produces: `_run_review(..., devops_repo_url: str | None = None, devops_pat: str | None = None, devops_branch: str | None = None)` — three new trailing keyword params, defaulting to `None` so every existing call site keeps working unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reviews_create.py` (near the other `test_create_review_*` tests, after `test_create_review_write_failure_returns_200_with_error_state`):

```python
def test_create_review_returns_error_when_neither_zip_nor_devops_fields_provided(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        state = _reviews[body["review_id"]]
        assert state["error"] == "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."


def test_create_review_returns_error_when_both_zip_and_devops_fields_provided(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "devopsRepoUrl": "https://dev.azure.com/myorg/MyProject/_git/my-repo",
                "devopsPat": "fake-pat",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        state = _reviews[body["review_id"]]
        assert state["error"] == "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."


def test_create_review_with_devops_fields_derives_project_name_from_repo_url(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "devopsRepoUrl": "https://dev.azure.com/myorg/MyProject/_git/my-repo",
                "devopsPat": "fake-pat",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "processing"
        assert _reviews[body["review_id"]]["project_name"] == "my-repo"
```

Add to `backend/tests/test_reviews_create.py` (near the other `_run_review` tests, after `test_run_review_static_mode_skips_compiler_and_scores_1_4_via_llm`):

```python
async def test_run_review_fetching_phase_writes_zip_from_devops_on_success(monkeypatch):
    review_id = "devops-fetch-success"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": "ok", "content": _build_zip_bytes(), "message": None}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="my-repo",
        devops_repo_url="https://dev.azure.com/myorg/MyProject/_git/my-repo", devops_pat="fake-pat",
    )

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert "fetch_time_ms" in state["stats"]


async def test_run_review_fetching_phase_failure_ends_review_with_devops_error_message(monkeypatch):
    review_id = "devops-fetch-failure"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="my-repo",
        devops_repo_url="https://dev.azure.com/myorg/MyProject/_git/my-repo", devops_pat="secret-pat-value",
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["error"] == "Invalid PAT or insufficient permissions."
    assert "secret-pat-value" not in str(state)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_create.py -v`
Expected: FAIL — the three `create_review` tests fail because `androidZip` is currently required (`File(...)`) so posting without it returns a 422, and `devopsRepoUrl`/`devopsPat`/`devopsBranch` aren't accepted fields yet; the two `_run_review` tests fail with `TypeError: _run_review() got an unexpected keyword argument 'devops_repo_url'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/api/reviews.py`, update the import block to add `devops_client`:

```python
from app.analyzer.devops_client import fetch_repo_zip, parse_repo_url
```

(add this line alongside the existing `from app.analyzer.compile_checker import check_compile_warnings` import).

Replace `create_review` (currently `backend/app/api/reviews.py:90-131`) with:

```python
@router.post("/api/reviews")
async def create_review(
    androidZip: UploadFile | None = File(None),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
    compileCheckMode: str = Form("compiler"),
    platform: str = Form("Android"),
    devopsRepoUrl: str | None = Form(None),
    devopsPat: str | None = Form(None),
    devopsBranch: str | None = Form(None),
):
    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    has_zip = androidZip is not None
    has_devops = bool(devopsRepoUrl) and bool(devopsPat)

    if has_zip and has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."
    elif not has_zip and not has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."
    else:
        input_error = None

    if input_error:
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["message"] = "Review failed"
        state["error"] = input_error
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    try:
        if has_zip:
            zip_path.write_bytes(await androidZip.read())
        template_path.write_bytes(await excelTemplate.read())
    except Exception as exc:
        logger.exception("Review %s failed while saving uploads", review_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["message"] = "Review failed"
        state["error"] = f"Failed to save uploaded files: {exc}"
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    zip_valid = (androidZip.filename or "").endswith(".zip") if has_zip else True
    template_valid = (excelTemplate.filename or "").endswith(".xlsx")

    if has_zip:
        project_name = Path(androidZip.filename).stem if androidZip.filename else "Unknown Project"
    else:
        parsed = parse_repo_url(devopsRepoUrl)
        project_name = parsed["repository"] if parsed else "Unknown Project"

    state = _new_review_state()
    state["project_name"] = project_name
    _reviews[review_id] = state
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode, platform,
            devopsRepoUrl, devopsPat, devopsBranch,
        )
    )
    return {"review_id": review_id, "status": "processing"}
```

Update `_run_review`'s signature (currently `backend/app/api/reviews.py:134-146`) to add three trailing parameters:

```python
async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
    project_name: str,
    llm_provider: str = "azure",
    ollama_model: str | None = None,
    compile_check_mode: str = "compiler",
    platform: str = "Android",
    devops_repo_url: str | None = None,
    devops_pat: str | None = None,
    devops_branch: str | None = None,
) -> None:
```

Inside `_run_review`'s `try` block, immediately after the existing `zip_valid`/`template_valid` early-return check and before the `t0 = time.monotonic()` / `"extracting"` phase, insert the new `"fetching"` phase:

```python
        if devops_repo_url and devops_pat:
            t_fetch = time.monotonic()
            state["phase"] = "fetching"
            state["message"] = "Fetching repository from Azure DevOps..."
            fetch_result = await fetch_repo_zip(devops_repo_url, devops_pat, devops_branch)
            if fetch_result["status"] != "ok":
                state["status"] = "error"
                state["phase"] = "error"
                state["message"] = "Review failed"
                state["error"] = fetch_result["message"]
                return
            zip_path.write_bytes(fetch_result["content"])
            stats["fetch_time_ms"] = int((time.monotonic() - t_fetch) * 1000)
```

Everything else in `_run_review` (extracting onward) stays exactly as-is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_create.py -v`
Expected: PASS (all tests, including the pre-existing ones — no existing test passes `devops_repo_url`/`devops_pat`, so they keep skipping the new "fetching" branch unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py
git commit -m "feat: accept an Azure DevOps repo URL + PAT as an alternate project source"
```

---

## Task 3: End-to-end integration test for a DevOps-sourced review

**Files:**
- Test: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: the `create_review`/`_run_review` behavior from Task 2, monkeypatching `reviews_module.fetch_repo_zip` exactly as Task 2's unit tests do.

- [ ] **Step 1: Write the test**

Add to `backend/tests/test_reviews_integration.py` (after `test_full_review_pipeline_static_mode_scores_1_4_via_stub_llm`):

```python
async def test_full_review_pipeline_from_devops_source(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": "ok", "content": _build_zip_bytes(), "message": None}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "devopsRepoUrl": "https://dev.azure.com/myorg/MyProject/_git/my-repo",
                "devopsPat": "fake-pat",
            },
        )
        assert create_response.status_code == 200
        review_id = create_response.json()["review_id"]

        final_state = None
        for _ in range(50):
            progress_response = client.get(f"/api/reviews/{review_id}/progress")
            body = progress_response.json()
            if body["status"] in ("completed", "error"):
                final_state = body
                break
            time.sleep(0.05)

        assert final_state is not None, "review did not finish in time"
        assert final_state["status"] == "completed"
        assert final_state["project_name"] == "my-repo"
        assert final_state["compile_status"] == "ok"

        category_1 = next(c for c in final_state["category_scores"] if c["id"] == "1")
        sub_1_1 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.1")
        assert sub_1_1["score"] == 1
```

- [ ] **Step 2: No implementation needed**

This task adds coverage on top of Task 2's already-committed implementation — there is no new production code, so there is no red step here. Proceed straight to running it.

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd backend && venv/bin/python -m pytest tests/test_reviews_integration.py -v`
Expected: PASS (all tests, including the new one)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_reviews_integration.py
git commit -m "test: cover a full review pipeline sourced from Azure DevOps"
```

---

## Task 4: `UploadForm` — source toggle between Upload and Azure DevOps

**Files:**
- Modify: `frontend/src/components/UploadForm.jsx`
- Test: `frontend/src/components/UploadForm.test.jsx`

**Interfaces:**
- Produces: `onSubmit({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch })` — a single options object, replacing the old `onSubmit(androidZip, excelTemplate)` two-argument call. In upload mode, `devopsRepoUrl`/`devopsPat`/`devopsBranch` are `null`; in DevOps mode, `androidZip` is `null`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/UploadForm.test.jsx`, replace the first test's assertion:

```js
test("calls onSubmit with both files when extensions are valid", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: xlsx, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
  });
});
```

Add these new tests at the end of the file:

```js
test("defaults to upload mode with the zip picker visible and DevOps fields hidden", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/repo url/i)).not.toBeInTheDocument();
});

test("switching to Clone from Azure DevOps hides the zip picker and shows the DevOps fields", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  expect(screen.queryByLabelText(/android project/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/repo url/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/personal access token/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/branch/i)).toBeInTheDocument();
});

test("the Personal Access Token field is type=password", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));
  expect(screen.getByLabelText(/personal access token/i)).toHaveAttribute("type", "password");
});

test("disables the start button until repo URL, PAT, and template are all provided in DevOps mode", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/repo url/i), "https://dev.azure.com/myorg/MyProject/_git/my-repo");
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/personal access token/i), "fake-pat");
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  expect(screen.getByRole("button", { name: /start review/i })).toBeEnabled();
});

test("calls onSubmit with the DevOps fields (and a null androidZip) in DevOps mode", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  await user.type(screen.getByLabelText(/repo url/i), "https://dev.azure.com/myorg/MyProject/_git/my-repo");
  await user.type(screen.getByLabelText(/personal access token/i), "fake-pat");
  await user.type(screen.getByLabelText(/branch/i), "release/1.0");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: null,
    excelTemplate: xlsx,
    devopsRepoUrl: "https://dev.azure.com/myorg/MyProject/_git/my-repo",
    devopsPat: "fake-pat",
    devopsBranch: "release/1.0",
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx react-scripts test UploadForm --watchAll=false`
Expected: FAIL — the first test fails because `onSubmit` is still called with two positional args; the new tests fail because there's no "Clone from Azure DevOps" button or DevOps fields yet.

- [ ] **Step 3: Write the implementation**

Replace `frontend/src/components/UploadForm.jsx` in full:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";
import { FileIcon, ArrowRightIcon } from "../icons";
import { getCompileCheckMode, setCompileCheckMode } from "../services/compileCheckModeStorage";

export default function UploadForm({ onSubmit, disabled, disabledLabel = "Starting review…", showCompileCheckToggle = false }) {
  const [sourceMode, setSourceMode] = useState("upload"); // upload | devops
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [devopsRepoUrl, setDevopsRepoUrl] = useState("");
  const [devopsPat, setDevopsPat] = useState("");
  const [devopsBranch, setDevopsBranch] = useState("");
  const [validationError, setValidationError] = useState("");
  const [compileCheckMode, setCompileCheckModeState] = useState(() => getCompileCheckMode());

  function handleSubmit(event) {
    event.preventDefault();
    if (sourceMode === "upload") {
      if (!androidZip || !androidZip.name.endsWith(".zip")) {
        setValidationError("Android project must be a .zip file");
        return;
      }
    } else if (!devopsRepoUrl || !devopsPat) {
      setValidationError("Azure DevOps repo URL and PAT are both required");
      return;
    }
    if (!excelTemplate || !excelTemplate.name.endsWith(".xlsx")) {
      setValidationError("Review template must be a .xlsx file");
      return;
    }
    setValidationError("");
    onSubmit({
      androidZip: sourceMode === "upload" ? androidZip : null,
      excelTemplate,
      devopsRepoUrl: sourceMode === "devops" ? devopsRepoUrl : null,
      devopsPat: sourceMode === "devops" ? devopsPat : null,
      devopsBranch: sourceMode === "devops" ? (devopsBranch || null) : null,
    });
  }

  function handleSelectMode(mode) {
    setCompileCheckMode(mode);
    setCompileCheckModeState(mode);
  }

  const canStart =
    !!excelTemplate && (sourceMode === "upload" ? !!androidZip : !!devopsRepoUrl && !!devopsPat);

  return (
    <form onSubmit={handleSubmit} className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
      <CornerMarks />
      <div className="card-kicker">Step 1 of 2</div>
      <div className="card-title" style={{ fontSize: 20 }}>Upload project files</div>
      <p className="card-body">Both a project source and a template are required to start a review.</p>

      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
        <button
          type="button"
          className={`btn ${sourceMode === "upload" ? "btn-primary" : ""}`}
          disabled={disabled}
          onClick={() => setSourceMode("upload")}
        >
          Upload files
        </button>
        <button
          type="button"
          className={`btn ${sourceMode === "devops" ? "btn-primary" : ""}`}
          disabled={disabled}
          onClick={() => setSourceMode("devops")}
        >
          Clone from Azure DevOps
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginTop: "var(--space-5)" }}>
        {sourceMode === "upload" ? (
          <div className="field">
            <label htmlFor="androidZip">Android project (.zip)</label>
            <label className="input" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
              <FileIcon />
              {androidZip ? <span>{androidZip.name}</span> : <span style={{ opacity: 0.55 }}>Choose ZIP file…</span>}
              <input
                id="androidZip"
                type="file"
                accept=".zip"
                disabled={disabled}
                onChange={(event) => setAndroidZip(event.target.files[0] ?? null)}
                style={{ display: "none" }}
              />
            </label>
          </div>
        ) : (
          <div className="field" style={{ gridColumn: "1 / -1", display: "grid", gap: "var(--space-3)" }}>
            <div>
              <label htmlFor="devopsRepoUrl">Repo URL</label>
              <input
                id="devopsRepoUrl"
                type="text"
                className="input"
                placeholder="https://dev.azure.com/org/project/_git/repo"
                disabled={disabled}
                value={devopsRepoUrl}
                onChange={(event) => setDevopsRepoUrl(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="devopsPat">Personal Access Token</label>
              <input
                id="devopsPat"
                type="password"
                className="input"
                disabled={disabled}
                value={devopsPat}
                onChange={(event) => setDevopsPat(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="devopsBranch">Branch (optional)</label>
              <input
                id="devopsBranch"
                type="text"
                className="input"
                placeholder="default branch"
                disabled={disabled}
                value={devopsBranch}
                onChange={(event) => setDevopsBranch(event.target.value)}
              />
            </div>
          </div>
        )}
        <div className="field">
          <label htmlFor="excelTemplate">Scoring template (.xlsx)</label>
          <label className="input" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
            <FileIcon />
            {excelTemplate ? <span>{excelTemplate.name}</span> : <span style={{ opacity: 0.55 }}>Choose Excel file…</span>}
            <input
              id="excelTemplate"
              type="file"
              accept=".xlsx"
              disabled={disabled}
              onChange={(event) => setExcelTemplate(event.target.files[0] ?? null)}
              style={{ display: "none" }}
            />
          </label>
        </div>
      </div>

      {showCompileCheckToggle && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <p className="card-body" style={{ marginBottom: "var(--space-2)" }}>Clause 1.4 evaluation</p>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              className={`btn ${compileCheckMode === "compiler" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("compiler")}
            >
              Compile-time lint
            </button>
            <button
              type="button"
              className={`btn ${compileCheckMode === "static" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("static")}
            >
              Static file analysis
            </button>
          </div>
        </div>
      )}

      {validationError && <p className="card-body" style={{ color: "#b3261e" }}>{validationError}</p>}

      <button
        type="submit"
        className="btn btn-primary btn-block blueprint"
        style={{ marginTop: "var(--space-5)" }}
        disabled={disabled || !canStart}
      >
        <CornerMarks />
        {disabled ? disabledLabel : "Start review"}
        <ArrowRightIcon />
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx react-scripts test UploadForm --watchAll=false`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx
git commit -m "feat: add an Azure DevOps source toggle to the upload form"
```

---

## Task 5: Thread the DevOps fields through `AndroidReviewFlow` and `services/api.js`

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/AndroidReviewFlow.jsx:25-49`
- Test: `frontend/src/services/api.test.js`
- Test: `frontend/src/pages/AndroidReviewFlow.test.jsx`

**Interfaces:**
- Consumes: Task 4's `onSubmit({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch })` contract.
- Produces: `createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform, devopsRepoUrl, devopsPat, devopsBranch)` — three new trailing optional params, each omitted from the posted `FormData` when falsy (same pattern as the existing `llmProvider`/`ollamaModel`/`compileCheckMode`/`platform` fields). `androidZip` itself is now optional — omitted from `FormData` when `null`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/services/api.test.js`, add these two tests inside the `describe("createReview", ...)` block:

```js
  it("includes devops fields when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(
      null, xlsx, "azure", null, "compiler", "Android",
      "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", "release/1.0"
    );

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("androidZip")).toBeNull();
    expect(formData.get("devopsRepoUrl")).toBe("https://dev.azure.com/myorg/MyProject/_git/my-repo");
    expect(formData.get("devopsPat")).toBe("fake-pat");
    expect(formData.get("devopsBranch")).toBe("release/1.0");
  });

  it("omits devops fields when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("devopsRepoUrl")).toBeNull();
    expect(formData.get("devopsPat")).toBeNull();
    expect(formData.get("devopsBranch")).toBeNull();
  });
```

In `frontend/src/pages/AndroidReviewFlow.test.jsx`, update the four existing `createReview` assertions to include the three new trailing `null` args:

```js
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler", "Android", null, null, null);
```
```js
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android", null, null, null);
```
```js
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static", "Android", null, null, null);
```
```js
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "AndroidCustom", null, null, null);
```

(These are the same four assertions currently at lines 190, 212, 239, and 263 respectively — each just gains `, null, null, null` before its closing paren.)

Add this new test at the end of `frontend/src/pages/AndroidReviewFlow.test.jsx`:

```js
test("sends devops fields through to createReview when starting a review in DevOps mode", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "fetching", progress: 0, message: "Fetching...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));
  await user.type(screen.getByLabelText(/repo url/i), "https://dev.azure.com/myorg/MyProject/_git/my-repo");
  await user.type(screen.getByLabelText(/personal access token/i), "fake-pat");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);

  await act(async () => {
    await user.click(screen.getByRole("button", { name: /start review/i }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(
    null, xlsx, "azure", null, "compiler", "Android",
    "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", null
  );
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx react-scripts test api.test AndroidReviewFlow --watchAll=false`
Expected: FAIL — the new `api.test.js` tests fail because `createReview` doesn't accept the devops params yet; the updated `AndroidReviewFlow.test.jsx` assertions fail on arg-count mismatch (`handleUpload` still calls `onSubmit(androidZip, excelTemplate)` positionally, incompatible with Task 4's new object contract); the new DevOps-mode test fails because `handleUpload` doesn't destructure an options object yet.

- [ ] **Step 3: Write the implementation**

Replace `createReview` in `frontend/src/services/api.js`:

```js
export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch
) {
  const formData = new FormData();
  if (androidZip) formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  if (devopsRepoUrl) formData.append("devopsRepoUrl", devopsRepoUrl);
  if (devopsPat) formData.append("devopsPat", devopsPat);
  if (devopsBranch) formData.append("devopsBranch", devopsBranch);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

Replace `handleUpload` in `frontend/src/pages/AndroidReviewFlow.jsx:25-49`:

```jsx
  const handleUpload = useCallback(async ({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch }) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const models = await getOllamaModels().catch(() => []);
      const storedProvider = getLlmProvider();
      const effectiveProvider = storedProvider === "ollama" && models.length === 0 ? "azure" : storedProvider;
      const effectiveModel = effectiveProvider === "ollama" ? getOllamaModel() : null;
      const compileCheckMode = getCompileCheckMode();

      const result = await createReview(
        androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode, platform.label,
        devopsRepoUrl, devopsPat, devopsBranch
      );
      if (result.status === "error") {
        setErrorMessage(result.error || "Upload failed");
        setState("error");
        return;
      }
      setReviewId(result.review_id);
      setState("polling");
    } catch (err) {
      setErrorMessage("Failed to start review. Is the server running?");
      setState("error");
    }
  }, []);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx react-scripts test api.test AndroidReviewFlow UploadForm --watchAll=false`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js frontend/src/pages/AndroidReviewFlow.jsx frontend/src/pages/AndroidReviewFlow.test.jsx
git commit -m "feat: thread Azure DevOps source fields through the review flow"
```

---

## Final Verification

After all five tasks:

- [ ] Run the full backend suite: `cd backend && venv/bin/python -m pytest -v` — expect all tests passing, zero failures.
- [ ] Run the full frontend suite: `cd frontend && npx react-scripts test --watchAll=false` — expect all tests passing, zero failures.
- [ ] Rebuild and start docker-compose; manually verify in a browser: the toggle appears, switching to "Clone from Azure DevOps" swaps the zip picker for the three fields, the PAT field masks input, and (if a real Azure DevOps repo + PAT are available to test with) a DevOps-sourced review completes end to end and produces a downloadable workbook.
