import datetime as _dt

import pytest

import app.api.reviews as reviews_module
from app.auth.dependencies import get_current_user
from app.db.models import User
from main import app as _app

_DEFAULT_TEST_USER = User(
    id="test-admin", email="test-admin@example.com", role="admin",
    is_active=True, password_hash="", created_at=_dt.datetime.now(_dt.timezone.utc),
)


@pytest.fixture(autouse=True)
def _stub_persist_review_result(monkeypatch):
    """DB persistence is opt-in per test -- most existing tests exercise the
    review pipeline without any test database configured, and the real
    _persist_review_result would otherwise attempt (and fail/log) a
    connection to the production DATABASE_URL default on every single one.
    Tests that specifically cover persistence override this with their own
    monkeypatch.setattr call.
    """
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(reviews_module, "_persist_review_result", _noop)


@pytest.fixture(autouse=True)
def _stub_load_clause_checklists(monkeypatch):
    """Same rationale as _stub_persist_review_result above -- most existing
    tests don't configure a test database, so the real _load_clause_checklists
    would otherwise attempt a real DB connection on every review. Tests that
    specifically cover checklist wiring override this with their own
    monkeypatch.setattr call.
    """
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", _empty)


@pytest.fixture(autouse=True)
def _default_authenticated_user():
    """Every existing test was written before auth existed and expects full
    access -- default every test to a fake admin via FastAPI's dependency
    override mechanism (not a real login/cookie), so locking down a router
    in a later task doesn't require touching that router's existing tests.
    Tests that specifically cover permission enforcement override this
    themselves (see e.g. test_auth_dependencies.py, and the *_permissions.py
    files added in later tasks).
    """
    _app.dependency_overrides[get_current_user] = lambda: _DEFAULT_TEST_USER
    yield
    _app.dependency_overrides.pop(get_current_user, None)
