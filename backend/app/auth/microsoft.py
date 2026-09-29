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
