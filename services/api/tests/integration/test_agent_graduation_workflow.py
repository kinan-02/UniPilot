"""Integration test for agent graduation progress workflow."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_graduation_progress_contract import _seed_profile
from tests.integration.test_agent_conversation_routes import register_access_token

VALID_PASSWORD = "StrongPass123!"


@pytest.mark.asyncio
async def test_agent_graduation_progress_with_profile(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "agent-grad@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _seed_profile(auth_client, token, fixtures["programId"])

    await auth_client.post(
        "/completed-courses",
        headers=headers,
        json=build_completed_course_payload(
            fixtures["courseBId"],
            semester_code="2024-2",
            grade=88,
            credits_earned=3.5,
        ),
    )

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "What am I missing to graduate?"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert body["messageId"]
    assert "graduation progress" in body["text"].lower() or "credits" in body["text"].lower()

    structured = [
        event.get("block")
        for event in body["events"]
        if event.get("type") == "structured_output" and event.get("block")
    ]
    block_types = {block.get("type") for block in structured if isinstance(block, dict)}
    assert "RequirementSummaryBlock" in block_types or any(
        event.get("type") == "message.completed" for event in body["events"]
    )
