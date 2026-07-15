"""Unit tests for `app.agent_core.orchestrator.monitor` (docs/agent/AGENT_VISION.md §9)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import CertaintyTag, NestedExecutionTrace, StateEntry


def _step(**overrides) -> PlanStep:
    defaults = dict(step_id="s1", objective="o")
    defaults.update(overrides)
    return PlanStep(**defaults)


# A minimal nested trace marks an entry as having come from the task
# handler's nested-subplan path -- whose internal checks were against its own
# sub-steps' criteria, so the monitor's outer check against the ORIGINAL
# step's criteria is NOT redundant there (unlike an atomic entry, which the
# task handler already verified against this step's own criteria).
_NESTED = NestedExecutionTrace(private_plan_id="p:s1", rounds_used=1)


def _entry(status: str, **overrides) -> StateEntry:
    defaults = dict(
        entry_id="s1-0",
        step_id="s1",
        role="retrieval",
        status=status,
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return StateEntry(**defaults)


async def test_failed_status_triggers_replan(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([])
    decision, unmet = await evaluate_step_result(_step(), _entry("failed"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "replan"
    assert unmet == []
    assert adapter.calls == []  # never reaches the success-criteria check at all


async def test_partial_status_triggers_clarify(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([])
    decision, unmet = await evaluate_step_result(_step(), _entry("partial"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "clarify"
    assert unmet == []
    assert adapter.calls == []  # never reaches the success-criteria check at all


async def test_succeeded_status_with_no_success_criteria_continues_without_an_llm_call(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([])
    decision, unmet = await evaluate_step_result(_step(), _entry("succeeded"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "continue"
    assert unmet == []
    assert adapter.calls == []


async def test_atomic_succeeded_step_skips_the_redundant_recheck(fake_llm_adapter_factory):
    # An atomic entry (nested_trace is None) was already verified against this
    # step's own success_criteria in the task handler before it could return
    # "succeeded" -- the monitor must NOT spend a second identical check call.
    adapter = fake_llm_adapter_factory([])  # any call would exhaust and raise
    step = _step(success_criteria=["a numeric GPA is returned"])
    entry = _entry("succeeded", data={"gpa": 3.5})  # nested_trace defaults to None -> atomic

    decision, unmet = await evaluate_step_result(step, entry, llm_adapter=adapter, block_id="blk-1")

    assert decision == "continue"
    assert unmet == []
    assert adapter.calls == []  # no redundant re-check


async def test_nested_succeeded_with_output_continues_without_an_llm_call(fake_llm_adapter_factory):
    # Deterministic outer check: a nested aggregate that produced structured
    # output is trusted as-is -- no LLM re-judges whether it covered "enough".
    adapter = fake_llm_adapter_factory([])  # any call would exhaust and raise
    step = _step(success_criteria=["a numeric GPA is returned"])
    entry = _entry("succeeded", data={"gpa": 3.5}, nested_trace=_NESTED)

    decision, unmet = await evaluate_step_result(step, entry, llm_adapter=adapter, block_id="blk-1")

    assert decision == "continue"
    assert unmet == []
    assert adapter.calls == []  # deterministic -- no success-criteria LLM call


async def test_nested_succeeded_with_no_output_downgrades_to_clarify(fake_llm_adapter_factory):
    # The one deterministic failure the outer check can still assert: a nested
    # entry self-reported "succeeded" yet carries no structured output at all.
    adapter = fake_llm_adapter_factory([])
    step = _step(success_criteria=["cumulative GPA and semester GPAs for the last two semesters"])
    entry = _entry("succeeded", data={}, nested_trace=_NESTED)

    decision, unmet = await evaluate_step_result(step, entry, llm_adapter=adapter, block_id="blk-1")

    assert decision == "clarify"
    assert unmet == ["step produced no structured output"]
    assert adapter.calls == []
