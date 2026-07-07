"""Integration tests: the three real Phase 10 specialist agents wired through
the Phase 13 bounded tool-request loop (`base.run_specialist_reasoning`).

All tests use a fake, queue-based `ReasoningBlock` -- no real LLM call is
made anywhere in this file.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput, ReasoningToolRequest
from app.agent.schemas import AgentContextPack
from app.agent.specialists.course_catalog_agent import run_course_catalog_agent
from app.agent.specialists.graduation_progress_agent import run_graduation_progress_agent
from app.agent.specialists.requirement_explanation_agent import run_requirement_explanation_agent
from app.agent.specialists.schemas import SpecialistAgentInput
from app.config import Settings

_TOOL_LOOP_ON = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_TOOL_LOOP_ENABLED=True)


class QueuedFakeReasoningBlock:
    def __init__(self, outputs: list[ReasoningBlockOutput]) -> None:
        self._outputs = list(outputs)
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self._outputs, "QueuedFakeReasoningBlock called more times than outputs were queued"
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


def _pack(**overrides: Any) -> AgentContextPack:
    defaults = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        user_context={
            "profile": {"degreeProgram": "BSc CS"},
            "completedCourses": ["234123"],
        },
        academic_context={
            "course": {"id": "x1", "courseNumber": "234123", "title": "Intro CS", "credits": 3.5},
            "degreeRequirements": [{"id": "r1", "name": "Intro CS", "minCredits": 5.0}],
            "requirementContribution": {"category": "core", "satisfies": True},
        },
        retrieved_wiki_context=[],
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


def _specialist_input(agent_name: str) -> SpecialistAgentInput:
    return SpecialistAgentInput(
        subtask_id="s1",
        agent_name=agent_name,  # type: ignore[arg-type]
        objective="test objective",
        user_message="test message",
    )


# ---------------------------------------------------------------------------
# 1. Graduation specialist can request graduation observations.
# ---------------------------------------------------------------------------


async def test_graduation_specialist_can_request_graduation_audit_observation() -> None:
    block = QueuedFakeReasoningBlock(
        [_needs_tool("graduation_audit_summary"), _completed({"creditsRemaining": 40.0})]
    )

    output = await run_graduation_progress_agent(
        _specialist_input("graduation_progress_agent"),
        reasoning_block=block,
        settings=_TOOL_LOOP_ON,
        agent_context_pack=_pack(academic_context={"graduationAudit": {"creditsEarned": 80.0, "creditsRequired": 120.0}}),
    )

    assert output.status == "completed"
    assert output.tool_loop_diagnostics.approved_observations == ["graduation_audit_summary"]


# ---------------------------------------------------------------------------
# 2. Course specialist can request course observations.
# ---------------------------------------------------------------------------


async def test_course_catalog_specialist_can_request_course_catalog_observation() -> None:
    block = QueuedFakeReasoningBlock(
        [_needs_tool("course_catalog_summary"), _completed({"decision_summary": "234123 is Intro CS"})]
    )

    output = await run_course_catalog_agent(
        _specialist_input("course_catalog_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
    )

    assert output.status == "completed"
    assert output.tool_loop_diagnostics.approved_observations == ["course_catalog_summary"]


# ---------------------------------------------------------------------------
# 3. Requirement specialist can request wiki/requirement observations.
# ---------------------------------------------------------------------------


async def test_requirement_explanation_specialist_can_request_requirement_contribution_observation() -> None:
    block = QueuedFakeReasoningBlock(
        [_needs_tool("requirement_contribution_summary"), _completed({"decision_summary": "satisfies core"})]
    )

    output = await run_requirement_explanation_agent(
        _specialist_input("requirement_explanation_agent"),
        reasoning_block=block,
        settings=_TOOL_LOOP_ON,
        agent_context_pack=_pack(),
    )

    assert output.status == "completed"
    assert output.tool_loop_diagnostics.approved_observations == ["requirement_contribution_summary"]


# ---------------------------------------------------------------------------
# 4. Specialist cannot request transcript rows/full catalog/raw PDF (these
# are simply not registered observation names -- there is no "tool" by that
# name to approve, regardless of which specialist asks).
# ---------------------------------------------------------------------------


async def test_specialist_cannot_request_unregistered_raw_data_names() -> None:
    for forbidden_name in ("transcript_rows", "full_catalog", "raw_pdf_bytes", "raw_context"):
        block = QueuedFakeReasoningBlock([_needs_tool(forbidden_name), _completed({"decision_summary": "done anyway"})])

        output = await run_course_catalog_agent(
            _specialist_input("course_catalog_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
        )

        assert output.tool_loop_diagnostics.approved_observations == []
        assert forbidden_name in output.tool_loop_diagnostics.rejected_observations


async def test_graduation_specialist_cannot_request_course_only_observation() -> None:
    """`course_catalog_summary` is allowed for `course_catalog_agent` but not
    for `graduation_progress_agent` -- the per-specialist allowlist must
    still apply inside the tool loop, not just at initial-observation time."""
    block = QueuedFakeReasoningBlock(
        [_needs_tool("course_catalog_summary"), _completed({"decision_summary": "done anyway"})]
    )

    output = await run_graduation_progress_agent(
        _specialist_input("graduation_progress_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
    )

    assert output.tool_loop_diagnostics.approved_observations == []
    assert "course_catalog_summary" in output.tool_loop_diagnostics.rejected_observations


# ---------------------------------------------------------------------------
# 5. Specialist tool loop diagnostics appear in compact summary.
# ---------------------------------------------------------------------------


async def test_tool_loop_diagnostics_have_compact_shape() -> None:
    from app.agent.specialists.tools.tool_loop_diagnostics import build_tool_loop_diagnostics_summary

    block = QueuedFakeReasoningBlock(
        [_needs_tool("profile_summary"), _completed({"decision_summary": "done"})]
    )

    output = await run_graduation_progress_agent(
        _specialist_input("graduation_progress_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
    )

    summary = build_tool_loop_diagnostics_summary(output.tool_loop_diagnostics)
    assert set(summary) == {
        "toolLoopStatus",
        "toolLoopRoundsUsed",
        "requestedObservationCount",
        "approvedObservationCount",
        "rejectedObservationCount",
        "requestedObservationNames",
        "rejectedObservationNames",
    }
    assert summary["toolLoopStatus"] == "completed_with_tools"
    assert summary["approvedObservationCount"] == 1


# ---------------------------------------------------------------------------
# 6 & 7. Specialist output validation/compare still work after the tool loop.
# ---------------------------------------------------------------------------


async def test_specialist_output_validation_still_works_after_tool_loop() -> None:
    from app.agent.specialists.validation import validate_specialist_output

    block = QueuedFakeReasoningBlock(
        [_needs_tool("profile_summary"), _completed({"decision_summary": "You still need 40 credits.", "creditsRemaining": 40.0})]
    )

    output = await run_graduation_progress_agent(
        _specialist_input("graduation_progress_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
    )

    result = validate_specialist_output(output, validation_enabled=True)
    assert result.status in ("passed", "passed_with_warnings", "failed", "skipped")
    assert result.agent_name == "graduation_progress_agent"


async def test_specialist_compare_still_works_after_tool_loop() -> None:
    from app.agent.specialists.compare import compare_workflow_and_specialist
    from app.agent.specialists.output_summarizer import summarize_specialist_output
    from app.agent.schemas import AgentResponse

    block = QueuedFakeReasoningBlock(
        [_needs_tool("profile_summary"), _completed({"decision_summary": "You still need 40 credits.", "creditsRemaining": 40.0})]
    )

    output = await run_graduation_progress_agent(
        _specialist_input("graduation_progress_agent"), reasoning_block=block, settings=_TOOL_LOOP_ON, agent_context_pack=_pack()
    )

    live_response = AgentResponse(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="You still need 40 credits.",
        blocks=[],
        warnings=[],
        used_sources=[],
        proposed_actions=[],
    )
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=live_response,
        specialist_output_summary=summarize_specialist_output(output),
    )
    assert comparison is not None
    assert comparison.comparable is True
