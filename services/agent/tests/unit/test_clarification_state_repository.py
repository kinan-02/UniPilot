"""Unit tests for clarification state repository (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.config import Settings
from app.repositories.clarification_state_repository import (
    ClarificationStateRepository,
    reset_clarification_state_indexes_state,
)


@pytest.fixture(autouse=True)
def _reset_indexes() -> None:
    reset_clarification_state_indexes_state()
    yield
    reset_clarification_state_indexes_state()


@pytest.fixture
def repo(mongo_database) -> ClarificationStateRepository:
    return ClarificationStateRepository(
        mongo_database,
        settings=Settings(agent_clarification_states_collection="agent_clarification_states"),
    )


async def _ids(mongo_database) -> tuple[str, str]:
    user_id = str(ObjectId())
    conversation_id = str(ObjectId())
    await mongo_database["agent_conversations"].insert_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id), "assumptions": []}
    )
    return user_id, conversation_id


async def test_create_pending_state(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Which preference?", "options": ["a", "b"]}],
        needs=[{"id": "need-1", "question_topic": "workload", "default_assumption": "lighter workload"}],
    )
    assert pending is not None
    assert pending.status == "pending"


async def test_get_active_state_by_conversation(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Which preference?", "options": ["a", "b"]}],
        needs=[{"id": "need-1"}],
    )
    active = await repo.get_active_for_conversation(conversation_id)
    assert active is not None
    assert active.conversation_id == conversation_id


async def test_only_one_active_pending_state_per_conversation(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    first = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="first",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
    )
    second = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="second",
        questions=[{"need_id": "need-2", "prompt": "Q2?", "options": ["b"]}],
        needs=[{"id": "need-2"}],
    )
    assert first is not None
    assert second is None


async def test_mark_answered(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
    )
    assert pending is not None
    updated = await repo.mark_answered(
        pending.clarification_id,
        answers=[{"need_id": "need-1", "value": "a", "provenance": "confirmed"}],
    )
    assert updated is not None
    assert updated.status == "answered"
    assert await repo.get_active_for_conversation(conversation_id) is None


async def test_mark_assumed(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1", "default_assumption": "a"}],
    )
    assert pending is not None
    updated = await repo.mark_assumed(
        pending.clarification_id,
        answers=[{"need_id": "need-1", "value": "a", "provenance": "assumed"}],
    )
    assert updated is not None
    assert updated.status == "assumed"


async def test_mark_expired(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
    )
    assert pending is not None
    updated = await repo.mark_expired(pending.clarification_id)
    assert updated is not None
    assert updated.status == "expired"


async def test_cancel_active(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
    )
    assert pending is not None
    cancelled = await repo.cancel_active(conversation_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"


async def test_no_student_academic_collections_touched(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
    )
    assert await mongo_database["completed_courses"].count_documents({}) == 0
    assert await mongo_database["semester_plans"].count_documents({}) == 0


async def test_stored_document_contains_no_raw_context(repo, mongo_database) -> None:
    user_id, conversation_id = await _ids(mongo_database)
    await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message="Plan my semester",
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a"]}],
        needs=[{"id": "need-1"}],
        compact_context={"questionCount": 1, "compiled_context": {"secret": True}},
    )
    doc = await mongo_database["agent_clarification_states"].find_one({"conversationId": ObjectId(conversation_id)})
    assert doc is not None
    stored = str(doc)
    assert "compiled_context" not in stored
    assert "proposed_actions" not in stored
