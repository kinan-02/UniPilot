"""Monitor (docs/agent/AGENT_VISION.md §9): checks a step's result against
the plan's own stated assumptions and decides whether to keep executing,
replan, or ask the user.

Status-based decisions (`failed`->replan, `partial`->clarify) were the
original skeleton's whole story -- a `succeeded` status alone was trusted at
face value. That was never actually redundant with the task handler's own
internal `check_success_criteria` calls: those only verify a SUB-step (an
atomic dispatch's own step, or one of the nested planner's own
self-authored sub-steps) against ITS OWN criteria -- the nested-planning
path never re-checks the aggregated result against the ORIGINAL top-level
step's declared `success_criteria` at all (`task_handler.py`'s
`_nested_planner_input` never even threads `step.success_criteria` into the
nested Planner's input, only `objective` and `assumptions_to_verify`). So a
`succeeded` `StateEntry` here still means "every internal sub-step met
whatever criteria IT was given," not necessarily "the ORIGINAL step's own
success_criteria are satisfied." This is that outer, final check -- reuses
the same fail-closed `check_success_criteria` primitive the task handler
already relies on, applied one level up.
"""

from __future__ import annotations

from typing import Literal

from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.subagents.schemas import SubagentResult

MonitorDecision = Literal["continue", "replan", "clarify"]


async def evaluate_step_result(
    step: PlanStep, entry: StateEntry, *, llm_adapter: LLMAdapter, block_id: str
) -> MonitorDecision:
    if entry.status == "failed":
        return "replan"
    if entry.status == "partial":
        return "clarify"

    # status == "succeeded": still confirm this against the ORIGINAL step's
    # own success_criteria -- see module docstring for why this is not
    # redundant with the task handler's own internal checks. Skips the LLM
    # call entirely (via check_success_criteria's own short-circuit) when
    # the step declared no success_criteria at all.
    criteria_met = await check_success_criteria(
        step=step,
        result=SubagentResult(
            status=entry.status,
            result=entry.data,
            certainty=entry.certainty,
            assumptions=entry.assumptions,
            warnings=entry.warnings,
            tool_audit_trail=entry.tool_audit_trail,
        ),
        llm_adapter=llm_adapter,
        block_id=block_id,
    )
    return "continue" if criteria_met else "clarify"


__all__ = ["MonitorDecision", "evaluate_step_result"]
