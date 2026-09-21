# Authentication & Role-Based Access Control — Design

## Problem

This app currently has zero authentication or user-identity infrastructure
anywhere: no user table, no session/JWT handling, no login page, no
frontend auth state. Every API endpoint is open to anyone who can reach
it. We need email/password login plus a three-role permission system
(admin / reviewer / user) covering every existing action, so the right
people can do the right things and everyone else is read-only.

Microsoft SSO is an explicit non-goal here — it's a separate, self-contained
follow-up project once the account/role model exists to map SSO identities
onto. (For the record: Azure AD/Entra ID app registration for basic
single-tenant OAuth/OIDC doesn't require a verified custom domain — a
redirect URI can point at `http://localhost:3000/...` using a free/trial
tenant. Domain verification only matters for publishing to the multi-tenant
app gallery or custom-domain federation, neither of which applies here.)

## Roles and permission matrix

Three roles: `admin`, `reviewer`, `user`. Everything requires a logged-in
session — nothing is reachable anonymously except `GET /api/health` and the
login endpoint itself.

| Action | Admin | Reviewer | User |
|---|:-:|:-:|:-:|
| View dashboard / reviews / projects / chatbot (all read-only GETs, `POST /api/chat`) | ✓ | ✓ | ✓ |
| Create a project (`POST /api/projects`, including the inline "add new" dialog during review start/upload) | ✓ | ✓ | ✓ |
| Start an automated review (`POST /api/reviews`) / upload a completed review (`POST /api/reviews/upload`) | ✓ | ✓ | ✓ |
| List Ollama models (`GET /api/ollama/models`, supports the review-start flow) | ✓ | ✓ | ✓ |
| Rename a project (`PATCH /api/projects/{id}`) | ✓ | ✗ | ✗ |
| Edit review scores / change review status (`PATCH /api/reviews/{id}`) | ✓ | ✓ | ✗ |
| View/edit org-wide settings — LLM provider defaults, clause checklists, sample templates (all `/api/settings/*`) | ✓ | ✓ | ✗ |
| Manage users — create, deactivate, change role (`/api/users/*`, new) | ✓ | ✗ | ✗ |

"Project status" in the original request refers to a review's own
`status` field (`pending_approval` → `approved`) via the existing
`PATCH /api/reviews/{id}` — projects themselves have no separate status
field, and this design doesn't add one.

## Data model

New `User` table:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "admin" | "reviewer" | "user"
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

A new Alembic migration creates this table. `is_active=False` is how an
admin deactivates an account without deleting it (preserves any
`created_by`/`approved_by` review history referencing that email).

## Backend architecture

