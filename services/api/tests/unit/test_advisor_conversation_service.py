"""Unit tests for advisor conversation persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.advisor_conversation_service import (
    _fallback_summary_update,
    persist_advisor_exchange,
)


def test_fallback_summary_update_merges_prior():
    payload = _fallback_summary_update(
        "Prior topic: syllabus.",
        "Can I take 00440148?",
        "You are eligible.",
    )
    assert "Prior topic" in payload["summary"]
    assert "00440148" in payload["summary"]


@pytest.mark.asyncio
async def test_persist_advisor_exchange_creates_conversation() -> None:
    database = AsyncMock()
    created_id = ObjectId()

    with (
        patch(
            "app.services.advisor_conversation_service.summarize_conversation",
            new=AsyncMock(
                return_value={"title": "Eligibility", "summary": "Discussed course fit."}
            ),
        ),
        patch(
            "app.services.advisor_conversation_service.create_advisor_conversation",
            new=AsyncMock(
                return_value={
                    "_id": created_id,
                    "title": "Eligibility",
                    "summary": "Discussed course fit.",
                    "exchangeCount": 1,
                    "lastConfidence": "high",
                    "createdAt": None,
                    "updatedAt": None,
                }
            ),
        ),
    ):
        result = await persist_advisor_exchange(
            database,
            str(ObjectId()),
            question="Am I eligible?",
            answer="Yes.",
            confidence="high",
        )

    assert result["status"] == "ok"
    assert result["conversation"]["id"] == str(created_id)


@pytest.mark.asyncio
async def test_persist_advisor_exchange_updates_existing() -> None:
    database = AsyncMock()
    conversation_id = str(ObjectId())

    with (
        patch(
            "app.services.advisor_conversation_service.find_advisor_conversation_for_user",
            new=AsyncMock(return_value={"summary": "Earlier summary."}),
        ),
        patch(
            "app.services.advisor_conversation_service.summarize_conversation",
            new=AsyncMock(
                return_value={"title": "Updated", "summary": "Merged summary."}
            ),
        ),
        patch(
            "app.services.advisor_conversation_service.update_advisor_conversation_summary",
            new=AsyncMock(
                return_value={
                    "_id": ObjectId(conversation_id),
                    "title": "Updated",
                    "summary": "Merged summary.",
                    "exchangeCount": 2,
                    "lastConfidence": "medium",
                    "createdAt": None,
                    "updatedAt": None,
                }
            ),
        ),
    ):
        result = await persist_advisor_exchange(
            database,
            str(ObjectId()),
            question="Follow-up?",
            answer="More info.",
            confidence="medium",
            conversation_id=conversation_id,
        )

    assert result["status"] == "ok"
    assert result["conversation"]["exchangeCount"] == 2
