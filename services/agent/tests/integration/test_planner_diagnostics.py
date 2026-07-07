"""Integration tests for the optional Phase 5 planner-diagnostics wiring.

Verifies the `AGENT_PLANNER_ENABLED` flag controls whether
`retrievalMetadata.plannerDiagnostics` is attached, and — critically — that
toggling it never changes the SSE event sequence, message text, blocks,
warnings, or proposed actions a student actually sees.

Runs `build_execution_plan` for real (not mocked) with `OPENAI_API_KEY=None`
— `ReasoningBlock`/`ChatLLMAdapter` fail fast without any network call, so
the planner falls back to its deterministic legacy plan, exercising the
real integration path end to end without a real LLM call.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user

_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_NO_LLM_OFF_SETTINGS = Settings(**{"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": False})
_NO_LLM_ON_SETTINGS = Settings(
    **{"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True, "AGENT_PLANNER_DRY_RUN": True}
)


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


async def _seed_user_and_conversation(mongo_database) -> tuple[str, str]:
    email = f"planner-diag-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": str(ObjectId()),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, user_id: str, conversation_id: str, settings: Settings):
    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=_MESSAGE,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


async def test_flag_off_keeps_behavior_unchanged_and_omits_planner_diagnostics(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_NO_LLM_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerDiagnostics" not in metadata


async def test_flag_on_stores_compact_planner_diagnostics(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_NO_LLM_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("plannerDiagnostics")
    assert diagnostics is not None
    assert diagnostics["status"] == "completed"
    assert diagnostics["planId"] == "legacy_workflow_plan"
    assert diagnostics["executionMode"] == "deterministic_workflow"
    assert diagnostics["capabilities"] == ["general_academic_workflow"]
    assert "planner_llm_unavailable_or_failed" in diagnostics["warnings"]
    assert isinstance(diagnostics["contextPreviews"], list)
    assert diagnostics["contextPreviews"]

    # Compact: no raw compiled context payload / chain-of-thought anywhere.
    assert "context" not in diagnostics
    for preview in diagnostics["contextPreviews"]:
        assert "context" not in preview
        assert set(preview) == {
            "subtaskId",
            "capabilityName",
            "includedSections",
            "omittedSections",
            "warnings",
            "estimatedItems",
        }


async def test_flag_does_not_change_user_visible_response_or_sse_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_NO_LLM_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_NO_LLM_ON_SETTINGS
    )

    assert [e.type for e in events_off] == [e.type for e in events_on]

    completed_off = next(e for e in events_off if e.type == "message.completed")
    completed_on = next(e for e in events_on if e.type == "message.completed")
    assert completed_off.text == completed_on.text

    blocks_off = [e.block for e in events_off if e.type == "structured_output"]
    blocks_on = [e.block for e in events_on if e.type == "structured_output"]
    assert [b.model_dump() for b in blocks_off] == [b.model_dump() for b in blocks_on]

    actions_off = [e.action for e in events_off if e.type == "action.proposed"]
    actions_on = [e.action for e in events_on if e.type == "action.proposed"]
    assert actions_off == actions_on


async def test_planner_diagnostic_failure_does_not_fail_the_turn(mongo_database, monkeypatch):
    """A bug inside `build_execution_plan` must never break a live turn.

    Exercises `planner.diagnostics.run_planner_dry_run`'s own internal
    try/except for real (rather than replacing that whole function), by
    breaking something it calls internally.
    """
    from app.agent.planner import diagnostics as planner_diagnostics

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(planner_diagnostics, "build_execution_plan", _boom)

    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_NO_LLM_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerDiagnostics" not in metadata
