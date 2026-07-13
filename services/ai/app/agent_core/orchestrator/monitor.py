"""Monitor (docs/agent/AGENT_VISION.md §9): checks a step's result against
the plan's own stated assumptions and decides whether to keep executing,
replan, or ask the user.

Status-based decisions (`failed`->replan, `partial`->clarify) were the
original skeleton's whole story -- a `succeeded` status alone was trusted at
face value. That was never actually redundant with the task handler's own
internal `check_success_criteria` calls: those only verify a SUB-step (an
atomic dispatch's own step, or one of the nested planner's own
self-authored sub-steps) against ITS OWN criteria. `task_handler.py`'s
`_nested_planner_input` now threads `step.success_criteria` in too (as
`constraints`), so the nested Planner is at least aiming at the real
target from round 1 -- but this outer check still matters as the final
verdict: a sub-step's own criteria can be satisfied while the aggregated
result still misses something the ORIGINAL step asked for. This is that
outer, final check -- reuses the same fail-closed `check_success_criteria`
primitive the task handler already relies on, applied one level up, and
returns its `unmet_criteria` back to the caller so a `clarify` verdict
carries actionable detail into the next Planner invocation instead of a
bare status.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.subagents.schemas import SubagentResult

MonitorDecision = Literal["continue", "replan", "clarify"]


class MonitorEvaluation(NamedTuple):
    """`unmet_criteria` is empty for `replan`/`continue` -- only a
    `clarify` verdict (the success-criteria check actually ran and found a
    gap) ever populates it. Callers must thread this into the next Planner
    invocation's `monitor_flags`/`replan_reason`: without it, a replan only
    knows a step's criteria weren't met, not WHICH ones or why, and tends to
    reissue an equivalent step that fails the identical way."""

    decision: MonitorDecision
    unmet_criteria: list[str]


async def evaluate_step_result(
    step: PlanStep, entry: StateEntry, *, llm_adapter: LLMAdapter, block_id: str
) -> MonitorEvaluation:
    if entry.status == "failed":
        return MonitorEvaluation("replan", [])
    if entry.status == "partial":
        return MonitorEvaluation("clarify", [])

    # status == "succeeded": still confirm this against the ORIGINAL step's
    # own success_criteria -- see module docstring for why this is not
    # redundant with the task handler's own internal checks. Skips the LLM
    # call entirely (via check_success_criteria's own short-circuit) when
    # the step declared no success_criteria at all.
    criteria_met, unmet_criteria = await check_success_criteria(
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
    if criteria_met:
        return MonitorEvaluation("continue", [])
    return MonitorEvaluation("clarify", unmet_criteria)


__all__ = ["MonitorDecision", "MonitorEvaluation", "evaluate_step_result"]
