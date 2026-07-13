"""Tests for `SimulationPlanningReasoningBlock`/`run_simulation_planning_subagent`
(docs/agent/agent_plans/SIMULATION_PLANNING_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_simulation_planning_subagent`
entry point. Uses the REAL `mutate_state` tool (pure in-memory, no external
infra) but a stub `search_over_state` (the real one needs a configured
academic graph engine even for trivial cases -- verified empirically, not
available in this unit-test environment -- mirrors the stubbing approach
`test_interpretation_block.py` already used for `interpret_text`).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.subagents.simulation_planning_block import (
    _MAX_ROUNDS,
    _MIN_ROUNDS,
    run_simulation_planning_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.mutate_state import DESCRIPTOR as MUTATE_STATE_DESCRIPTOR
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry


class _FakeSearchInput(BaseModel):
    state: dict = {}
    constraints: list = []
    objective: str = ""


def _make_registry(*, search_ok: bool = True, unscheduled: list | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MUTATE_STATE_DESCRIPTOR)

    async def _search_over_state(payload: _FakeSearchInput) -> ToolOutputEnvelope:
        if not search_ok:
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_unavailable: simulated")
        return ToolOutputEnvelope(
            ok=True,
            data={
                "objective": payload.objective,
                "requiredCourses": ["00440105"],
                "satisfiedCourses": [],
                "alreadyPlannedCourses": [],
                "plan": {"2025-2": [{"courseNumber": "00440105", "credits": 3.5}]},
                "semestersUsed": 1,
                "unscheduledCourses": unscheduled or [],
            },
        )

    registry.register(
        ToolDescriptor(
            name="search_over_state",
            description="test stub",
            input_model=_FakeSearchInput,
            output_model=ToolOutputEnvelope,
            side_effect="compute",
            callable=_search_over_state,
        )
    )
    return registry


class _CountingToolRegistry:
    def __init__(self, inner: ToolRegistry) -> None:
        self._inner = inner
        self.call_count = 0

    def get(self, name: str):
        descriptor = self._inner.get(name)
        original_callable = descriptor.callable

        async def _counting_callable(payload):
            self.call_count += 1
            return await original_callable(payload)

        return descriptor.model_copy(update={"callable": _counting_callable})

    def has(self, name: str) -> bool:
        return self._inner.has(name)


def _context_package(tool_grant=("mutate_state", "search_over_state")) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Project what happens if I fail this course.",
        structured_fields=StepInstructionFields(goal="Simulate the disruption.", description="Simulate it."),
        dependency_state=[],
        tool_grant=list(tool_grant),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


def _need_tools(tool_name="mutate_state", arguments=None):
    return {
        "status": "need_tools",
        "tool_requests": [
            {
                "tool_name": tool_name,
                "arguments": arguments
                or {"base_state": {"completedCourses": [], "plannedSemesters": {}, "currentSemesterCode": "2025-1"}, "change": {"type": "fail_course", "courseNumber": "00440105", "semester": "2024-2"}},
            }
        ],
    }


def _ready_result():
    return {
        "status": "ready",
        "result": {
            "certainty_basis": "hypothetical_simulation",
            "confidence": 0.8,
            "assumptions": [],
            "outcome": {"semestersUsed": 1},
        },
    }


async def test_round_1_ready_is_not_honored_even_with_a_well_formed_result(fake_llm_adapter_factory):
    assert _MIN_ROUNDS == 2
    adapter = fake_llm_adapter_factory([_ready_result(), _need_tools(), _ready_result()])
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert len(adapter.calls) == 3
    assert result.status == "succeeded"
    assert registry.call_count == 1


async def test_happy_path_mutate_then_search_then_finalize(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _need_tools("mutate_state"),
            _need_tools("search_over_state", {"state": {}, "constraints": [], "objective": "minimize_semesters"}),
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 2
    assert len(result.tool_audit_trail) == 2
    assert result.certainty.basis == "hypothetical_simulation"


async def test_reflect_and_revise_after_a_failed_candidate_is_just_the_ordinary_loop(fake_llm_adapter_factory):
    # Round 1's search_over_state comes back with unscheduled courses (a
    # failed/incomplete candidate) -- round 2 just tries a different call,
    # no special "retry" code path needed.
    registry_ok_after_retry = _make_registry(unscheduled=[])
    adapter = fake_llm_adapter_factory(
        [
            _need_tools("search_over_state", {"state": {}, "constraints": [], "objective": "minimize_semesters"}),
            _need_tools("search_over_state", {"state": {}, "constraints": [{"type": "max_semesters", "value": 10}], "objective": "minimize_semesters"}),
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(registry_ok_after_retry)

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 2
    assert len(adapter.calls) == 3


async def test_malformed_tool_requests_repaired_before_execution(fake_llm_adapter_factory):
    # Same fix as retrieval_block's/interpretation_block's -- a round's
    # tool_requests previously went straight to execute_tool_round
    # unvalidated, so wrong keys (e.g. "name"/"params" instead of
    # "tool_name"/"arguments") silently wasted the whole round. Now it's
    # repaired first via the shared `_repair_tool_requests_if_needed` helper.
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "need_tools",
                "tool_requests": [
                    {"name": "search_over_state", "params": {"state": {}, "constraints": [], "objective": "minimize_semesters"}}
                ],
            },
            {
                "status": "need_tools",
                "tool_requests": [
                    {"tool_name": "search_over_state", "arguments": {"state": {}, "constraints": [], "objective": "minimize_semesters"}}
                ],
            },
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].tool_name == "search_over_state"
    # round1 (malformed) + repair + round2 (finalize) = 3 LLM calls.
    assert len(adapter.calls) == 3


async def test_tool_not_in_grant_skipped_without_aborting_round(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "need_tools",
                "tool_requests": [
                    {"tool_name": "search_over_state", "arguments": {"state": {}, "constraints": [], "objective": "minimize_semesters"}},
                    {
                        "tool_name": "mutate_state",
                        "arguments": {
                            "base_state": {"completedCourses": [], "plannedSemesters": {}, "currentSemesterCode": "2025-1"},
                            "change": {"type": "fail_course", "courseNumber": "00440105", "semester": "2024-2"},
                        },
                    },
                ],
            },
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(tool_grant=("mutate_state",)),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1  # only mutate_state actually executed
    assert len(result.tool_audit_trail) == 2
    assert result.tool_audit_trail[0].tool_name == "search_over_state"
    assert result.tool_audit_trail[0].output_ok is False


async def test_official_record_certainty_basis_is_rejected_by_the_restricted_enum(fake_llm_adapter_factory):
    bad_response = {
        "status": "ready",
        "result": {"certainty_basis": "official_record", "confidence": 0.9, "outcome": {"semestersUsed": 1}},
    }
    adapter = fake_llm_adapter_factory([_need_tools(), bad_response, bad_response, bad_response])
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("schema_repair_exhausted" in w for w in result.warnings)


async def test_round_budget_exhausted_forces_finalize_and_fails_closed_if_no_result(fake_llm_adapter_factory):
    responses = [{"status": "need_tools", "tool_requests": []} for _ in range(_MAX_ROUNDS)]
    adapter = fake_llm_adapter_factory(responses)
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert len(adapter.calls) == _MAX_ROUNDS
    assert any("round_budget_exhausted" in w for w in result.warnings)


async def test_malformed_result_on_finalize_triggers_repair(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _need_tools(),
            {"status": "ready", "result": {"certainty_basis": "hypothetical_simulation"}},  # missing confidence/outcome
            {"certainty_basis": "hypothetical_simulation", "confidence": 0.8, "outcome": {"semestersUsed": 1}},
        ]
    )
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(adapter.calls) == 3


async def test_repair_exhausted_fails_closed(fake_llm_adapter_factory):
    bad_response = {"status": "ready", "result": {"certainty_basis": "hypothetical_simulation"}}
    bad_repair = {"certainty_basis": "hypothetical_simulation"}
    adapter = fake_llm_adapter_factory([_need_tools(), bad_response, bad_repair, bad_repair])
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("schema_repair_exhausted" in w for w in result.warnings)


async def test_returns_subagent_result_shape_matching_the_generic_paths_output(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_need_tools(), _ready_result()])
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status in ("succeeded", "partial", "failed")
    assert result.certainty is not None
    assert result.certainty.basis in ("hypothetical_simulation", "predicted_pattern")
    assert isinstance(result.assumptions, list)
    assert isinstance(result.warnings, list)
    assert isinstance(result.tool_audit_trail, list)
    assert result.needs_another_round is False


async def test_certainty_defaults_to_hypothetical_simulation_never_llm_interpretation(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"status": "need_tools", "tool_requests": []} for _ in range(_MAX_ROUNDS)])
    registry = _CountingToolRegistry(_make_registry())

    result = await run_simulation_planning_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert result.certainty.basis == "hypothetical_simulation"
