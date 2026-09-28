# Microsoft SSO Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users sign in with their organization's Microsoft account, auto-provisioning a `role="user"` account on first sign-in, while keeping email/password login available as a fallback.

**Architecture:** A server-driven OAuth 2.0 Authorization Code flow against Microsoft Entra ID, using the `msal` library. The backend redirects the browser to Microsoft, receives the callback, exchanges the code for tokens server-to-server, and issues the app's existing session cookie (`create_access_token`) — the frontend never handles a Microsoft token.

**Tech Stack:** FastAPI, `msal` (Microsoft Authentication Library for Python), the existing JWT-cookie session mechanism (`app/auth/token.py`), React.

**Spec:** `docs/superpowers/specs/2026-09-28-microsoft-sso-design.md`

## Global Constraints

- Server-driven flow only — the frontend never sees a Microsoft token, only a full-page redirect.
- New/existing accounts are matched by email claim (`email`, falling back to `preferred_username`); an existing account's `role` is **never** changed by an SSO login.
- A first-time SSO login creates `role="user"`, `is_active=True`, `password_hash=""`.
- Single-tenant restriction is enforced by the Entra ID app registration itself, not application code.
- Password login stays fully functional — no removal, no endpoint changes to `/api/auth/login`.
- New env vars: `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET`, `AZURE_AD_REDIRECT_URI`, `FRONTEND_BASE_URL` (default `http://localhost:3000`).
- `msal==1.39.0` (latest stable, verified available via `pip index versions msal` at plan time).

---

### Task 1: Harden `verify_password` against a malformed hash

**Files:**
- Modify: `backend/app/auth/hashing.py`
- Test: `backend/tests/test_auth_hashing.py`

**Interfaces:**
- Produces: `verify_password(password: str, password_hash: str) -> bool` — now returns `False` instead of raising for any hash `bcrypt.checkpw` can't parse (e.g. `""`, used later for SSO-only accounts).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_auth_hashing.py`:

```python
def test_verify_password_returns_false_instead_of_raising_for_a_malformed_hash():
    assert verify_password("anything", "") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_hashing.py::test_verify_password_returns_false_instead_of_raising_for_a_malformed_hash -v`
Expected: FAIL with a `ValueError` raised from inside `bcrypt.checkpw`, not an assertion failure.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/auth/hashing.py`, replace the body of `verify_password`:

```python
def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_hashing.py -v`
Expected: PASS (all tests in the file, 5 total).

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/auth/hashing.py tests/test_auth_hashing.py
git commit -m "fix: verify_password returns False instead of raising on a malformed hash"
```

---

### Task 2: Add `app/auth/microsoft.py` (MSAL wrapper) and the `GET /api/auth/microsoft/login` endpoint

**Files:**
- Create: `backend/app/auth/microsoft.py`
- Create: `backend/tests/test_auth_microsoft.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_auth_api.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (for Task 3 to consume):
  - `app.auth.microsoft.get_authorization_url(state: str) -> str`
  - `app.auth.microsoft.exchange_code_for_claims(code: str) -> dict` — returns the ID token's claims dict on success; raises `ValueError` if Microsoft's response contains an `"error"` key.
  - `app.auth.microsoft.frontend_base_url() -> str` — reads `FRONTEND_BASE_URL`, defaulting to `"http://localhost:3000"`.
  - In `app/api/auth.py`: module-level import `from app.auth import microsoft as microsoft_auth`, and the constant `SSO_STATE_COOKIE = "sso_state"`.

- [ ] **Step 1: Add the `msal` dependency**

In `backend/requirements.txt`, add this line after `PyJWT==2.9.0`:

```
msal==1.39.0
```

Install it:

```bash
cd backend && source venv/bin/activate && pip install msal==1.39.0
```

- [ ] **Step 2: Write the failing tests for the MSAL wrapper module**

Create `backend/tests/test_auth_microsoft.py`:

```python
import pytest

import app.auth.microsoft as microsoft_module
from app.auth.microsoft import exchange_code_for_claims, get_authorization_url


class _FakeConfidentialClientApplication:
    def __init__(self, client_id, client_credential, authority):
        self.client_id = client_id
        self.client_credential = client_credential
        self.authority = authority

    def get_authorization_request_url(self, scopes, state, redirect_uri):
        return f"https://mock-authorize?scopes={','.join(scopes)}&state={state}&redirect_uri={redirect_uri}"

    def acquire_token_by_authorization_code(self, code, scopes, redirect_uri):
        if code == "bad-code":
            return {"error": "invalid_grant", "error_description": "The code is invalid or expired."}
        return {"access_token": "fake", "id_token_claims": {"email": "person@example.com"}}


