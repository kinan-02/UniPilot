import pytest

from app.security.microsoft_oauth import (
    MicrosoftOAuthError,
    build_microsoft_authorization_url,
    fetch_microsoft_user_profile,
)


def test_build_authorization_url_requires_client_id(monkeypatch):
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(MicrosoftOAuthError):
        build_microsoft_authorization_url(state="s", code_challenge="c")


@pytest.mark.asyncio
async def test_fetch_profile_missing_fields(monkeypatch):
    import httpx
    import respx

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    from app.config import get_settings

    get_settings.cache_clear()

    with respx.mock:
        respx.get("https://graph.microsoft.com/v1.0/me").mock(
            return_value=httpx.Response(200, json={"id": "", "mail": ""})
        )
        with pytest.raises(MicrosoftOAuthError):
            await fetch_microsoft_user_profile("token")


@pytest.mark.asyncio
async def test_fetch_profile_graph_error(monkeypatch):
    import httpx
    import respx

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    from app.config import get_settings

    get_settings.cache_clear()

    with respx.mock:
        respx.get("https://graph.microsoft.com/v1.0/me").mock(
            return_value=httpx.Response(500, json={"error": "server"})
        )
        with pytest.raises(MicrosoftOAuthError):
            await fetch_microsoft_user_profile("token")
