from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.graph.client import GraphMailClient, html_to_text, summarize_message
from app.graph.errors import OutlookNotConnectedError, OutlookRateLimitError
from app.security.token_store import upsert_outlook_tokens


@pytest.mark.asyncio
@respx.mock
async def test_search_messages_builds_request_and_returns_summary(
    mongo_database,
    sample_user_id,
    monkeypatch,
):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    from app.config import get_settings
    from app.db.mongo import set_test_database

    get_settings.cache_clear()
    set_test_database(mongo_database)

    await upsert_outlook_tokens(
        mongo_database,
        user_id=sample_user_id,
        microsoft_user_id="ms-user",
        email="student@example.com",
        access_token="access-token",
        refresh_token="refresh-token",
        access_token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["Mail.Read"],
    )

    graph_route = respx.get("https://graph.microsoft.com/v1.0/me/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Hello",
                        "from": {"emailAddress": {"name": "Admin", "address": "admin@example.com"}},
                        "receivedDateTime": "2026-01-01T10:00:00Z",
                        "bodyPreview": "Preview text",
                        "hasAttachments": False,
                        "parentFolderId": "inbox",
                    }
                ]
            },
        )
    )

    client = GraphMailClient()
    messages = await client.search_messages(user_id=sample_user_id, query="hello", max_results=5)

    assert graph_route.called
    request = graph_route.calls[0].request
    assert request.headers["Authorization"] == "Bearer access-token"
    assert messages[0]["subject"] == "Hello"
    assert messages[0]["sender"]["email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_missing_tokens_raises_not_connected(mongo_database, sample_user_id, monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    from app.config import get_settings
    from app.db.mongo import set_test_database

    get_settings.cache_clear()
    set_test_database(mongo_database)

    client = GraphMailClient()
    with pytest.raises(OutlookNotConnectedError):
        await client.search_messages(user_id=sample_user_id, max_results=5)


@pytest.mark.asyncio
@respx.mock
async def test_graph_rate_limit_error(mongo_database, sample_user_id, monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    from app.config import get_settings
    from app.db.mongo import set_test_database

    get_settings.cache_clear()
    set_test_database(mongo_database)

    await upsert_outlook_tokens(
        mongo_database,
        user_id=sample_user_id,
        microsoft_user_id="ms-user",
        email="student@example.com",
        access_token="access-token",
        refresh_token="refresh-token",
        access_token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["Mail.Read"],
    )

    respx.get("https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages").mock(
        return_value=httpx.Response(429, json={"error": {"code": "TooManyRequests"}})
    )

    client = GraphMailClient()
    with pytest.raises(OutlookRateLimitError):
        await client.get_recent_messages(user_id=sample_user_id, max_results=3)


def test_html_to_text_strips_tags():
    assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_summarize_message_uses_preview():
    summary = summarize_message(
        {
            "id": "1",
            "subject": "Subject",
            "from": {"emailAddress": {"address": "a@b.com"}},
            "receivedDateTime": "2026-01-01T00:00:00Z",
            "bodyPreview": "Short preview",
            "hasAttachments": True,
        }
    )
    assert summary["snippet"] == "Short preview"
    assert summary["hasAttachments"] is True