@pytest.fixture
def fake_msal_app(monkeypatch):
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "mock-tenant")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "mock-client-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "mock-secret")
    monkeypatch.setenv("AZURE_AD_REDIRECT_URI", "http://localhost:8000/api/auth/microsoft/callback")
    monkeypatch.setattr(microsoft_module.msal, "ConfidentialClientApplication", _FakeConfidentialClientApplication)


def test_get_authorization_url_builds_a_url_with_the_given_state_and_configured_redirect_uri(fake_msal_app):
    url = get_authorization_url("state-123")

    assert "state=state-123" in url
    assert "redirect_uri=http://localhost:8000/api/auth/microsoft/callback" in url


def test_exchange_code_for_claims_returns_the_id_token_claims_on_success(fake_msal_app):
    claims = exchange_code_for_claims("good-code")

    assert claims == {"email": "person@example.com"}


def test_exchange_code_for_claims_raises_value_error_on_a_microsoft_error_result(fake_msal_app):
    with pytest.raises(ValueError, match="The code is invalid or expired."):
        exchange_code_for_claims("bad-code")


def test_frontend_base_url_defaults_when_not_set(monkeypatch):
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)

    assert microsoft_module.frontend_base_url() == "http://localhost:3000"


def test_frontend_base_url_reads_the_env_var_when_set(monkeypatch):
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://reviews.example.com")

    assert microsoft_module.frontend_base_url() == "https://reviews.example.com"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_microsoft.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth.microsoft'`.

- [ ] **Step 4: Write the MSAL wrapper module**

Create `backend/app/auth/microsoft.py`:

