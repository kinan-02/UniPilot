"""Integration tests for Phase 10 specialist-agent wrappers wired into the
Supervisor Orchestrator Runtime.

`OPENAI_API_KEY=None` throughout — `ChatLLMAdapter.complete_json` raises
`LLMAdapterError("llm_unavailable")` *before* any network call whenever no
key is configured (see `app/agent/reasoning/llm_adapter.py`), so every test
here exercises the full `SpecialistAgentHandler` -> `ReasoningBlock` ->
`ChatLLMAdapter` path with zero real LLM calls, degrading safely to the
Phase 10 fallback output.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import SupervisorRunInput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user

_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_BASE_KWARGS = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True, "AGENT_SUPERVISOR_ENABLED": True}

_SPECIALISTS_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_AGENTS_ENABLED": False})
_SPECIALISTS_ON_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_AGENTS_ENABLED": True})


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


async def _seed_user_and_conversation(mongo_database) -> tuple[str, str]:
    email = f"specialist-diag-{uuid.uuid4().hex[:10]}@example.com"
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


def _specialist_plan(capability_name: str = "graduation_progress_agent") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-specialist-1",
        "user_goal": "What am I missing to graduate?",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": "ask_specialist",
                "title": "Ask the graduation progress specialist",
                "kind": "analyze",
                "capability_name": capability_name,
                "objective": "Determine remaining requirements toward graduation.",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


# ---------------------------------------------------------------------------
# 1. Specialist capabilities can appear in a supervisor plan.
# ---------------------------------------------------------------------------


async def test_specialist_capability_can_appear_in_a_supervisor_plan():
    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_specialist_plan()
    )

    output = await run_supervisor_shadow(input=run_input, settings=_SPECIALISTS_ON_SETTINGS)

    assert output.status in ("completed", "completed_with_warnings")
    record = output.subtask_records[0]
    assert record.capability_name == "graduation_progress_agent"


@pytest.mark.parametrize(
    "capability_name", ["graduation_progress_agent", "course_catalog_agent", "requirement_explanation_agent"]
)
async def test_each_specialist_capability_can_appear_in_a_plan(capability_name):
    run_input = SupervisorRunInput(user_message="test", planner_output=_specialist_plan(capability_name))

    output = await run_supervisor_shadow(input=run_input, settings=_SPECIALISTS_ON_SETTINGS)

    assert output.subtask_records[0].capability_name == capability_name


# ---------------------------------------------------------------------------
# 2. Supervisor uses SpecialistAgentHandler when enabled.
# ---------------------------------------------------------------------------


async def test_supervisor_uses_specialist_agent_handler_when_enabled():
    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_specialist_plan()
    )

    output = await run_supervisor_shadow(input=run_input, settings=_SPECIALISTS_ON_SETTINGS)

    record = output.subtask_records[0]
    # `SpecialistAgentHandler`'s compact summary shape is distinct from the
    # generic `DryRunCapabilityHandler`'s `{"dryRun": True, ...}` shape.
    assert record.result_summary is not None
    assert record.result_summary.get("agentName") == "graduation_progress_agent"
    assert "dryRun" not in record.result_summary


async def test_specialist_handler_falls_back_safely_without_real_llm():
    """No OPENAI_API_KEY -> ChatLLMAdapter raises before any network call ->
    the specialist gracefully returns its Phase 10 fallback output."""
    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_specialist_plan()
    )

    output = await run_supervisor_shadow(input=run_input, settings=_SPECIALISTS_ON_SETTINGS)

    record = output.subtask_records[0]
    assert record.result_summary["status"] == "skipped"
    assert record.result_summary["confidence"] == 0.0
    assert "specialist_reasoning_unavailable_or_failed" in record.warnings


# ---------------------------------------------------------------------------
# 3. Supervisor stores compact specialist diagnostics only.
# ---------------------------------------------------------------------------


async def test_supervisor_stores_compact_specialist_diagnostics_only():
    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_specialist_plan()
    )

    output = await run_supervisor_shadow(input=run_input, settings=_SPECIALISTS_ON_SETTINGS)

    record = output.subtask_records[0]
    summary_text = str(record.result_summary)
    for forbidden in (
        "raw_context",
        "compiled_context",
        "chain_of_thought",
        "hidden_reasoning",
        "scratchpad",
        "thoughts",
        "raw_prompt",
    ):
        assert forbidden not in summary_text


# ---------------------------------------------------------------------------
# 4. Specialist failure does not break the live turn.
# ---------------------------------------------------------------------------


async def test_specialist_failure_does_not_break_live_turn(mongo_database, monkeypatch):
    from app.agent.specialists import supervisor_handler as supervisor_handler_module

    class _BoomRegistry:
        def get(self, _name):
            def _boom(*_args, **_kwargs):
                raise RuntimeError("boom")

            return _boom

    monkeypatch.setattr(
        supervisor_handler_module,
        "build_default_specialist_agent_registry",
        lambda: _BoomRegistry(),
    )

    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SPECIALISTS_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


# ---------------------------------------------------------------------------
# 5. Specialists disabled keeps previous behavior.
# ---------------------------------------------------------------------------


async def test_specialists_disabled_returns_skipped_without_calling_reasoning_block(monkeypatch):
    from app.agent.specialists import base as specialists_base_module

    called = False

    async def _boom(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("ReasoningBlock.run must not be called when specialists are disabled")

    class _FakeBlock:
        run = staticmethod(_boom)

    monkeypatch.setattr(specialists_base_module, "ReasoningBlock", lambda **_kwargs: _FakeBlock())

    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_specialist_plan()
    )

    settings_off = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_AGENTS_ENABLED": False})
    output = await run_supervisor_shadow(input=run_input, settings=settings_off)

    assert called is False
    record = output.subtask_records[0]
    assert record.result_summary["status"] == "skipped"


async def test_specialists_disabled_preserves_phase6_diagnostics_behavior(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_SPECIALISTS_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("supervisorDiagnostics")
    assert diagnostics is not None
    assert diagnostics["completedSubtasks"] == ["run_legacy_workflow"]


# ---------------------------------------------------------------------------
# 6. Enabling specialists does not change user-facing text/blocks/actions/SSE
# sequence (the deterministic fallback plan never references a specialist
# capability, so the flag alone can never change a live turn).
# ---------------------------------------------------------------------------


async def test_enabling_specialists_does_not_change_user_visible_response_or_sse_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_SPECIALISTS_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_SPECIALISTS_ON_SETTINGS
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


# ---------------------------------------------------------------------------
# 7. Specialist output is not promotable in Phase 10.
# ---------------------------------------------------------------------------


async def test_specialist_output_is_never_promotable(mongo_database):
    """Phase 9 promotion is restricted to `graduation_progress_workflow` (the
    workflow), never `graduation_progress_agent` (the specialist) -- confirm
    `eligible_promotion_workflows` never includes any specialist agent name."""
    from app.agent.supervisor.promotion import eligible_promotion_workflows

    settings = Settings(
        **{
            **_BASE_KWARGS,
            "AGENT_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_SUPERVISOR_PROMOTION_ENABLED": True,
            "AGENT_SUPERVISOR_PROMOTION_MODE": "promote_validated",
            "AGENT_SUPERVISOR_PROMOTION_WORKFLOWS": (
                "graduation_progress_workflow,graduation_progress_agent,course_catalog_agent"
            ),
        }
    )

    eligible = eligible_promotion_workflows(settings)

    assert eligible == {"graduation_progress_workflow"}
    assert "graduation_progress_agent" not in eligible
    assert "course_catalog_agent" not in eligible
    assert "requirement_explanation_agent" not in eligible
