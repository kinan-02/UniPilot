"""Unit tests for the Phase 13 bounded specialist tool-request loop.

Covers both layers:
1. `app.agent.specialists.tools.tool_loop.run_specialist_tool_loop` -- the
   single-round validate+build executor (real registry, fake `AgentContextPack`,
   no `ReasoningBlock` involved at all).
2. `app.agent.specialists.base.run_specialist_reasoning`'s orchestration of
   that loop across rounds, using a fake, queue-based `ReasoningBlock` --
   never a real LLM call.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput, ReasoningToolRequest
from app.agent.reasoning.task_schemas import SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA
from app.agent.schemas import AgentContextPack
from app.agent.specialists.base import run_specialist_reasoning
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistToolObservation
from app.agent.specialists.tools.registry import build_default_observation_registry
from app.agent.specialists.tools.tool_loop import run_specialist_tool_loop
from app.config import Settings

_TOOL_LOOP_ON = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=True)
_TOOL_LOOP_OFF = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=False)


def _pack(**overrides: Any) -> AgentContextPack:
    defaults = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        user_context={"profile": {"degreeProgram": "BSc CS", "track": "cs", "catalogYear": 2024}},
        academic_context={},
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


def _specialist_input(**overrides: Any) -> SpecialistAgentInput:
    defaults: dict[str, Any] = dict(
        subtask_id="s1",
        agent_name="graduation_progress_agent",
        objective="Determine remaining requirements toward graduation.",
        user_message="What am I missing to graduate?",
    )
    defaults.update(overrides)
    return SpecialistAgentInput(**defaults)


# ---------------------------------------------------------------------------
# `run_specialist_tool_loop` (round executor) -- no ReasoningBlock involved.
# ---------------------------------------------------------------------------


def test_round_executor_builds_approved_observation_from_real_pack() -> None:
    outcome = run_specialist_tool_loop(
        tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="need the degree program")],
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
        compiled_context={},
        dependency_outputs={},
        max_requests_per_round=4,
        agent_context_pack=_pack(),
    )

    assert outcome.approved_observations == ["profile_summary"]
    assert outcome.requested_observations == ["profile_summary"]
    assert outcome.rejected_observations == []
    assert len(outcome.new_observations) == 1
    assert outcome.new_observations[0].name == "profile_summary"
    assert outcome.new_observations[0].status == "available"


def test_round_executor_reports_missing_when_source_unavailable() -> None:
    outcome = run_specialist_tool_loop(
        tool_requests=[ReasoningToolRequest(tool_name="graduation_audit_summary", purpose="need audit")],
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
        compiled_context={},
        dependency_outputs={},
        max_requests_per_round=4,
        agent_context_pack=_pack(),  # no graduationAudit on this pack
    )

    assert outcome.approved_observations == ["graduation_audit_summary"]
    assert outcome.new_observations == []
    assert "graduation_audit_summary" in outcome.missing_observations


def test_round_executor_rejects_unknown_and_disallowed_requests() -> None:
    outcome = run_specialist_tool_loop(
        tool_requests=[
            ReasoningToolRequest(tool_name="not_a_real_observation", purpose="x"),
            ReasoningToolRequest(tool_name="course_catalog_summary", purpose="x"),  # not allowed for this specialist
        ],
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
        compiled_context={},
        dependency_outputs={},
        max_requests_per_round=4,
        agent_context_pack=_pack(),
    )

    assert outcome.approved_observations == []
    assert set(outcome.rejected_observations) == {"not_a_real_observation", "course_catalog_summary"}


def test_round_executor_never_raises_on_empty_requests() -> None:
    outcome = run_specialist_tool_loop(
        tool_requests=[],
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
        compiled_context={},
        dependency_outputs={},
        max_requests_per_round=4,
        agent_context_pack=None,
    )

    assert outcome.approved_observations == []
    assert outcome.new_observations == []


def test_round_executor_uses_default_registry_when_none_supplied() -> None:
    outcome = run_specialist_tool_loop(
        tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="need it")],
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
        compiled_context={},
        dependency_outputs={},
        max_requests_per_round=4,
        agent_context_pack=_pack(),
        registry=build_default_observation_registry(),
    )
    assert outcome.approved_observations == ["profile_summary"]


# ---------------------------------------------------------------------------
# Fake, queue-based `ReasoningBlock` for exercising `base.run_specialist_reasoning`.
# ---------------------------------------------------------------------------


class QueuedFakeReasoningBlock:
    """Returns queued outputs in order, one per `.run()` call; raises `AssertionError`
    if called more times than outputs were queued (surfaces unexpected extra rounds)."""

    def __init__(self, outputs: list[ReasoningBlockOutput], *, raises: Exception | None = None) -> None:
        self._outputs = list(outputs)
        self._raises = raises
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        if self._raises is not None and len(self.calls) > len(self._outputs):
            raise self._raises
        assert self._outputs, "QueuedFakeReasoningBlock called more times than outputs were queued"
        return self._outputs.pop(0)


def _needs_tool_output(*, tool_requests: list[ReasoningToolRequest], iterations_used: int = 1) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="needs_tool",
        result=None,
        tool_requests=tool_requests,
        decision_summary="Need more data before answering.",
        confidence=0.3,
        schema_valid=False,
        iterations_used=iterations_used,
        repair_attempts_used=0,
    )


def _completed_output(result: dict[str, Any]) -> ReasoningBlockOutput:
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


def _needs_more_context_output() -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="needs_more_context",
        result=None,
        tool_requests=[],
        decision_summary="Still missing data.",
        missing_context=["completed_courses"],
        confidence=0.2,
        schema_valid=False,
        iterations_used=1,
        repair_attempts_used=0,
    )


_RESULT = {"decision_summary": "You still need 40 credits.", "creditsRemaining": 40.0}


async def _run(
    block: QueuedFakeReasoningBlock, *, settings: Settings, agent_context_pack: Any | None = None
) -> Any:
    return await run_specialist_reasoning(
        _specialist_input(),
        prompt_contract_name="specialist_graduation_progress_v1",
        output_schema_name="specialist_graduation_progress_output_v1",
        output_schema=SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA,
        risk_level="high",
        constraints=["test constraint"],
        success_criteria=["test criterion"],
        reasoning_block=block,
        settings=settings,
        agent_context_pack=agent_context_pack,
    )


# ---------------------------------------------------------------------------
# 1. Disabled tool loop preserves Phase 12 behavior.
# ---------------------------------------------------------------------------


async def test_disabled_tool_loop_preserves_phase12_fallback_behavior() -> None:
    block = QueuedFakeReasoningBlock([_needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")])])

    output = await _run(block, settings=_TOOL_LOOP_OFF)

    assert len(block.calls) == 1  # never re-ran reasoning
    assert output.status == "skipped"
    assert output.tool_loop_diagnostics is None


# ---------------------------------------------------------------------------
# 2 & 3. Enabled loop executes one approved observation round, then completes.
# ---------------------------------------------------------------------------


async def test_enabled_loop_executes_one_round_then_completes() -> None:
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="need it")]),
            _completed_output(_RESULT),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    assert len(block.calls) == 2
    assert output.status == "completed"
    assert output.tool_loop_diagnostics is not None
    assert output.tool_loop_diagnostics.status == "completed_with_tools"
    assert output.tool_loop_diagnostics.rounds_used == 1
    assert output.tool_loop_diagnostics.approved_observations == ["profile_summary"]

    second_call_context = block.calls[1].task_context
    observation_names = [obs["name"] for obs in second_call_context["deterministic_observations"]]
    assert "profile_summary" in observation_names


# ---------------------------------------------------------------------------
# 4. needs_tool with all rejected requests returns fallback/missing-context.
# ---------------------------------------------------------------------------


async def test_needs_tool_with_all_rejected_requests_still_reruns_and_falls_back() -> None:
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="not_a_real_observation", purpose="x")]),
            _needs_more_context_output(),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    assert len(block.calls) == 2
    assert output.status == "skipped"  # Phase 10 fallback for any non-"completed" final ReasoningBlockOutput
    assert output.tool_loop_diagnostics is not None
    assert output.tool_loop_diagnostics.status == "completed"  # loop itself ran fine, just approved nothing
    assert output.tool_loop_diagnostics.approved_observations == []
    assert "not_a_real_observation" in output.tool_loop_diagnostics.rejected_observations


# ---------------------------------------------------------------------------
# 5. needs_more_context (no tool request at all) returns safe fallback.
# ---------------------------------------------------------------------------


async def test_needs_more_context_without_tool_request_returns_safe_fallback() -> None:
    block = QueuedFakeReasoningBlock([_needs_more_context_output()])

    output = await _run(block, settings=_TOOL_LOOP_ON)

    assert len(block.calls) == 1  # tool loop never engages -- status wasn't needs_tool
    assert output.status == "skipped"
    assert output.tool_loop_diagnostics is None


# ---------------------------------------------------------------------------
# 6. ReasoningBlock failure (raises) returns safe fallback.
# ---------------------------------------------------------------------------


async def test_reasoning_block_raises_on_final_pass_returns_safe_fallback() -> None:
    block = QueuedFakeReasoningBlock(
        [_needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")])],
        raises=RuntimeError("boom"),
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    assert output.status == "skipped"
    assert output.tool_loop_diagnostics is not None
    assert output.tool_loop_diagnostics.status == "failed"


async def test_reasoning_block_raises_on_first_pass_returns_safe_fallback() -> None:
    block = QueuedFakeReasoningBlock([], raises=RuntimeError("boom"))

    output = await _run(block, settings=_TOOL_LOOP_ON)

    assert output.status == "skipped"
    assert output.tool_loop_diagnostics is None


# ---------------------------------------------------------------------------
# 7. Max rounds enforced.
# ---------------------------------------------------------------------------


async def test_max_rounds_enforced_at_configured_value() -> None:
    settings = Settings(
        AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=True,
        AGENT_SPECIALIST_TOOL_LOOP_MAX_ROUNDS=1,
    )
    # Specialist keeps asking for tools forever -- loop must stop after exactly 1 round.
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="completed_courses_summary", purpose="x")]),
        ]
    )

    output = await _run(block, settings=settings, agent_context_pack=_pack())

    assert len(block.calls) == 2  # 1 initial + 1 round, never a 3rd call
    assert output.tool_loop_diagnostics.rounds_used == 1
    assert output.tool_loop_diagnostics.status == "budget_exceeded"
    assert output.status == "skipped"


async def test_max_rounds_hard_capped_at_two_even_when_configured_higher() -> None:
    settings = Settings(
        AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=True,
        AGENT_SPECIALIST_TOOL_LOOP_MAX_ROUNDS=99,
    )
    assert settings.resolved_agent_specialist_tool_loop_max_rounds() == 2

    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="completed_courses_summary", purpose="x")]),
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
        ]
    )

    output = await _run(block, settings=settings, agent_context_pack=_pack())

    assert len(block.calls) == 3  # 1 initial + hard-capped 2 rounds, never a 4th call
    assert output.tool_loop_diagnostics.rounds_used == 2


# ---------------------------------------------------------------------------
# 8. Max requests per round enforced (flows through to config resolution).
# ---------------------------------------------------------------------------


async def test_max_requests_per_round_enforced_via_settings() -> None:
    settings = Settings(
        AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=True,
        AGENT_SPECIALIST_TOOL_LOOP_MAX_REQUESTS_PER_ROUND=1,
    )
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(
                tool_requests=[
                    ReasoningToolRequest(tool_name="profile_summary", purpose="x"),
                    ReasoningToolRequest(tool_name="completed_courses_summary", purpose="x"),
                ]
            ),
            _completed_output(_RESULT),
        ]
    )

    output = await _run(block, settings=settings, agent_context_pack=_pack())

    assert output.tool_loop_diagnostics.approved_observations == ["profile_summary"]
    assert "completed_courses_summary" in output.tool_loop_diagnostics.rejected_observations


async def test_max_requests_per_round_hard_capped_at_eight() -> None:
    settings = Settings(AGENT_SPECIALIST_TOOL_LOOP_MAX_REQUESTS_PER_ROUND=999)
    assert settings.resolved_agent_specialist_tool_loop_max_requests_per_round() == 8


# ---------------------------------------------------------------------------
# 9. Raw tool request arguments are not stored in diagnostics.
# ---------------------------------------------------------------------------


async def test_raw_tool_request_arguments_never_appear_in_diagnostics() -> None:
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(
                tool_requests=[
                    ReasoningToolRequest(
                        tool_name="profile_summary", purpose="x", arguments={"secretArg": "TOP_SECRET_VALUE"}
                    )
                ]
            ),
            _completed_output(_RESULT),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    diagnostics_text = str(output.tool_loop_diagnostics.model_dump())
    assert "TOP_SECRET_VALUE" not in diagnostics_text
    assert "secretArg" not in diagnostics_text


# ---------------------------------------------------------------------------
# 10. Raw observation summaries are not stored on the diagnostics object.
# ---------------------------------------------------------------------------


async def test_raw_observation_summaries_never_appear_in_diagnostics() -> None:
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _completed_output(_RESULT),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack(
        user_context={"profile": {"degreeProgram": "VERY_SPECIFIC_DEGREE_NAME_XYZ"}}
    ))

    diagnostics_text = str(output.tool_loop_diagnostics.model_dump())
    assert "VERY_SPECIFIC_DEGREE_NAME_XYZ" not in diagnostics_text


# ---------------------------------------------------------------------------
# 11. proposed_actions still stripped after the tool loop runs.
# ---------------------------------------------------------------------------


async def test_proposed_actions_still_stripped_after_tool_loop() -> None:
    result_with_actions = {**_RESULT, "proposed_actions": [{"actionType": "save_semester_plan"}]}
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _completed_output(result_with_actions),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    assert output.proposed_actions == []
    assert "specialist_proposed_actions_blocked" in output.warnings


# ---------------------------------------------------------------------------
# 12. No chain-of-thought fields appear anywhere in the final output.
# ---------------------------------------------------------------------------


async def test_no_chain_of_thought_fields_appear_after_tool_loop() -> None:
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _completed_output(_RESULT),
        ]
    )

    output = await _run(block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack())

    dumped_text = str(output.model_dump())
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in dumped_text


# ---------------------------------------------------------------------------
# Additional: existing deterministic_observations are preserved/merged, not replaced.
# ---------------------------------------------------------------------------


async def test_existing_deterministic_observations_are_preserved_and_merged() -> None:
    initial_observation = SpecialistToolObservation(name="requirement_bucket_summary", summary={"count": 2})
    block = QueuedFakeReasoningBlock(
        [
            _needs_tool_output(tool_requests=[ReasoningToolRequest(tool_name="profile_summary", purpose="x")]),
            _completed_output(_RESULT),
        ]
    )

    output = await run_specialist_reasoning(
        _specialist_input(deterministic_observations=[initial_observation]),
        prompt_contract_name="specialist_graduation_progress_v1",
        output_schema_name="specialist_graduation_progress_output_v1",
        output_schema=SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA,
        risk_level="high",
        constraints=["test constraint"],
        success_criteria=["test criterion"],
        reasoning_block=block,
        settings=_TOOL_LOOP_ON,
        agent_context_pack=_pack(),
    )

    second_call_context = block.calls[1].task_context
    observation_names = {obs["name"] for obs in second_call_context["deterministic_observations"]}
    assert observation_names == {"requirement_bucket_summary", "profile_summary"}
    assert output.status == "completed"
