"""Integration tests for agent semester planning workflow."""

from __future__ import annotations

import pytest

from tests.fixtures.suggest_courses_fixtures import seed_suggest_courses_offerings
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import create_profile, register_access_token


@pytest.mark.asyncio
async def test_agent_semester_plan_requires_semester(auth_client):
    token = await register_access_token(auth_client, "agent-plan-no-sem@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "Build me a semester plan"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    lowered = body["text"].lower()
    assert "profile" in lowered or "semester" in lowered


@pytest.mark.asyncio
async def test_agent_semester_plan_options_and_save(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_suggest_courses_offerings(mongo_database)
    token = await register_access_token(auth_client, "agent-plan@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "Build me a plan for next semester with no more than 18 credits"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "option" in body["text"].lower()

    block_types = {
        event.get("block", {}).get("type")
        for event in body["events"]
        if event.get("type") == "structured_output"
    }
    assert "SemesterPlanOptionsBlock" in block_types
    assert "SchedulePreviewBlock" in block_types

    action_events = [event for event in body["events"] if event.get("type") == "action.proposed"]
    assert action_events
    action_id = action_events[0]["action"]["id"]

    confirm_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/actions/{action_id}/confirm",
        headers=headers,
    )
    assert confirm_response.status_code == 200
    plan = confirm_response.json()["data"]["planResult"]["plan"]
    assert plan["plannerType"] == "manual"
    assert plan["semesters"][0]["plannedCourses"]
