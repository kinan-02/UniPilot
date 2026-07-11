"""Tests for `app.agent_core.orchestrator.task_handler_success_check`."""

from __future__ import annotations

from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import CertaintyTag
from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.subagents.schemas import SubagentResult


def _result(data: dict | None = None) -> SubagentResult:
    return SubagentResult(
        status="succeeded",
        result=data or {},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        assumptions=[],
        warnings=[],
        tool_audit_trail=[],
    )


async def test_no_llm_call_when_success_criteria_is_empty(fake_llm_adapter_factory):
    step = PlanStep(step_id="1a", objective="do a thing", depends_on=[], success_criteria=[], assumptions_to_verify=[])
    adapter = fake_llm_adapter_factory([])  # exhausting would raise -- proves zero calls happen

    met = await check_success_criteria(step=step, result=_result(), llm_adapter=adapter, block_id="blk-1")

    assert met is True
    assert len(adapter.calls) == 0


async def test_criteria_met_returns_true(fake_llm_adapter_factory):
    step = PlanStep(
        step_id="1a", objective="fetch GPA", depends_on=[],
        success_criteria=["cumulative GPA returned"], assumptions_to_verify=[],
    )
    adapter = fake_llm_adapter_factory([{"criteria_met": True, "unmet_criteria": []}])

    met = await check_success_criteria(step=step, result=_result({"gpa": 3.5}), llm_adapter=adapter, block_id="blk-1")

    assert met is True


async def test_criteria_not_met_returns_false(fake_llm_adapter_factory):
    step = PlanStep(
        step_id="1a", objective="fetch GPA breakdown", depends_on=[],
        success_criteria=["cumulative GPA AND last two semester GPAs"], assumptions_to_verify=[],
    )
    adapter = fake_llm_adapter_factory(
        [{"criteria_met": False, "unmet_criteria": ["last two semester GPAs missing"]}]
    )

    met = await check_success_criteria(step=step, result=_result({"gpa": 3.5}), llm_adapter=adapter, block_id="blk-1")

    assert met is False


async def test_raising_adapter_fails_closed_to_false():
    step = PlanStep(
        step_id="1a", objective="fetch GPA", depends_on=[],
        success_criteria=["cumulative GPA returned"], assumptions_to_verify=[],
    )

    class RaisingAdapter:
        async def complete_json(self, **kwargs):
            raise LLMAdapterError("boom")

    met = await check_success_criteria(step=step, result=_result(), llm_adapter=RaisingAdapter(), block_id="blk-1")

    assert met is False


async def test_hollow_criteria_met_true_with_unmet_listed_fails_closed(fake_llm_adapter_factory):
    step = PlanStep(
        step_id="1a", objective="fetch GPA", depends_on=[],
        success_criteria=["cumulative GPA returned"], assumptions_to_verify=[],
    )
    adapter = fake_llm_adapter_factory(
        [{"criteria_met": True, "unmet_criteria": ["something still missing"]}] * 2
    )

    met = await check_success_criteria(step=step, result=_result(), llm_adapter=adapter, block_id="blk-1")

    assert met is False
