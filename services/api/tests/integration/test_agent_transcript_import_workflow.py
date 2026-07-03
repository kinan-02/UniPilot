"""Integration tests for agent transcript import workflow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures.completed_course_fixtures import KNOWN_COURSE_NUMBER, seed_production_course_fixture
from tests.integration.test_agent_conversation_routes import register_access_token

SAMPLE_PDF = b"%PDF-1.4\n00940345 Discrete Math 90 4.0\n"


@pytest.mark.asyncio
async def test_agent_transcript_import_requires_upload(auth_client):
    token = await register_access_token(auth_client, "agent-transcript-no-file@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "Import my transcript"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "upload" in body["text"].lower()


@pytest.mark.asyncio
async def test_agent_transcript_import_review_and_confirm(auth_client, mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    token = await register_access_token(auth_client, "agent-transcript@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    parse_result = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-2",
                "grade": 88,
                "creditsEarned": 4,
                "confidence": 0.95,
                "title": "Discrete Math",
                "warnings": [],
            }
        ],
        "warnings": [],
        "parseMetadata": {
            "pageCount": 1,
            "extractor": "test",
            "pipelineVersion": "test",
            "textCharCount": 42,
        },
    }

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={
            "content": "Import my transcript",
            "attachments": [
                {
                    "type": "transcript_pdf",
                    "filename": "transcript.pdf",
                    "parsePreview": parse_result,
                }
            ],
        },
        headers=headers,
    )

    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "confirm" in body["text"].lower()

    block_types = {
        event.get("block", {}).get("type")
        for event in body["events"]
        if event.get("type") == "structured_output"
    }
    assert "TranscriptReviewBlock" in block_types
    assert "ConfirmationBlock" in block_types

    action_events = [event for event in body["events"] if event.get("type") == "action.proposed"]
    assert action_events
    action_id = action_events[0]["action"]["id"]

    confirm_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/actions/{action_id}/confirm",
        headers=headers,
    )
    assert confirm_response.status_code == 200
    import_result = confirm_response.json()["data"]["importResult"]
    assert import_result["createdCount"] == 1
    assert import_result["created"][0]["courseNumber"] == KNOWN_COURSE_NUMBER
