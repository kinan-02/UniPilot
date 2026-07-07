"""Integration tests for the optional Phase 6 supervisor-diagnostics wiring.

Verifies the `AGENT_SUPERVISOR_ENABLED` flag controls whether
`retrievalMetadata.supervisorDiagnostics` is attached, and — critically —
that toggling it never changes the SSE event sequence, message text,
blocks, warnings, or proposed actions a student actually sees.

`AGENT_PLANNER_ENABLED` stays `True` in every test here (both flag-off and
flag-on) so the only variable under test is the supervisor flag itself —
per the spec, the supervisor only ever runs once planner diagnostics
already produced a plan. Runs the real (not mocked) deterministic-fallback
planner + supervisor paths with `OPENAI_API_KEY=None` — no real LLM call.
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

_BASE_SETTINGS_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    # Explicit, not relied-on-default: this file tests the Phase 6
    # pre-context dry-run diagnostic in isolation. An operator's real
    # `.env` may enable real handlers ambiently for the unrelated Phase 9
    # promotion rollout (exactly as this repo's own root `.env` now does) --
    # since this call site never supplies a `runtime_context`, enabling real
    # handlers wouldn't change *execution* here, but it does attach an extra
    # "missing runtime context" warning that would otherwise flip
    # `status` from "completed" to "completed_with_warnings".
    "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": False,
}

_SUPERVISOR_OFF_SETTINGS = Settings(**{**_BASE_SETTINGS_KWARGS, "AGENT_SUPERVISOR_ENABLED": False})
_SUPERVISOR_ON_SETTINGS = Settings(
    **{**_BASE_SETTINGS_KWARGS, "AGENT_SUPERVISOR_ENABLED": True, "AGENT_SUPERVISOR_DRY_RUN": True}
)
_SUPERVISOR_ON_DRY_RUN_FALSE_SETTINGS = Settings(
    **{**_BASE_SETTINGS_KWARGS, "AGENT_SUPERVISOR_ENABLED": True, "AGENT_SUPERVISOR_DRY_RUN": False}
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
    email = f"supervisor-diag-{uuid.uuid4().hex[:10]}@example.com"
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


async def test_flag_off_keeps_behavior_unchanged_and_omits_supervisor_diagnostics(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SUPERVISOR_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorDiagnostics" not in metadata
    # Planner still ran (its own independent flag stayed on) -- confirms
    # we isolated exactly the supervisor flag's effect.
    assert "plannerDiagnostics" in metadata


async def test_flag_on_attaches_compact_supervisor_diagnostics(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SUPERVISOR_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("supervisorDiagnostics")
    assert diagnostics is not None
    assert diagnostics["status"] == "completed"
    assert diagnostics["planId"] == "legacy_workflow_plan"
    assert diagnostics["executionMode"] == "deterministic_workflow"
    assert diagnostics["capabilities"] == ["general_academic_workflow"]
    assert diagnostics["completedSubtasks"] == ["run_legacy_workflow"]
    assert diagnostics["failedSubtasks"] == []
    assert diagnostics["skippedSubtasks"] == []
    assert diagnostics["contextPreviewCount"] >= 1
    assert set(diagnostics["budget"]) == {"maxSubtasks", "maxRetriesPerSubtask"}

    # Compact: no raw compiled context payload / chain-of-thought anywhere.
    assert "context" not in diagnostics
    assert "chain_of_thought" not in str(diagnostics)
    assert "scratchpad" not in str(diagnostics)


async def test_flag_does_not_change_user_visible_response_or_sse_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_SUPERVISOR_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_SUPERVISOR_ON_SETTINGS
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


async def test_supervisor_diagnostic_failure_does_not_fail_the_turn(mongo_database, monkeypatch):
    """A bug inside `run_supervisor_shadow` must never break a live turn."""
    from app.agent.supervisor import diagnostics as supervisor_diagnostics

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(supervisor_diagnostics, "run_supervisor_shadow", _boom)

    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SUPERVISOR_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorDiagnostics" not in metadata


async def test_supervisor_diagnostics_has_no_raw_context_or_chain_of_thought(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    _events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SUPERVISOR_ON_SETTINGS
    )

    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics_text = str(metadata.get("supervisorDiagnostics"))
    for forbidden in (
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "raw_mongo_document",
        "attachment_contents",
    ):
        assert forbidden not in diagnostics_text


async def test_supervisor_dry_run_false_still_remains_shadow_only_and_warns(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_SUPERVISOR_ON_DRY_RUN_FALSE_SETTINGS,
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("supervisorDiagnostics")
    assert diagnostics is not None
    # Still shadow-only: the same safe dry-run handler ran, nothing executed for real.
    assert diagnostics["completedSubtasks"] == ["run_legacy_workflow"]
    assert any("supervisor_dry_run_flag_has_no_effect_on_shadow_execution" in w for w in diagnostics["warnings"])

    # And, critically, the response itself is still completely unaffected.
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
