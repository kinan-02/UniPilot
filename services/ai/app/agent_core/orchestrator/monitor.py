"""Monitor (docs/agent/AGENT_VISION.md §9): checks a step's result against
the plan's own stated assumptions and decides whether to keep executing,
replan, or ask the user.

Minimal, rule-based for the skeleton -- real assumption-violation detection
(comparing `StateEntry` content against `PlanStep.assumptions_to_verify`
semantically) is explicit later work, not part of this pass.
"""

from __future__ import annotations

from typing import Literal

from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import StateEntry

MonitorDecision = Literal["continue", "replan", "clarify"]


def evaluate_step_result(step: PlanStep, entry: StateEntry) -> MonitorDecision:
    if entry.status == "failed":
        return "replan"
    if entry.status == "partial":
        return "clarify"
    return "continue"


__all__ = ["MonitorDecision", "evaluate_step_result"]