**New `app/auth/` package:**
- `hashing.py` — `hash_password(plain) -> str` / `verify_password(plain, hashed) -> bool`, using the `bcrypt` library directly (added to `requirements.txt`; `passlib` is effectively unmaintained, `bcrypt` alone is simpler and actively maintained).
- `jwt.py` — `create_access_token(user) -> str` (encodes `{sub: user.id, role: user.role, exp}`) / `decode_access_token(token) -> dict`, using `PyJWT` (added to `requirements.txt`), signed with an `AUTH_SECRET_KEY` env var, 7-day expiry (this is a regularly-used internal tool — no refresh-token complexity, just re-login after a week).
- `dependencies.py` — FastAPI dependencies: `get_current_user(request) -> User` (reads the `access_token` cookie, decodes it, loads the `User` row, raises `401` if missing/invalid/inactive) and `require_roles(*roles)` (a dependency factory returning `403` if `current_user.role` isn't in the allowed set).

**New `app/api/auth.py` router:**
- `POST /api/auth/login` — body `{email, password}`; verifies against the `User` row, sets the JWT as an `httpOnly`, `SameSite=Lax` cookie named `access_token` (`Secure` flag driven by a `COOKIE_SECURE` env var, default `false` for this app's current plain-HTTP deployment — flip to `true` the day it's served over HTTPS). Returns `401` on bad credentials or an inactive account.
- `POST /api/auth/logout` — clears the cookie.
- `GET /api/auth/me` — returns `{id, email, role}` for the current session; `401` if not logged in. The frontend calls this once on mount to bootstrap auth state.

**New `app/api/users.py` router (all endpoints gated `require_roles("admin")`):**
- `GET /api/users` — list all users (id/email/role/is_active/created_at, never password_hash).
- `POST /api/users` — create a user (email/password/role). Password must be at least 8 characters (the only validation rule — no complexity requirements); `400` otherwise.
- `PATCH /api/users/{id}` — change role and/or `is_active`.

**Existing routers** (`projects.py`, `reviews.py`, `settings.py`, `ollama.py`, `chat.py`) each get `Depends(get_current_user)` (all endpoints) and `Depends(require_roles(...))` added per the matrix above, on exactly the endpoints the matrix restricts.

**`main.py`:** `CORSMiddleware` gains `allow_credentials=True` (origin is already the exact `http://localhost:3000`, not a wildcard, so this is compatible). A startup hook checks whether the `users` table is empty; if so and `ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars are set, it creates one seeded admin account. If those env vars aren't set, it logs a warning and continues rather than crashing the app (so existing local/CI flows that don't care about auth yet aren't broken by its mere presence). `docker-compose.yml` gains `ADMIN_EMAIL`/`ADMIN_PASSWORD`/`AUTH_SECRET_KEY` entries for this dev stack.

## Frontend architecture

- `LoginPage.jsx` — email/password form (reusing the existing `.card`/`.field`/`.input`/`.btn` design-system classes), `POST /api/auth/login`, navigates to `/` on success, shows the backend's error message on failure.
- `AuthContext.jsx` — a React context providing `{user, loading, login, logout}`. On mount, calls `GET /api/auth/me`; `user` is `null` until that resolves (or stays `null` on `401`).
- `AppRoutes.jsx` — a `RequireAuth` wrapper redirects to `/login` when `user` is `null` (after loading finishes); a `RequireRole` wrapper (used for `/settings` and a new `/users` admin page) redirects to `/` when the user's role isn't allowed.
- `services/api.js` — `axios.defaults.withCredentials = true`, plus a response interceptor that redirects to `/login` on any `401`.
- Nav bar shows the logged-in user's email + a "Log out" button.
- Role-driven UI: the Settings nav link and the new Users-management link are hidden for `user`-role accounts (and the Users link hidden for `reviewer` too); `ReviewReportPage`'s score-edit controls are hidden for `user`-role accounts; `DashboardFilters`' project-rename button is hidden for non-admins.
- New `UsersPage.jsx` at `/users` (admin-only) — a simple table of users with an "Add user" dialog and per-row role/active toggles, calling the new `/api/users` endpoints. Linked from its own nav entry, visible only to admins (kept separate from the Settings link since reviewers can reach Settings but not user management).

## Testing consequence (called out explicitly, not hidden)

Nearly every existing backend endpoint test currently calls the API with
no authentication at all. Locking down each router means every one of
those test files needs an authenticated test-client fixture (a helper
that logs in a seeded test user and carries the resulting cookie) added
alongside its existing tests. This is a large, mechanical chunk of the
work — real effort, not incidental. New tests are also needed for: password
hashing round-trip, JWT creation/expiry/tampering, the login/logout/me
endpoints, the admin-only users endpoints, per-role enforcement on every
restricted existing endpoint (403 for the wrong role, 200 for the right
one), the admin-seeding startup behavior (both when env vars are set and
when they aren't), and the new frontend pieces (`LoginPage`, `AuthContext`,
route guards, role-driven UI hiding).

## Out of scope

- Microsoft SSO (separate future project, as discussed above).
- Password reset / "forgot password" flow (not requested; an admin can
  reassign a password via the new user-management endpoints in the
  meantime).
- Refresh tokens / "remember me" (7-day JWT expiry is simple and sufficient
  for an internal tool with regular use).
- Project-level status field (the "project status" language in the
  original request maps to the existing review-level status, per above).
