import pytest

import app.api.reviews as reviews_module


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
