"""Tests for `CalculationValidationReasoningBlock`/`run_calculation_validation_subagent`
(docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 2).

All scenarios exercised through the public `run_calculation_validation_subagent`
entry point (never the private block class directly) -- it's the one thing
`task_handler.py` actually calls, and exercising it end-to-end also covers
the `SubagentResult` mapping. `dependency_state` is left empty throughout:
none of these scenarios need a real fact lookup by `ref` (that's already
covered by `test_expression_tree.py`), only the block's own draft -> validate
-> repair -> execute control flow.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.planning.state import CertaintyTag, StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.subagents.calculation_validation_block import (
    _MAX_REPAIR_ATTEMPTS,
    run_calculation_validation_subagent,
)

# A successful calc result now goes through one targeted plausibility check
# (the ONE per-step LLM check we keep -- semantic correctness of a computed
# number is the one thing no schema catches). Tests that reach a successful
# evaluation queue this verdict after the draft/repair responses.
_PLAUSIBLE = {"plausible": True, "reason": "the expression answers the objective"}
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolRegistry


def _context_package(tool_grant=("apply_deterministic_rule",)) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Compute the value.",
        structured_fields=StepInstructionFields(goal="Compute the value.", description="Compute the value."),
        dependency_state=[],
        tool_grant=list(tool_grant),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


class _CountingToolRegistry:
    """Wraps a real `ToolRegistry`, counting how many times a tool's own
    `callable` actually runs -- used to assert "the tool was never called"
    in the repair-exhausted scenario."""

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


async def test_draft_valid_on_first_try_calls_tool_once_and_returns_result(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [{"op": "add", "left": {"const": 2}, "right": {"const": 3}}, _PLAUSIBLE]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert result.result == {"type": "expression", "result": 5, "trace": ["2 + 3 = 5"]}
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0
    assert registry.call_count == 1
    assert len(adapter.calls) == 2  # draft + plausibility check


async def test_invalid_draft_bad_ref_triggers_one_repair_call_with_the_exact_error(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {"op": "add", "left": {"ref": "missing_fact"}, "right": {"const": 1}},
            {"op": "add", "left": {"const": 5}, "right": {"const": 1}},
            _PLAUSIBLE,
        ]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert result.result == {"type": "expression", "result": 6, "trace": ["5 + 1 = 6"]}
    assert registry.call_count == 1
    assert len(adapter.calls) == 3  # invalid draft + repair + plausibility check
    repair_prompt = adapter.calls[1]["user_prompt"]
    assert "missing_fact" in repair_prompt
    assert "not found in facts" in repair_prompt


async def test_repair_exhausted_fails_closed_without_ever_calling_the_tool(fake_llm_adapter_factory):
    bad_response = {"op": "add", "left": {"ref": "missing_fact"}, "right": {"const": 1}}
    adapter = fake_llm_adapter_factory([bad_response] * (_MAX_REPAIR_ATTEMPTS + 1))
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert registry.call_count == 0
    assert len(adapter.calls) == _MAX_REPAIR_ATTEMPTS + 1
    assert any("calculation_validation_failed" in warning for warning in result.warnings)


async def test_tool_runtime_failure_on_a_validated_tree_fails_closed_not_a_retry(fake_llm_adapter_factory):
    """`divide` by a `const` zero passes `validate_expression_tree` (it only
    checks structure, not values) but fails at evaluation time -- a genuine
    runtime surprise, not a structural draft mistake, so it must not trigger
    the repair loop."""
    adapter = fake_llm_adapter_factory([{"op": "divide", "left": {"const": 10}, "right": {"const": 0}}])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert len(adapter.calls) == 1  # no repair call -- this wasn't a structural draft error
    assert registry.call_count == 1  # the tool WAS called -- this is its own failure, not skipped
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].output_ok is False


async def test_tool_not_in_grant_fails_closed_without_calling_the_tool(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"op": "add", "left": {"const": 2}, "right": {"const": 3}}])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(tool_grant=()),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert registry.call_count == 0


async def test_returns_subagent_result_shape_matching_the_generic_paths_output(fake_llm_adapter_factory):
    """Same shape `build_subagent_result` produces today -- so `task_handler.py`'s
    downstream handling needs zero changes regardless of which path ran."""
    adapter = fake_llm_adapter_factory(
        [{"op": "add", "left": {"const": 2}, "right": {"const": 3}}, _PLAUSIBLE]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status in ("succeeded", "partial", "failed")
    assert result.certainty is not None
    assert isinstance(result.assumptions, list)
    assert isinstance(result.warnings, list)
    assert isinstance(result.tool_audit_trail, list)
    assert result.tool_audit_trail[0].tool_name == "apply_deterministic_rule"
    assert result.needs_another_round is False


async def test_implausible_result_triggers_a_redraft_that_recovers(fake_llm_adapter_factory):
    # The deterministic engine computes correctly, but the plausibility check
    # catches a valid-but-WRONG expression (e.g. a spurious filter). Its critique
    # is fed back into a bounded re-draft, which then passes.
    adapter = fake_llm_adapter_factory(
        [
            {"op": "add", "left": {"const": 2}, "right": {"const": 3}},  # draft -> 5
            {"plausible": False, "reason": "drop the courseNumber filter -- the objective asks for the total"},
            {"op": "add", "left": {"const": 60}, "right": {"const": 2}},  # re-draft -> 62
            {"plausible": True, "reason": "now aggregates all courses"},
        ]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert result.result == {"type": "expression", "result": 62, "trace": ["60 + 2 = 62"]}
    assert registry.call_count == 2  # evaluated the draft and the re-draft
    assert len(adapter.calls) == 4  # draft + plausibility + re-draft + plausibility
    # The plausibility critique must reach the re-draft prompt so it can act on it.
    assert "drop the courseNumber filter" in adapter.calls[2]["user_prompt"]
    assert not any("calculation_implausible" in warning for warning in result.warnings)


async def test_implausible_after_the_redraft_budget_is_marked_partial(fake_llm_adapter_factory):
    # Still implausible after the one allowed re-draft: keep the number (so it is
    # not silently discarded) but mark the step partial -> the orchestrator
    # replans rather than reporting a wrong number as fact.
    adapter = fake_llm_adapter_factory(
        [
            {"op": "add", "left": {"const": 2}, "right": {"const": 3}},  # draft -> 5
            {"plausible": False, "reason": "wrong subset"},
            {"op": "add", "left": {"const": 1}, "right": {"const": 1}},  # re-draft -> 2
            {"plausible": False, "reason": "still the wrong subset"},
        ]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "partial"
    assert any("calculation_implausible" in warning for warning in result.warnings)
    assert result.certainty.confidence == 0.3
    # The last computed number is still returned, for transparency in the replan.
    assert result.result == {"type": "expression", "result": 2, "trace": ["1 + 1 = 2"]}
    assert registry.call_count == 2


async def test_plausibility_checker_error_fails_open_and_keeps_the_result():
    # A flaky plausibility checker must never discard a correctly-computed
    # result -- the check fails OPEN (treated as plausible).
    class _DraftThenRaiseAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *, raw_model_text_out=None, **_):
            self.calls += 1
            if self.calls == 1:
                return {"op": "add", "left": {"const": 2}, "right": {"const": 3}}
            raise LLMAdapterError("plausibility_boom")

        async def complete_text(self, **_):
            raise AssertionError("calc block does not use complete_text")

    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=_DraftThenRaiseAdapter(),
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert result.result == {"type": "expression", "result": 5, "trace": ["2 + 3 = 5"]}
    assert not any("calculation_implausible" in warning for warning in result.warnings)


async def test_dependency_facts_nested_under_data_facts_are_promoted_to_top_level_refs(
    fake_llm_adapter_factory,
):
    """Regression guard: `ref` is a flat, single-hop lookup
    (`expression_tree.py`'s `facts[node.ref]`, no dotted-path traversal), but
    a retrieval-shaped dependency's actual fetched values live nested one
    level deeper, under its own `data["facts"]`. Keying the calc-validation
    `facts` dict only by step_id handed the model the whole retrieval
    envelope (confidence, source_ref, ...) where a list/number was expected,
    producing "of_not_a_list"/"ref not found" no matter how many repair
    attempts it got (found via a live-eval run against a real seeded
    student). Confirms a fact nested under `data["facts"]` is now directly
    ref-able by its own key, resolved for real through the actual
    `apply_deterministic_rule` tool call."""
    dependency = StateEntry(
        entry_id="2a-0",
        step_id="2a",
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={"certainty_basis": "official_record", "confidence": 0.9, "facts": {"gpa": 3.4}},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )
    context_package = SubagentContextPackage(
        rendered_prompt="Check the GPA.",
        structured_fields=StepInstructionFields(goal="Check the GPA.", description="Check the GPA."),
        dependency_state=[dependency],
        tool_grant=["apply_deterministic_rule"],
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )
    adapter = fake_llm_adapter_factory(
        [
            {"op": "compare", "left": {"ref": "gpa"}, "comparator": ">=", "right": {"const": 2.0}},
            _PLAUSIBLE,
        ]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_calculation_validation_subagent(
        context_package=context_package,
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
