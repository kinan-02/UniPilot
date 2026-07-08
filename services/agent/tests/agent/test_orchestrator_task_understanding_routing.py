"""Proves the Layer 1 (request-understanding) redesign's core new behavior:
with `AGENT_TASK_UNDERSTANDING_DRY_RUN=False`, Task Understanding's
`primary_intent` — not the legacy rules-first/LLM-fallback classifier —
drives workflow dispatch.

Companion to `tests/integration/test_capability_diagnostics.py` (which
covers the `dry_run=True`/default "no behavior change" case) and
`tests/unit/test_task_understanding_integration.py` (the bridge's own unit
coverage).
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.user_repository import create_user

_LIVE_SETTINGS = Settings(
    **{
        "OPENAI_API_KEY": None,
        "AGENT_TASK_UNDERSTANDING_ENABLED": True,
        "AGENT_TASK_UNDERSTANDING_DRY_RUN": False,
    }
)

# Same as above, but with graph retrieval off — for tests that only care
# about entity-merge/persistence behavior and use made-up course numbers
# that don't exist in the real wiki/graph corpus.
_LIVE_SETTINGS_NO_GRAPH = Settings(
    **{
        "OPENAI_API_KEY": None,
        "AGENT_TASK_UNDERSTANDING_ENABLED": True,
        "AGENT_TASK_UNDERSTANDING_DRY_RUN": False,
        "AGENT_GRAPH_RETRIEVAL_ENABLED": False,
    }
)

# Deliberately meaningless: the deterministic rules classifier resolves this
# to `unknown_or_unsupported` (-> `general_academic_workflow`) with low
# confidence — nothing here would ever plausibly imply transcript import.
_NONSENSE_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"


def _fake_transcript_import_understanding() -> TaskUnderstandingOutput:
    return TaskUnderstandingOutput(
        status="completed",
        user_goal="Import a transcript.",
        normalized_request="Import a transcript.",
        primary_intent="transcript_import",
        secondary_intents=[],
        task_category="transcript_processing",
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
        intent_confidence=0.95,
        overall_confidence=0.9,
        decision_summary="Fake understanding forcing transcript_import routing.",
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


async def test_dry_run_false_routes_by_task_understanding_intent_not_deterministic_intent(
    mongo_database, monkeypatch
):
    from app.agent import orchestrator

    async def _fake_run_task_understanding(*, settings=None, **_kwargs):
        return _fake_transcript_import_understanding()

    monkeypatch.setattr(orchestrator, "run_task_understanding", _fake_run_task_understanding)

    user = await create_user(mongo_database, email="agent-tu-routing@example.com", password_hash="hashed")
    user_id = str(user["_id"])
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=str(conversation["id"]),
            user_message=_NONSENSE_MESSAGE,
            trigger_message_id=str(ObjectId()),
            settings=_LIVE_SETTINGS,
        )
    ]

    assert not any(e.type == "run.failed" for e in events)
    completed = [e for e in events if e.type == "message.completed"]
    assert completed
    # `transcript_import_workflow`'s distinctive no-attachment guidance text
    # (see `test_transcript_import_workflow_requires_upload`) — only reachable
    # if task understanding's intent, not the deterministic guess, drove
    # `build_task_plan`.
    assert "upload" in completed[0].text.lower()

    run_doc = await mongo_database[_LIVE_SETTINGS.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    assert run_doc is not None
    assert run_doc["intent"] == "transcript_import"


async def test_dry_run_false_persists_entities_with_regex_precedence_over_task_understanding(
    mongo_database, monkeypatch
):
    """Regex-found core entities must never be silently overwritten by task
    understanding's own guess — this is the same non-overwrite guarantee
    `resolve_entities_with_llm_fallback` gave before this redesign.
    """
    from app.agent import orchestrator

    async def _fake_run_task_understanding(*, settings=None, **_kwargs):
        return TaskUnderstandingOutput(
            status="completed",
            user_goal="Course question.",
            normalized_request="Course question.",
            primary_intent="course_question",
            secondary_intents=[],
            task_category="simple_question",
            task_complexity="low",
            recommended_autonomy_level=2,
            suggested_next_layer="deterministic_workflow",
            required_context=[],
            missing_context=[],
            # Deliberately conflicting courseNumber (regex will find a
            # different one from the raw message) plus a key regex can't find.
            extracted_entities={"courseNumber": "999999", "trackSlug": "track-computer-science"},
            assumptions=[],
            requires_user_confirmation=False,
            write_risk="none",
            clarifying_questions=[],
            intent_confidence=0.9,
            overall_confidence=0.85,
            decision_summary="test",
            warnings=[],
            source="llm_reasoning_block",
        )

    monkeypatch.setattr(orchestrator, "run_task_understanding", _fake_run_task_understanding)

    user = await create_user(mongo_database, email="agent-tu-entities@example.com", password_hash="hashed")
    user_id = str(user["_id"])
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=str(conversation["id"]),
            user_message="Can I take course 234218 next semester?",
            trigger_message_id=str(ObjectId()),
            settings=_LIVE_SETTINGS_NO_GRAPH,
        )
    ]

    assert not any(e.type == "run.failed" for e in events)

    conversation_doc = await mongo_database[_LIVE_SETTINGS_NO_GRAPH.agent_conversations_collection].find_one(
        {"_id": ObjectId(str(conversation["id"]))}
    )
    assert conversation_doc is not None
    entities = conversation_doc.get("entities") or {}
    # Regex-found value wins over task understanding's conflicting guess.
    assert entities.get("courseNumber") == "234218"
    # Task understanding's contribution beyond what regex found is preserved.
    assert entities.get("trackSlug") == "track-computer-science"