```python
import os

import msal

SCOPES = ["User.Read"]


def _tenant_id() -> str:
    return os.environ["AZURE_AD_TENANT_ID"]


def _client_id() -> str:
    return os.environ["AZURE_AD_CLIENT_ID"]


def _client_secret() -> str:
    return os.environ["AZURE_AD_CLIENT_SECRET"]


def _redirect_uri() -> str:
    return os.environ["AZURE_AD_REDIRECT_URI"]


def frontend_base_url() -> str:
    return os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=_client_id(),
        client_credential=_client_secret(),
        authority=f"https://login.microsoftonline.com/{_tenant_id()}",
    )


def get_authorization_url(state: str) -> str:
    return _msal_app().get_authorization_request_url(
        SCOPES, state=state, redirect_uri=_redirect_uri(),
    )


def exchange_code_for_claims(code: str) -> dict:
    """Exchanges an authorization code for tokens and returns the ID
    token's claims. Raises ValueError if Microsoft's response reports an
    error (e.g. an expired or already-used code)."""
    result = _msal_app().acquire_token_by_authorization_code(
        code, scopes=SCOPES, redirect_uri=_redirect_uri(),
    )
    if "error" in result:
        raise ValueError(result.get("error_description", result["error"]))
    return result["id_token_claims"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_microsoft.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Write the failing test for the login endpoint**

Add to `backend/tests/test_auth_api.py`, after the imports (add `import app.api.auth as auth_module` is already imported at the top — confirm it's there; it is) and anywhere after the existing tests:

```python
def test_microsoft_login_redirects_to_the_authorization_url_and_sets_a_state_cookie(test_sessionmaker, monkeypatch):
    captured = {}

    def fake_get_authorization_url(state):
        captured["state"] = state
        return "https://login.microsoftonline.com/mock-tenant/authorize?mock=1"

    monkeypatch.setattr(auth_module.microsoft_auth, "get_authorization_url", fake_get_authorization_url)

    response = client.get("/api/auth/microsoft/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://login.microsoftonline.com/mock-tenant/authorize?mock=1"
    assert response.cookies["sso_state"] == captured["state"]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_api.py::test_microsoft_login_redirects_to_the_authorization_url_and_sets_a_state_cookie -v`
Expected: FAIL with 404 (route doesn't exist) or `AttributeError: module 'app.api.auth' has no attribute 'microsoft_auth'`.

- [ ] **Step 8: Implement the login endpoint**

In `backend/app/api/auth.py`, change the import line:

```python
from fastapi import APIRouter, Depends, HTTPException, Response
```

to (adding `Request`):

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
```

Add a new import right after the existing `from app.db.session import new_session` line:

```python
import secrets

from fastapi.responses import RedirectResponse

from app.auth import microsoft as microsoft_auth
```

(Put `import secrets` with the other stdlib imports at the very top of the file, next to `import os`, per normal import ordering — stdlib first, then third-party, then local.)

Add this constant near `SEVEN_DAYS_SECONDS`:

```python
SSO_STATE_COOKIE = "sso_state"
SSO_STATE_MAX_AGE_SECONDS = 10 * 60
```

Add the new endpoint after the existing `login` endpoint:

```python
@router.get("/api/auth/microsoft/login")
async def microsoft_login():
    state = secrets.token_urlsafe(24)
    authorization_url = microsoft_auth.get_authorization_url(state)
    redirect_response = RedirectResponse(url=authorization_url)
    redirect_response.set_cookie(
        key=SSO_STATE_COOKIE, value=state, httponly=True, samesite="lax",
        secure=_cookie_secure(), max_age=SSO_STATE_MAX_AGE_SECONDS,
    )
    return redirect_response
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_api.py tests/test_auth_microsoft.py -v`
Expected: PASS (all tests, including the new one).

- [ ] **Step 10: Wire the new env vars into docker-compose.yml**

In `docker-compose.yml`, in the `backend` service's `environment:` block, add these lines after `- COOKIE_SECURE=false`:

```yaml
      - AZURE_AD_TENANT_ID=${AZURE_AD_TENANT_ID:-}
      - AZURE_AD_CLIENT_ID=${AZURE_AD_CLIENT_ID:-}
      - AZURE_AD_CLIENT_SECRET=${AZURE_AD_CLIENT_SECRET:-}
      - AZURE_AD_REDIRECT_URI=${AZURE_AD_REDIRECT_URI:-http://localhost:8000/api/auth/microsoft/callback}
      - FRONTEND_BASE_URL=http://localhost:3000
```

This follows the existing pattern in the file — secrets/tenant-specific values come from the root `.env` via `${VAR:-}` substitution (same as `AZURE_OPENAI_KEY`), while `FRONTEND_BASE_URL` is a plain local-dev default (same as `OLLAMA_BASE_URL`).

- [ ] **Step 11: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest`
Expected: PASS, no regressions (was 467 before this plan; should now be 467 + 1 hashing test + 5 microsoft tests + 1 login-endpoint test = 474).

- [ ] **Step 12: Commit**

```bash
cd backend
git add app/auth/microsoft.py app/api/auth.py requirements.txt tests/test_auth_microsoft.py tests/test_auth_api.py
git add ../docker-compose.yml
git commit -m "feat: add Microsoft SSO login endpoint (authorization redirect)"
```

---

### Task 3: `GET /api/auth/microsoft/callback` — token exchange, provisioning, session

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `microsoft_auth.exchange_code_for_claims(code) -> dict` and `microsoft_auth.frontend_base_url() -> str` (Task 2), `crud.get_user_by_email`, `crud.create_user` (both pre-existing in `app/db/crud.py`), `create_access_token` and `SSO_STATE_COOKIE`/`_cookie_secure`/`COOKIE_NAME`/`SEVEN_DAYS_SECONDS` (all already in `app/api/auth.py`).
- Produces: nothing further tasks depend on — this is the last backend task.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth_api.py`, after the Task 2 test:

```python
async def test_microsoft_callback_creates_a_new_role_user_account_for_an_unseen_email(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(
        auth_module.microsoft_auth, "exchange_code_for_claims",
        lambda code: {"email": "newperson@example.com"},
    )

    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:3000/"
    assert "access_token" in response.cookies

    async with test_sessionmaker() as session:
        user = await crud.get_user_by_email(session, "newperson@example.com")
    assert user.role == "user"
    assert user.is_active is True


async def test_microsoft_callback_reuses_an_existing_account_without_changing_its_role(test_sessionmaker, monkeypatch):
    await _create_user(test_sessionmaker, email="admin@example.com", password="whatever", role="admin")
    monkeypatch.setattr(
        auth_module.microsoft_auth, "exchange_code_for_claims",
        lambda code: {"email": "admin@example.com"},
    )

    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert "access_token" in response.cookies
    async with test_sessionmaker() as session:
        user = await crud.get_user_by_email(session, "admin@example.com")
    assert user.role == "admin"
    assert user.id == "u1"


async def test_microsoft_callback_falls_back_to_preferred_username_when_email_claim_is_absent(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(
        auth_module.microsoft_auth, "exchange_code_for_claims",
        lambda code: {"preferred_username": "upn@example.com"},
    )

    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert "access_token" in response.cookies
    async with test_sessionmaker() as session:
        user = await crud.get_user_by_email(session, "upn@example.com")
    assert user is not None


def test_microsoft_callback_redirects_to_error_when_state_does_not_match(test_sessionmaker):
    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "different"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:3000/login?error=sso_failed"


def test_microsoft_callback_redirects_to_error_when_no_state_cookie_present(test_sessionmaker):
    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "http://localhost:3000/login?error=sso_failed"


def test_microsoft_callback_redirects_to_error_when_microsoft_reports_an_error(test_sessionmaker):
    response = client.get(
        "/api/auth/microsoft/callback",
        params={"error": "access_denied"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "http://localhost:3000/login?error=sso_failed"


def test_microsoft_callback_redirects_to_error_when_token_exchange_fails(test_sessionmaker, monkeypatch):
    def fake_exchange(code):
        raise ValueError("invalid_grant")

    monkeypatch.setattr(auth_module.microsoft_auth, "exchange_code_for_claims", fake_exchange)

    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "http://localhost:3000/login?error=sso_failed"


async def test_microsoft_callback_blocks_an_inactive_existing_account(test_sessionmaker, monkeypatch):
    await _create_user(test_sessionmaker, email="gone@example.com", password="whatever", role="user")
    async with test_sessionmaker() as session:
        await crud.update_user(session, "u1", is_active=False)
    monkeypatch.setattr(
        auth_module.microsoft_auth, "exchange_code_for_claims",
        lambda code: {"email": "gone@example.com"},
    )

    response = client.get(
        "/api/auth/microsoft/callback",
        params={"code": "abc", "state": "xyz"},
        cookies={"sso_state": "xyz"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "http://localhost:3000/login?error=sso_failed"
    assert "access_token" not in response.cookies
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_api.py -k microsoft_callback -v`
Expected: FAIL — the route doesn't exist yet (404s / `KeyError: 'location'` since there's no redirect).

