"""Integration tests for the optional Phase 4 capability-diagnostics wiring.

Verifies the `AGENT_TASK_UNDERSTANDING_ENABLED` flag controls whether
`retrievalMetadata.capabilityDiagnostics` is attached, and — critically —
that toggling it never changes the SSE event sequence, message text, blocks,
warnings, or proposed actions a student actually sees, **as long as
`AGENT_TASK_UNDERSTANDING_DRY_RUN` stays at its default (`True`)** — under
the Layer 1 (request-understanding) redesign, routing follows Task
Understanding once `dry_run=False`; that behavior is covered separately in
`tests/agent/test_orchestrator_task_understanding_routing.py`.

`run_task_understanding` itself is mocked here rather than re-exercised — it
already has its own dedicated unit tests. This test suite is only about the
Phase 4 capability-diagnostics wiring in `orchestrator.py`.

Since `run_task_understanding` now always returns a real
`TaskUnderstandingOutput` (never `None`), `retrievalMetadata.taskUnderstanding`
is now always populated regardless of the flag — only
`capabilityDiagnostics` remains flag-gated.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user

_NO_LLM_OFF_SETTINGS = Settings(**{"OPENAI_API_KEY": None, "AGENT_TASK_UNDERSTANDING_ENABLED": False})
_NO_LLM_ON_SETTINGS = Settings(
    **{
        "OPENAI_API_KEY": None,
        "AGENT_TASK_UNDERSTANDING_ENABLED": True,
        "AGENT_TASK_UNDERSTANDING_DRY_RUN": True,
    }
)

_FAKE_TASK_UNDERSTANDING_SUMMARY = {
    "status": "completed",
    "primaryIntent": "course_question",
    "secondaryIntents": [],
    "taskCategory": "simple_question",
    "taskComplexity": "low",
    "recommendedAutonomyLevel": 2,
    "suggestedNextLayer": "deterministic_workflow",
    "requiresUserConfirmation": False,
    "writeRisk": "none",
    "missingContext": [],
    "intentConfidence": 0.9,
    "overallConfidence": 0.85,
    "decisionSummary": "test fixture summary",
    "warnings": [],
    "source": "llm_reasoning_block",
}

_FAKE_TASK_UNDERSTANDING_OUTPUT = TaskUnderstandingOutput(
    status="completed",
    user_goal="test fixture goal",
    normalized_request="test fixture goal",
    primary_intent="course_question",
    secondary_intents=[],
    task_category="simple_question",
    task_complexity="low",
    recommended_autonomy_level=2,
    suggested_next_layer="deterministic_workflow",
    required_context=[],
    missing_context=[],
    extracted_entities={},
    assumptions=[],
    requires_user_confirmation=False,
    write_risk="none",
    clarifying_questions=[],
    intent_confidence=0.9,
    overall_confidence=0.85,
    decision_summary="test fixture summary",
    warnings=[],
    source="llm_reasoning_block",
)


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


@pytest.fixture(autouse=True)
def _mock_task_understanding(monkeypatch):
    """Stand in for the real Task Understanding call — always returns a valid
    result (matching its actual never-`None` contract) regardless of the
    flag; `orchestrator.py`'s own flag check independently gates
    `capabilityDiagnostics`.
    """
    from app.agent import orchestrator

    async def _fake_run_task_understanding(*, settings=None, **_kwargs):
        return _FAKE_TASK_UNDERSTANDING_OUTPUT

    monkeypatch.setattr(orchestrator, "run_task_understanding", _fake_run_task_understanding)


async def _seed_user_and_conversation(mongo_database) -> tuple[str, str]:
    email = f"capability-diag-{uuid.uuid4().hex[:10]}@example.com"
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
            user_message="asdfgh this is not a recognizable academic request qwerty",
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


async def test_flag_off_omits_capability_diagnostics_but_still_records_task_understanding(
    mongo_database,
):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_NO_LLM_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "capabilityDiagnostics" not in metadata
    # `run_task_understanding` never returns `None` (even flag-off, it falls
    # back internally) — so `taskUnderstanding` is always attached now,
    # unlike the old dry-run wrapper that short-circuited before ever
    # producing a summary.
    assert metadata.get("taskUnderstanding") == _FAKE_TASK_UNDERSTANDING_SUMMARY


async def test_flag_on_attaches_compact_capability_diagnostics(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_NO_LLM_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("taskUnderstanding") == _FAKE_TASK_UNDERSTANDING_SUMMARY

    diagnostics = metadata.get("capabilityDiagnostics")
    assert diagnostics is not None
    assert diagnostics["targetCapability"] == "planner_agent"
    assert "course_question_workflow" in diagnostics["matchedCapabilities"]
    assert isinstance(diagnostics["includedSections"], list)
    assert isinstance(diagnostics["omittedSections"], list)
    assert isinstance(diagnostics["warnings"], list)
    assert isinstance(diagnostics["estimatedItems"], int)

    # Compact: no raw compiled context payload, no huge nested academic data.
    assert "context" not in diagnostics
    assert len(diagnostics["omittedSections"]) <= 12
    assert len(diagnostics["warnings"]) <= 8


async def test_flag_does_not_change_user_visible_response_or_sse_sequence(mongo_database):
    """With `AGENT_TASK_UNDERSTANDING_DRY_RUN=True` (both settings above),
    routing still follows the legacy rules-first/LLM-fallback classifier —
    Task Understanding's (mocked) disagreement with it must not leak into
    the response, since it's diagnostic-only for this dry-run mode.
    """
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
