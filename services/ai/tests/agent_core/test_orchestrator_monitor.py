"""Unit tests for `app.agent_core.orchestrator.monitor` (docs/agent/AGENT_VISION.md §9)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import CertaintyTag, StateEntry


def _step(**overrides) -> PlanStep:
    defaults = dict(step_id="s1", objective="o")
    defaults.update(overrides)
    return PlanStep(**defaults)


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
    decision = await evaluate_step_result(_step(), _entry("failed"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "replan"
    assert adapter.calls == []  # never reaches the success-criteria check at all


async def test_partial_status_triggers_clarify(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([])
    decision = await evaluate_step_result(_step(), _entry("partial"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "clarify"
    assert adapter.calls == []  # never reaches the success-criteria check at all


async def test_succeeded_status_with_no_success_criteria_continues_without_an_llm_call(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([])
    decision = await evaluate_step_result(_step(), _entry("succeeded"), llm_adapter=adapter, block_id="blk-1")
    assert decision == "continue"
    assert adapter.calls == []


async def test_succeeded_status_continues_when_success_criteria_are_met(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"criteria_met": True, "unmet_criteria": []}])
    step = _step(success_criteria=["a numeric GPA is returned"])
    entry = _entry("succeeded", data={"gpa": 3.5})

    decision = await evaluate_step_result(step, entry, llm_adapter=adapter, block_id="blk-1")

    assert decision == "continue"


async def test_succeeded_status_downgrades_to_clarify_when_success_criteria_are_not_met(fake_llm_adapter_factory):
    # The specialist self-reported "succeeded", but the aggregated result
    # doesn't actually cover the step's own declared success_criteria -- this
    # is exactly the gap the task handler's internal checks can't catch,
    # since they only verify sub-steps against criteria THEY were given, not
    # the original top-level step's own criteria (see monitor.py's docstring).
    adapter = fake_llm_adapter_factory(
        [{"criteria_met": False, "unmet_criteria": ["semester GPAs for the last two semesters"]}]
    )
    step = _step(success_criteria=["cumulative GPA and semester GPAs for the last two semesters"])
    entry = _entry("succeeded", data={"gpa": 3.5})

    decision = await evaluate_step_result(step, entry, llm_adapter=adapter, block_id="blk-1")

    assert decision == "clarify"
