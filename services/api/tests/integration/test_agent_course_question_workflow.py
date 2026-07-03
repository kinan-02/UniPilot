"""Integration tests for agent course question workflow."""

from __future__ import annotations

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_graduation_progress_contract import _seed_profile
from tests.integration.test_agent_conversation_routes import register_access_token


@pytest.mark.asyncio
async def test_agent_course_contribution_question(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "agent-course@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _seed_profile(auth_client, token, fixtures["programId"])

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": f"Does course {fixtures['courseBNumber']} count toward my degree?"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert body["messageId"]
    assert fixtures["courseBNumber"] in body["text"]

    block_types = {
        event.get("block", {}).get("type")
        for event in body["events"]
        if event.get("type") == "structured_output"
    }
    assert "CourseRecommendationBlock" in block_types


@pytest.mark.asyncio
async def test_agent_course_question_requires_number(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "agent-course-nonum@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _seed_profile(auth_client, token, fixtures["programId"])

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "Can I take this course next semester?"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "course number" in body["text"].lower()
