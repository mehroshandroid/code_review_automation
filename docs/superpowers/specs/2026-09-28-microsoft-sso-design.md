# Microsoft SSO Login — Design

## Problem

The app currently only supports email/password login (see
`2026-08-25-auth-rbac-design.md`, which explicitly deferred SSO as a
follow-up once the account/role model existed). We now want to let users
sign in with their organization's Microsoft account instead of a
password. A first-time Microsoft sign-in should auto-provision a `user`
-role account; an admin then promotes them to `reviewer`/`admin` through
the existing User Management UI, exactly as they would for a
password-created account. Password login stays available as a
break-glass fallback.

## Scope

- Add a Microsoft Entra ID (Azure AD) OAuth 2.0 Authorization Code flow,
  driven entirely server-side.
- Auto-provision a `role="user"` account on first SSO sign-in by a new
  email; reuse (and never modify the role of) an existing account when
  the SSO email matches one already on file.
- Add a "Sign in with Microsoft" option to the login page, alongside the
  existing password form.
- Fix a latent bug in `verify_password` that this feature would otherwise
  hit in production (see below).

**Out of scope:** calling the Microsoft Graph API for anything beyond the
sign-in identity claims, storing Microsoft's own tokens, multi-tenant or
personal-Microsoft-account sign-in, and removing password login.

## Approach: server-driven Authorization Code flow

The browser is redirected to Microsoft's login page by the backend;
Microsoft redirects back to a backend callback with an authorization
code; the backend exchanges that code for tokens **server-to-server**
(using the app registration's client secret) via Microsoft's official
`msal` Python library, validates the returned ID token, and then issues
the **same** session cookie the password-login path already issues via
`create_access_token`. The frontend never sees a Microsoft token — after
a successful sign-in it's simply redirected to `/`, already logged in,
same as after a password login.

This was chosen over driving the OAuth flow from the browser with
MSAL.js (which would hand the frontend a Microsoft ID token to POST to
the backend for verification): the app's session model is already
cookie-based, not bearer-token-based, so a browser-driven flow would mean
running two different session mechanisms side by side for no benefit,
plus the added complexity of a public-client PKCE flow. The backend
already exists and can hold a client secret, so there's no reason not to
use a confidential-client flow.

## Data model — no schema change

`User` already has every column this needs. On a successful callback:

1. Look up `User` by the email claim from Microsoft's ID token.
2. **If found:** reuse that row as-is. Role, `is_active`, and everything
   else is left untouched — this is what makes an existing
   `admin@example.com` password account keep its admin role if that same
   person later signs in via SSO with the same email.
3. **If not found:** create a new row — `role="user"`, `is_active=True`,
   `password_hash=""`. An empty hash can never match any real password
   (see the `verify_password` fix below), which is what makes the account
   SSO-only until/unless an admin later sets a password for it via the
   existing `PATCH /api/users/{id}` (already supports setting `password`).

Microsoft's ID token exposes the signed-in user's email via the `email`
claim (requested via the `email` OIDC scope) — `preferred_username` is
used as a fallback for tenants that omit `email`.

## Backend

### New endpoints (`app/api/auth.py`)

**`GET /api/auth/microsoft/login`**
- Builds the Microsoft authorize URL via
  `msal.ConfidentialClientApplication.get_authorization_request_url()`,
  requesting the `email` scope (`openid`/`profile` are implicit).
- Generates a random CSRF `state` value, stores it in a short-lived
  cookie (`sso_state`, httponly, `samesite=lax`, `secure` set via the same
  `_cookie_secure()` check the session cookie already uses, a few
  minutes' max-age).
- Redirects (307) to the Microsoft authorize URL.

**`GET /api/auth/microsoft/callback`**
- Reads `code` and `state` from the query string, and the `sso_state`
  cookie.
- If `state` doesn't match the cookie (or the cookie is missing), or
  Microsoft returned an `error` query param, or the token exchange fails:
  clears the `sso_state` cookie and redirects to
  `{FRONTEND_BASE_URL}/login?error=sso_failed`.
- Otherwise exchanges `code` for tokens via
  `msal.ConfidentialClientApplication.acquire_token_by_authorization_code()`,
  reads the email claim from `id_token_claims`, upserts/links the `User`
  row per the Data Model section above, and — if `is_active` is `False`
  — redirects to `{FRONTEND_BASE_URL}/login?error=sso_failed` instead of
  logging them in (same rule password login already enforces).
- On success: clears `sso_state`, sets the normal session cookie via
  `create_access_token(user.id)` (identical to the password-login path),
  redirects (307) to `{FRONTEND_BASE_URL}/`.

### New config (env vars, following this repo's existing pattern of plain
`os.environ.get(...)` reads with sane local-dev defaults where possible)

| Var | Purpose |
|---|---|
| `AZURE_AD_TENANT_ID` | Entra ID tenant to restrict sign-in to (single-tenant app registration) |
| `AZURE_AD_CLIENT_ID` | App registration's client ID |
| `AZURE_AD_CLIENT_SECRET` | App registration's client secret |
| `AZURE_AD_REDIRECT_URI` | Must exactly match the redirect URI registered in Entra ID, e.g. `http://localhost:8000/api/auth/microsoft/callback` for local dev |
| `FRONTEND_BASE_URL` | Where to send the browser after success/failure; defaults to `http://localhost:3000` (matches the existing hardcoded CORS origin in `main.py`) |

Tenant restriction to the org's own directory is enforced by Microsoft
itself (a single-tenant app registration only accepts sign-ins from that
tenant) — no additional domain-allowlist code is needed on our side.

### Fix: `verify_password` crashes on a malformed hash

`app/auth/hashing.py::verify_password` calls `bcrypt.checkpw()` directly,
which raises `ValueError` for a hash that isn't valid bcrypt output (e.g.
the `""` this design stores for SSO-only accounts) instead of returning
`False`. Today this can't happen because every existing `password_hash`
comes from `hash_password()`. Once SSO-provisioned accounts with
`password_hash=""` exist, anyone who tried the password form against one
of those accounts would hit an unhandled `ValueError` — a 500 instead of
a clean 401. Fix: catch `ValueError` in `verify_password` and return
`False`.

