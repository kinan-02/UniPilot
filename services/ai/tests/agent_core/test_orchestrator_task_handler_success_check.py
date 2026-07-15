"""Tests for the DETERMINISTIC `check_success_criteria` (no LLM call).

The success check no longer asks an LLM whether a specialist's result
"satisfies" a step's success_criteria: at runtime there is no ground truth
for what a step should have returned -- if there were, executing the step
would be pointless -- so an LLM re-judging sufficiency only added a call per
step and produced false `partial` downgrades. The check now verifies only
what IS deterministically knowable: the specialist did not fail, and it
produced structurally usable (non-empty) output.
"""

from __future__ import annotations

from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import CertaintyTag
from app.agent_core.subagents.schemas import SubagentResult


def _result(data: dict | None = None, status: str = "succeeded") -> SubagentResult:
    return SubagentResult(
        status=status,
        result=data if data is not None else {},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        assumptions=[],
        warnings=[],
        tool_audit_trail=[],
    )


class _ExplodingAdapter:
    """Any LLM call is now a bug -- the check must be purely deterministic."""

    async def complete_json(self, **_: object) -> dict:
        raise AssertionError("check_success_criteria must not call the LLM")

    async def complete_text(self, **_: object) -> str:
        raise AssertionError("check_success_criteria must not call the LLM")


def _step(success_criteria: list[str]) -> PlanStep:
    return PlanStep(
        step_id="1a",
        objective="fetch a thing",
        depends_on=[],
        success_criteria=success_criteria,
        assumptions_to_verify=[],
    )


async def test_no_criteria_is_met_without_any_llm_call():
    met, unmet = await check_success_criteria(
        step=_step([]), result=_result({"x": 1}), llm_adapter=_ExplodingAdapter(), block_id="b"
    )
    assert met is True
    assert unmet == []


async def test_criteria_with_nonempty_output_is_met_without_llm_call():
    # A partially-covering result now passes: there is no runtime ground truth
    # for "enough", and the specialist already schema-validated its own output.
    met, unmet = await check_success_criteria(
        step=_step(["cumulative GPA AND last two semester GPAs"]),
        result=_result({"gpa": 3.5}),
        llm_adapter=_ExplodingAdapter(),
        block_id="b",
    )
    assert met is True
    assert unmet == []


async def test_empty_output_with_criteria_is_not_met():
    met, unmet = await check_success_criteria(
        step=_step(["cumulative GPA returned"]),
        result=_result({}),
        llm_adapter=_ExplodingAdapter(),
        block_id="b",
    )
    assert met is False
    assert unmet  # a non-empty reason is surfaced for the replan


async def test_failed_status_with_criteria_is_not_met():
    met, _ = await check_success_criteria(
        step=_step(["cumulative GPA returned"]),
        result=_result({"gpa": 3.5}, status="failed"),
        llm_adapter=_ExplodingAdapter(),
        block_id="b",
    )
    assert met is False


async def test_non_dict_output_with_criteria_is_not_met():
    met, _ = await check_success_criteria(
        step=_step(["something"]),
        result=_result(None),
        llm_adapter=_ExplodingAdapter(),
        block_id="b",
    )
    assert met is False
