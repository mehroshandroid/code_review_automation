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
