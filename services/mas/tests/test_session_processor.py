"""Unit tests for MAS session processor completion events."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.sessions.processor import process_session


@pytest.mark.asyncio
async def test_process_session_persists_completion_event_on_success() -> None:
    session_id = str(ObjectId())
    session_doc = {
        "_id": ObjectId(session_id),
        "userId": ObjectId(),
        "goal": "plan next semester",
        "status": "pending",
        "constraints": {},
    }
    negotiation_result = AsyncMock(
        status="completed",
        transcript=[{"agent_role": "arbiter"}],
        final_decision={"course_ids": ["00140008"]},
        utility_breakdown={"total": 0.8},
        rounds=2,
        error=None,
    )

    with (
        patch("app.sessions.processor.get_database", new=AsyncMock()) as db_factory,
        patch("app.sessions.processor.ensure_agent_session_indexes", new=AsyncMock()),
        patch("app.sessions.processor.find_session_by_id", new=AsyncMock(side_effect=[session_doc, session_doc])),
        patch("app.sessions.processor.mark_session_processing", new=AsyncMock()),
        patch("app.sessions.processor.load_enriched_user_context", new=AsyncMock(return_value={"user_id": "user-1"})),
        patch("app.sessions.processor.run_negotiation", new=AsyncMock(return_value=negotiation_result)),
        patch("app.sessions.processor.complete_session", new=AsyncMock()) as complete_session,
        patch("app.sessions.processor.persist_session_completion_event", new=AsyncMock()) as completion_event,
        patch("app.sessions.processor.build_session_lineage", return_value=None),
        patch("app.sessions.processor.merge_lineage_into_decision", side_effect=lambda decision, _lineage: decision),
    ):
        db_factory.return_value = AsyncMock()

        await process_session(session_id)

    complete_session.assert_awaited_once()
    completion_event.assert_awaited_once()
    assert completion_event.await_args.kwargs["status"] == "completed"
    assert completion_event.await_args.kwargs["rounds"] == 2


@pytest.mark.asyncio
async def test_process_session_returns_early_for_terminal_status() -> None:
    session_id = str(ObjectId())
    session_doc = {
        "_id": ObjectId(session_id),
        "userId": ObjectId(),
        "goal": "plan next semester",
        "status": "completed",
    }

    with (
        patch("app.sessions.processor.get_database", new=AsyncMock()),
        patch("app.sessions.processor.ensure_agent_session_indexes", new=AsyncMock()),
        patch("app.sessions.processor.find_session_by_id", new=AsyncMock(return_value=session_doc)),
        patch("app.sessions.processor.run_negotiation", new=AsyncMock()) as run_negotiation,
    ):
        result = await process_session(session_id)

    assert result == session_doc
    run_negotiation.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_session_raises_when_session_missing() -> None:
    with (
        patch("app.sessions.processor.get_database", new=AsyncMock()),
        patch("app.sessions.processor.ensure_agent_session_indexes", new=AsyncMock()),
        patch("app.sessions.processor.find_session_by_id", new=AsyncMock(return_value=None)),
    ):
        with pytest.raises(ValueError, match="Agent session not found"):
            await process_session(str(ObjectId()))


@pytest.mark.asyncio
async def test_process_session_persists_failure_completion_event() -> None:
    session_id = str(ObjectId())
    session_doc = {
        "_id": ObjectId(session_id),
        "userId": ObjectId(),
        "goal": "plan next semester",
        "status": "pending",
        "constraints": {},
    }

    with (
        patch("app.sessions.processor.get_database", new=AsyncMock()),
        patch("app.sessions.processor.ensure_agent_session_indexes", new=AsyncMock()),
        patch("app.sessions.processor.find_session_by_id", new=AsyncMock(return_value=session_doc)),
        patch("app.sessions.processor.mark_session_processing", new=AsyncMock()),
        patch("app.sessions.processor.load_enriched_user_context", new=AsyncMock(return_value={"user_id": "user-1"})),
        patch("app.sessions.processor.run_negotiation", new=AsyncMock(side_effect=RuntimeError("negotiation failed"))),
        patch("app.sessions.processor.complete_session", new=AsyncMock()) as complete_session,
        patch("app.sessions.processor.persist_session_completion_event", new=AsyncMock()) as completion_event,
        patch("app.sessions.processor.build_session_lineage", return_value=None),
    ):
        with pytest.raises(RuntimeError, match="negotiation failed"):
            await process_session(session_id)

    complete_session.assert_awaited_once()
    completion_event.assert_awaited_once()
    assert completion_event.await_args.kwargs["status"] == "failed"
    assert completion_event.await_args.kwargs["error"] == "negotiation failed"