## Frontend

- `LoginPage.jsx`: add a "Sign in with Microsoft" button below the
  existing password form, separated by a divider. Clicking it performs a
  full browser navigation — `window.location.href =
  `${API_BASE_URL}/auth/microsoft/login`` — not an axios call, since the
  browser needs to actually leave the SPA to reach Microsoft's login
  page.
- On success, the backend redirects straight to `/`; the existing
  `AuthContext` (unchanged) picks up the new session on its normal
  `GET /api/auth/me` mount-time call.
- On failure, the backend redirects to `/login?error=sso_failed`;
  `LoginPage` reads that query param (via `useSearchParams`) on mount and
  shows "Microsoft sign-in failed. Please try again." in the same error
  slot the password form already uses.
- No changes to `UsersPage.jsx` — promoting an auto-provisioned SSO user
  to `reviewer`/`admin` uses the exact same admin UI that already exists
  for password-created accounts.

## Testing

**Backend** — mock the `msal.ConfidentialClientApplication` boundary
entirely; no real Microsoft calls in tests.
- `GET /api/auth/microsoft/login` sets the `sso_state` cookie and
  redirects to a URL containing the configured tenant/client id.
- `GET /api/auth/microsoft/callback` with a valid code+matching state and
  an unseen email creates a new `role="user"`, `is_active=True` account
  and sets the session cookie.
- The same, for an email that already exists as a password account,
  reuses that row and does **not** change its existing role.
- Mismatched or missing `state` redirects to the `sso_failed` error URL
  without raising.
- An existing but `is_active=False` account is blocked (redirected to the
  error URL), same as password login.
- `verify_password` returns `False` (not a raised exception) for an
  empty/malformed hash.

**Frontend**
- `LoginPage` renders the Microsoft sign-in button pointing at
  `{API_BASE_URL}/auth/microsoft/login`.
- `LoginPage` shows the SSO error message when the URL has
  `?error=sso_failed`.
- Existing password-login tests are unaffected.
