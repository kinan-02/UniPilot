"""Integration tests for UniPilot Agent conversation routes.

`orchestrator.run_agent_turn` now lives in the standalone `agent` service
(see `services/agent/`). These tests exercise everything `api` still owns
(conversation CRUD, auth, rate limiting, action confirm/reject) and mock
`app.services.agent_conversation_service.stream_agent_turn` — the one call
that crosses the service boundary — with a canned SSE stream shaped exactly
like a real `agent` service response, so the proxy/persistence logic in
`api` is verified without needing the real service running.
"""

from __future__ import annotations

import json

import pytest

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


def _sse_event(event_type: str, **fields) -> str:
    payload = {"type": event_type, **fields}
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _fake_agent_turn_stream(*, text: str):
    async def _stream(**_kwargs):
        yield _sse_event("agent.step.started", label="Understanding your request")
        yield _sse_event("agent.step.completed", label="Understanding your request")
        yield _sse_event("message.completed", text=text, messageId="fake-message-id", runId="fake-run-id")
        yield _sse_event("run.completed", runId="fake-run-id")

    return _stream


@pytest.mark.asyncio
async def test_agent_conversations_require_auth(auth_client):
    response = await auth_client.post("/agent/conversations", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_conversations(auth_client):
    token = await register_access_token(auth_client, "agent-conv@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post(
        "/agent/conversations",
        json={"title": "Graduation check"},
        headers=headers,
    )
    assert create_response.status_code == 200
    conversation = create_response.json()["data"]["conversation"]
    assert conversation["title"] == "Graduation check"
    assert conversation["status"] == "active"

    list_response = await auth_client.get("/agent/conversations", headers=headers)
    assert list_response.status_code == 200
    conversations = list_response.json()["data"]["conversations"]
    assert any(item["id"] == conversation["id"] for item in conversations)


@pytest.mark.asyncio
async def test_send_message_json_mode_without_profile(auth_client, monkeypatch):
    from app.services import agent_conversation_service

    monkeypatch.setattr(
        agent_conversation_service,
        "stream_agent_turn",
        _fake_agent_turn_stream(text="Please complete your student profile before I can continue."),
    )

    token = await register_access_token(auth_client, "agent-msg@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "What am I missing to graduate?"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "student profile" in body["text"].lower()
    assert body["messageId"]
    assert any(event.get("type") == "agent.step.started" for event in body["events"])


@pytest.mark.asyncio
async def test_send_message_forwards_to_agent_service_with_correct_params(auth_client, monkeypatch):
    """Confirms `api` actually calls `stream_agent_turn` (the service boundary) with
    the right conversation/user/message identifiers, and relays its text back.

    Note: the assistant message itself is persisted by the real `agent`
    service via its own direct Mongo connection during `run_agent_turn` (see
    `services/agent/tests/agent/test_orchestrator_workflows.py`) — not by
    `api` — so that persistence isn't re-verified through this mock.
    """
    from app.services import agent_conversation_service

    calls: list[dict] = []

    def _tracking_stream(**kwargs):
        calls.append(kwargs)
        return _fake_agent_turn_stream(text="You have 90 of 120 credits completed.")(**kwargs)

    monkeypatch.setattr(agent_conversation_service, "stream_agent_turn", _tracking_stream)

    token = await register_access_token(auth_client, "agent-forward@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "What am I missing to graduate?"},
        headers=headers,
    )

    assert message_response.status_code == 200
    assert message_response.json()["data"]["text"] == "You have 90 of 120 credits completed."
    assert len(calls) == 1
    assert calls[0]["user_message"] == "What am I missing to graduate?"
    assert calls[0]["conversation_id"] == conversation_id
    assert calls[0]["trigger_message_id"]