- [ ] **Step 3: Implement the callback endpoint**

Add `import uuid` at the top of `backend/app/api/auth.py` if not already present (check first — it is not, since this file currently has no `uuid` usage).

Add the endpoint at the end of `backend/app/api/auth.py`, after `microsoft_login`:

```python
@router.get("/api/auth/microsoft/callback")
async def microsoft_callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
):
    failure = RedirectResponse(url=f"{microsoft_auth.frontend_base_url()}/login?error=sso_failed")
    failure.delete_cookie(SSO_STATE_COOKIE)

    cookie_state = request.cookies.get(SSO_STATE_COOKIE)
    if error or not code or not state or not cookie_state or state != cookie_state:
        return failure

    try:
        claims = microsoft_auth.exchange_code_for_claims(code)
    except ValueError:
        return failure

    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        return failure

    async with new_session() as session:
        user = await crud.get_user_by_email(session, email)
        if user is None:
            user = await crud.create_user(
                session, user_id=str(uuid.uuid4()), email=email, password_hash="", role="user",
            )

    if not user.is_active:
        return failure

    token = create_access_token(user.id)
    success = RedirectResponse(url=f"{microsoft_auth.frontend_base_url()}/")
    success.delete_cookie(SSO_STATE_COOKIE)
    success.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, samesite="lax",
        secure=_cookie_secure(), max_age=SEVEN_DAYS_SECONDS,
    )
    return success
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_auth_api.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest`
Expected: PASS, no regressions (474 from Task 2, plus 8 new callback tests = 482).

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/api/auth.py tests/test_auth_api.py
git commit -m "feat: add Microsoft SSO callback endpoint with account linking and provisioning"
```

---

### Task 4: Frontend — "Sign in with Microsoft" on the login page

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/LoginPage.jsx`
- Modify: `frontend/src/pages/LoginPage.test.jsx`

**Interfaces:**
- Consumes: nothing from the backend tasks directly (frontend just links to a fixed URL path).
- Produces: `getMicrosoftLoginUrl(): string`, exported from `frontend/src/services/api.js`.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `frontend/src/pages/LoginPage.test.jsx` with:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "./LoginPage";
import { AuthContext } from "../context/AuthContext";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderWithAuth(loginImpl, initialEntries = ["/login"]) {
  const value = { user: null, loading: false, login: loginImpl, logout: jest.fn() };
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthContext.Provider value={value}>
        <LoginPage />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockNavigate.mockClear();
});

