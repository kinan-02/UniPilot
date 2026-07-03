import pytest

from app.security.microsoft_oauth import (
    MicrosoftOAuthError,
    build_microsoft_authorization_url,
    generate_pkce_pair,
)
from app.config import get_settings


def test_generate_pkce_pair_is_unique():
    verifier_a, challenge_a = generate_pkce_pair()
    verifier_b, challenge_b = generate_pkce_pair()
    assert verifier_a != verifier_b
    assert challenge_a != challenge_b


def test_build_authorization_url_contains_pkce_and_scopes(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
    monkeypatch.setenv("WEB_APP_URL", "http://localhost:3000")
    get_settings.cache_clear()

    url = build_microsoft_authorization_url(state="state123", code_challenge="challenge")
    assert "client-id" in url
    assert "code_challenge=challenge" in url
    assert "Mail.Read" in url
    assert "offline_access" in url


def test_build_authorization_url_requires_configuration(monkeypatch):
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    get_settings.cache_clear()
    with pytest.raises(MicrosoftOAuthError):
        build_microsoft_authorization_url(state="s", code_challenge="c")
