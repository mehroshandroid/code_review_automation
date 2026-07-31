# Azure DevOps Repo as a Project Source — Design Spec

**Status:** Approved
**Date:** 2026-07-30
**Source:** "we have our codes hosted on azure devops, if i provide the repo url and PAT , is it possible to pull the code directly from repo ? i want to give the option to either upload the project or clone from the devops repo"

## Purpose

Today the only way to supply the Android project is a manual `.zip` upload. This adds a second input method: an Azure DevOps repository URL + Personal Access Token (PAT), optionally with a specific branch. The backend fetches the repo directly from Azure DevOps via its REST API (as a zip archive) instead of requiring a manual export/zip/upload step, and feeds it into the exact same review pipeline. The reviewer picks whichever method is more convenient per review, on the same upload form.

## Out of Scope

- Any other git host (GitHub, GitLab, Bitbucket) — Azure DevOps only, for now.
- `git clone`/full history/submodules — the Items REST API's zip export is sufficient and avoids needing a `git` binary in the backend container at all.
- Persisting the repo URL, PAT, or branch anywhere (`localStorage` or otherwise) — every field is entered fresh per review, matching how file uploads already work today.
- TLS/transport hardening beyond what the app already has — this is a local/team tool running over the existing docker-compose network; production-grade credential transport is a separate concern if this tool is ever deployed beyond that.

## 1. Backend: `devops_client.py`

New module, following the existing dict-result, never-raises style already used by `ollama_client.py` and `compile_checker.py`:

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

## 2. `reviews.py`: exactly-one-input-method validation, a new "fetching" phase

`create_review` gains three new optional form fields and makes the zip upload itself optional:

```python
androidZip: UploadFile | None = File(None),
...
devopsRepoUrl: str | None = Form(None),
devopsPat: str | None = Form(None),
devopsBranch: str | None = Form(None),
```

Validation (mirroring today's `zip_valid`/`template_valid` early-error pattern): exactly one input method must be present — `androidZip` alone, or `devopsRepoUrl` + `devopsPat` together. Neither, or both, is an immediate error state (`"Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."` / `"...not neither."`), returned the same way today's save-failure branch is.

`project_name` is derived from whichever input method was used: `Path(androidZip.filename).stem` as today when a zip was uploaded; otherwise the `repository` segment parsed from `devopsRepoUrl` (falling back to `"Unknown Project"` if the URL doesn't parse — though by validation time it's already known to parse, since that's part of what "exactly one input method" checks).

When a zip was uploaded, `zip_path` is written exactly as today, before dispatching the background task. When DevOps fields were used instead, `zip_path` is *not* written yet — `_run_review` gains a new phase, `"fetching"`, inserted before `"extracting"`, that calls `devops_client.fetch_repo_zip(devops_repo_url, devops_pat, devops_branch)` and writes the returned `content` bytes to that same `zip_path`. A non-`"ok"` result ends the review immediately with `state["error"]` set to the returned `message` — the PAT itself is never placed into `state` or logged anywhere, at any point in this flow. Once `zip_path` holds real zip bytes (from either source), the `"extracting"` phase onward is byte-for-byte the same code that runs today, with no awareness of which input method produced them.

## 3. Frontend: `UploadForm` source toggle

A new toggle, local `UploadForm` state (not persisted): `"upload"` (default) vs `"devops"`. In `"upload"` mode, the form looks exactly as it does today. In `"devops"` mode, the "Android project (.zip)" file picker is replaced by three fields: Repo URL (text), Personal Access Token (`type="password"`), Branch (text, optional, placeholder like "default branch"). The "Scoring template (.xlsx)" picker is unaffected by this toggle either way — a template is always required.

`onSubmit`'s contract changes from `(androidZip, excelTemplate)` to a single options object: `onSubmit({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch })`, with `androidZip` populated in upload mode and the three `devops*` fields populated in DevOps mode (the unused set stays `null`/`undefined`). `canStart` (gating the submit button) becomes: `excelTemplate` always required, plus either `androidZip` (upload mode) or `devopsRepoUrl && devopsPat` (DevOps mode, branch optional).

`AndroidReviewFlow.handleUpload` and `createReview` (`services/api.js`) are updated to accept and forward the same fields, appended as new optional multipart form fields alongside the existing `llmProvider`/`ollamaModel`/`compileCheckMode`/`platform`.

## Testing

- **Backend**: new `test_devops_client.py` — `parse_repo_url` on a valid URL, an invalid/unrecognized URL, and a URL with a trailing slash; `fetch_repo_zip` success (mocked 200 response), unauthorized (401), not-found (404), and a network-error case, each via the same `httpx.AsyncClient` monkeypatch style already used in `test_ollama_client.py`. Extend `test_reviews_create.py` for: the exactly-one-input-method validation (neither provided, both provided), the new `"fetching"` phase populating `zip_path` correctly on success, and a fetch-failure case ending the review with the right `state["error"]` and never touching `state` with the PAT value. Extend `test_reviews_integration.py` with one end-to-end DevOps-sourced review (mocking `devops_client.fetch_repo_zip` to return a real fixture zip's bytes), proving the rest of the pipeline runs unchanged.
- **Frontend**: extend `UploadForm.test.jsx` for the toggle's default/switch behavior, the three DevOps fields appearing/disappearing, the PAT field's `type="password"`, and `canStart`'s two gating conditions. Extend `AndroidReviewFlow.test.jsx` and `api.test.js` for the new fields being threaded through `createReview`.

## Ambiguity resolved during self-review

- "Both provided" (a zip file *and* DevOps fields on the same request) is treated as a validation error, not a silent precedence rule (e.g. "zip wins") — an ambiguous request should fail loudly rather than guess which source the reviewer actually meant.
- The Azure DevOps URL format supported is exactly `https://dev.azure.com/{org}/{project}/_git/{repo}` (the current standard form) — the older `https://{org}.visualstudio.com/...` form is not supported in this round; `parse_repo_url` returning `None` for it produces the same clear "not a recognized URL" error as any other malformed input, not a crash.