test("submitting valid credentials logs in and navigates to /", async () => {
  const user = userEvent.setup();
  const loginImpl = jest.fn().mockResolvedValue({ id: "u1", email: "a@example.com", role: "admin" });
  renderWithAuth(loginImpl);

  await user.type(screen.getByLabelText(/email/i), "a@example.com");
  await user.type(screen.getByLabelText(/password/i), "correct horse");
  await user.click(screen.getByRole("button", { name: /log in/i }));

  await waitFor(() => expect(loginImpl).toHaveBeenCalledWith("a@example.com", "correct horse"));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
});

test("shows the backend's error message on failed login and does not navigate", async () => {
  const user = userEvent.setup();
  const loginImpl = jest.fn().mockRejectedValue({ response: { data: { detail: "Incorrect email or password" } } });
  renderWithAuth(loginImpl);

  await user.type(screen.getByLabelText(/email/i), "a@example.com");
  await user.type(screen.getByLabelText(/password/i), "wrong");
  await user.click(screen.getByRole("button", { name: /log in/i }));

  expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test("shows a Sign in with Microsoft link pointing at the backend's Microsoft login route", async () => {
  renderWithAuth(jest.fn());

  const link = screen.getByRole("link", { name: /sign in with microsoft/i });
  expect(link).toHaveAttribute("href", expect.stringContaining("/auth/microsoft/login"));
});

test("shows an SSO failure message when the URL has error=sso_failed", async () => {
  renderWithAuth(jest.fn(), ["/login?error=sso_failed"]);

  expect(await screen.findByText(/microsoft sign-in failed/i)).toBeInTheDocument();
});

test("does not show an SSO failure message on a normal visit", async () => {
  renderWithAuth(jest.fn());

  expect(screen.queryByText(/microsoft sign-in failed/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/LoginPage.test.jsx --watchAll=false`
Expected: the 2 new tests FAIL (no Microsoft link / no error text exists yet); the 2 pre-existing tests still PASS.

- [ ] **Step 3: Add `getMicrosoftLoginUrl` to the API client**

In `frontend/src/services/api.js`, add this function right after `export function getDownloadUrl(downloadPath) { ... }`:

```javascript
export function getMicrosoftLoginUrl() {
  return `${API_BASE_URL}/auth/microsoft/login`;
}
```

- [ ] **Step 4: Update `LoginPage.jsx`**

Replace the full contents of `frontend/src/pages/LoginPage.jsx` with:

```jsx
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getMicrosoftLoginUrl } from "../services/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const ssoFailed = searchParams.get("error") === "sso_failed";

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "var(--color-bg)" }}>
      <form onSubmit={handleSubmit} className="card elev-sm" style={{ padding: 32, width: 360, display: "grid", gap: "var(--space-4)" }}>
        <div className="card-title" style={{ fontSize: 20 }}>Log in</div>
        <a href={getMicrosoftLoginUrl()} className="btn" style={{ textAlign: "center" }}>
          Sign in with Microsoft
        </a>
        {ssoFailed && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>Microsoft sign-in failed. Please try again.</p>}
        <div style={{ borderTop: "1px solid var(--color-divider)" }} />
        <div className="field">
          <label htmlFor="loginEmail">Email</label>
          <input
            id="loginEmail" type="email" className="input" value={email}
            onChange={(event) => setEmail(event.target.value)} required
          />
        </div>
        <div className="field">
          <label htmlFor="loginPassword">Password</label>
          <input
            id="loginPassword" type="password" className="input" value={password}
            onChange={(event) => setPassword(event.target.value)} required
          />
        </div>
        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/LoginPage.test.jsx --watchAll=false`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: PASS, no regressions (was 314 before this plan; should now be 317).

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/services/api.js src/pages/LoginPage.jsx src/pages/LoginPage.test.jsx
git commit -m "feat: add Sign in with Microsoft to the login page"
```

---

## After all tasks: deployment note (not a task — informational)

This feature requires a real Entra ID app registration before it works against live Microsoft accounts: an Azure admin needs to register an app, set its redirect URI to `AZURE_AD_REDIRECT_URI` (e.g. `http://localhost:8000/api/auth/microsoft/callback` for local dev), restrict it to single-tenant sign-in, and provide `AZURE_AD_TENANT_ID` / `AZURE_AD_CLIENT_ID` / `AZURE_AD_CLIENT_SECRET` via the root `.env` file. Until those are set, `GET /api/auth/microsoft/login` will raise a `KeyError` from `os.environ[...]` — acceptable for now since password login remains the fallback, but worth a quick manual smoke test once real credentials are available.
