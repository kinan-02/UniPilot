"""Integration tests for Phase 13's Bounded Specialist Tool-Request Loop,
wired into the Supervisor Orchestrator Runtime + live-turn diagnostics.

Mirrors `test_specialist_observations_supervisor_diagnostics.py` (Phase 12):
strong, behavior-specific assertions (the tool loop actually engaging,
approving/rejecting observations, diagnostics counts) run at the
`run_supervisor_shadow` level with an injected specialist plan and a
monkeypatched, queue-based fake `ReasoningBlock` (no real LLM call, no
`OPENAI_API_KEY`); weak, regression-only assertions (SSE/text/blocks/actions
parity, no raw content leaking into `agent_runs.retrievalMetadata`, no
writes/action proposals) run through a real `run_agent_turn` with an
unrecognized message, exactly like Phase 10/12's own full-turn tests --
`OPENAI_API_KEY=None` there means the live path's own planner/specialist
reasoning safely falls back before any network call, same as before Phase 13
existed.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput, ReasoningToolRequest
from app.agent.schemas import AgentContextPack
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import SupervisorRunInput, SupervisorRuntimeContext
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user

_GRADUATION_MESSAGE = "What am I missing to graduate?"
_UNRECOGNIZED_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SPECIALIST_AGENTS_ENABLED": True,
}

_TOOL_LOOP_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_TOOL_LOOP_ENABLED": False})
_TOOL_LOOP_ON_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_TOOL_LOOP_ENABLED": True})


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


def _specialist_plan(capability_name: str = "graduation_progress_agent") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-tool-loop-1",
        "user_goal": _GRADUATION_MESSAGE,
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


def _real_pack(**overrides: Any) -> AgentContextPack:
    defaults = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        user_context={
            "profile": {"degreeProgram": "BSc CS", "track": "cs", "catalogYear": 2024},
            "completedCourses": ["234123", "104031"],
            "completedCourseIds": ["a1", "a2"],
            "dataQuality": {"ok": True},
        },
        academic_context={
            "degreeRequirements": [{"id": "r1", "name": "Intro CS", "minCredits": 5.0}],
            "degreeProgram": {"programCode": "P1", "name": "CS", "catalogYear": 2024},
        },
        assumptions=["Using latest completed-course data on file."],
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


class _QueuedFakeBlock:
    def __init__(self, outputs: list[ReasoningBlockOutput]) -> None:
        self._outputs = list(outputs)

    async def run(self, reasoning_input: ReasoningBlockInput) -> ReasoningBlockOutput:
        assert self._outputs, "QueuedFakeBlock called more times than outputs were queued"
        return self._outputs.pop(0)


def _needs_tool(tool_name: str) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="needs_tool",
        result=None,
        tool_requests=[ReasoningToolRequest(tool_name=tool_name, purpose="need more data")],
        decision_summary="Need more data.",
        confidence=0.3,
        schema_valid=False,
        iterations_used=1,
        repair_attempts_used=0,
    )


def _completed(result: dict[str, Any]) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary=result.get("decision_summary", "done"),
        confidence=0.9,
        schema_valid=True,
        iterations_used=3,
        repair_attempts_used=0,
    )


def _patch_reasoning_block(monkeypatch, outputs: list[ReasoningBlockOutput]) -> None:
    """Monkeypatches the `ReasoningBlock` name inside `specialists.base` only
    -- every other `ReasoningBlock` consumer (intent classification, task
    understanding, etc.) is unaffected, exactly like the existing Phase 10
    `test_specialists_disabled_returns_skipped_without_calling_reasoning_block` pattern."""
    from app.agent.specialists import base as specialists_base_module

    monkeypatch.setattr(specialists_base_module, "ReasoningBlock", lambda **_kwargs: _QueuedFakeBlock(outputs))


async def _seed_user_and_conversation(mongo_database) -> tuple[str, str]:
    email = f"specialist-tool-loop-{uuid.uuid4().hex[:10]}@example.com"
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
            user_message=_UNRECOGNIZED_MESSAGE,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


# ---------------------------------------------------------------------------
# 1. Tool loop flag off keeps response unchanged (no ReasoningBlock patch --
# the real adapter fails immediately with no OPENAI_API_KEY, so both flags
# degrade to the same Phase 10 fallback either way).
# ---------------------------------------------------------------------------


async def test_flag_off_keeps_behavior_unchanged() -> None:
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_TOOL_LOOP_OFF_SETTINGS
    )

    record = output.subtask_records[0]
    assert "toolLoopStatus" not in record.result_summary
    assert record.result_summary["status"] == "skipped"


# ---------------------------------------------------------------------------
# 2. Tool loop flag on keeps final text/blocks/actions/SSE sequence unchanged
# (still shadow-only -- the live turn never reaches the specialist plan).
# ---------------------------------------------------------------------------


async def test_flag_on_does_not_change_user_visible_response_or_sse_sequence(mongo_database) -> None:
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_TOOL_LOOP_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_TOOL_LOOP_ON_SETTINGS
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
# 3. Tool loop diagnostics are compact (real engagement via a monkeypatched
# fake ReasoningBlock -- no real LLM call).
# ---------------------------------------------------------------------------


async def test_tool_loop_diagnostics_are_compact_when_engaged(monkeypatch) -> None:
    _patch_reasoning_block(
        monkeypatch,
        [_needs_tool("profile_summary"), _completed({"decision_summary": "You still need 40 credits."})],
    )
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_TOOL_LOOP_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert record.result_summary["status"] == "completed"
    assert record.result_summary["toolLoopStatus"] == "completed_with_tools"
    assert record.result_summary["toolLoopRoundsUsed"] == 1
    assert record.result_summary["approvedObservationCount"] == 1
    assert record.result_summary["requestedObservationNames"] == ["profile_summary"]
    for key in (
        "toolLoopStatus",
        "toolLoopRoundsUsed",
        "requestedObservationCount",
        "approvedObservationCount",
        "rejectedObservationCount",
        "requestedObservationNames",
        "rejectedObservationNames",
    ):
        assert key in record.result_summary


# ---------------------------------------------------------------------------
# 4. Rejected observation request is surfaced in diagnostics.
# ---------------------------------------------------------------------------


async def test_rejected_observation_request_is_surfaced_in_diagnostics(monkeypatch) -> None:
    _patch_reasoning_block(
        monkeypatch,
        [_needs_tool("full_catalog"), _completed({"decision_summary": "done anyway"})],
    )
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_TOOL_LOOP_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert record.result_summary["approvedObservationCount"] == 0
    assert "full_catalog" in record.result_summary["rejectedObservationNames"]


# ---------------------------------------------------------------------------
# 5. Missing observation does not fail the live turn.
# ---------------------------------------------------------------------------


async def test_missing_observation_does_not_fail_the_turn(monkeypatch) -> None:
    _patch_reasoning_block(
        monkeypatch,
        [_needs_tool("graduation_audit_summary"), _completed({"decision_summary": "done anyway"})],
    )
    # No `graduationAudit` on this pack -> the approved observation comes
    # back "missing", never a crash.
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_TOOL_LOOP_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert record.status != "failed"
    assert record.result_summary["status"] == "completed"
    assert record.result_summary["approvedObservationCount"] == 1


# ---------------------------------------------------------------------------
# 6. No raw observations/tool-request content stored in retrievalMetadata.
# ---------------------------------------------------------------------------


async def test_no_raw_tool_loop_content_stored_in_retrieval_metadata(mongo_database) -> None:
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    _events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TOOL_LOOP_ON_SETTINGS
    )

    metadata_text = str(run_doc.get("retrievalMetadata") or {})
    for forbidden in (
        "toolLoopStatus",
        "requestedObservationNames",
        "raw_context",
        "chain_of_thought",
        "TOP_SECRET",
    ):
        assert forbidden not in metadata_text


# ---------------------------------------------------------------------------
# 7. No writes/action proposals created.
# ---------------------------------------------------------------------------


async def test_no_writes_or_action_proposals_created(mongo_database) -> None:
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, _ = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TOOL_LOOP_ON_SETTINGS
    )

    assert not any(e.type == "action.proposed" for e in events)
    proposals = await mongo_database["agent_action_proposals"].count_documents({"userId": ObjectId(user_id)})
    assert proposals == 0


# ---------------------------------------------------------------------------
# 8. Direct LLM guard: the tool loop never calls an LLM directly, even when
# it actually engages (monkeypatched fake ReasoningBlock proves the loop
# only ever re-invokes the same block object, never a new LLM call site).
# ---------------------------------------------------------------------------


async def test_tool_loop_engaging_introduces_no_direct_llm_call(monkeypatch) -> None:
    _patch_reasoning_block(
        monkeypatch,
        [_needs_tool("profile_summary"), _completed({"decision_summary": "done"})],
    )
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_TOOL_LOOP_ON_SETTINGS
    )

    # Reaching a real result via the fake block (never the real ChatLLMAdapter)
    # confirms no direct network/LLM call happened anywhere in the loop.
    assert output.subtask_records[0].result_summary["status"] == "completed"
