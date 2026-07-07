"""Bounded replan/revision cycle policy (Phase 28.2).

Same-turn diagnostic accounting only — cross-turn persistence is not yet
available. The budget prevents unbounded repair/regeneration loops within one
diagnostic repair evaluation.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel

from app.agent.planner.repair_schemas import PlanExecutionDelta, RepairMode

ReplanEscalationAction = Literal[
    "allow_repair",
    "allow_regeneration",
    "abort_safely",
    "ask_clarification",
    "escalate_strategy",
]

_DEFAULT_MAX_REPAIRS = 2
_DEFAULT_MAX_REGENERATIONS = 1


class ReplanCycleBudget(BaseModel):
    goal_fingerprint: str
    repair_attempts: int = 0
    regeneration_attempts: int = 0
    max_repairs: int = _DEFAULT_MAX_REPAIRS
    max_regenerations: int = _DEFAULT_MAX_REGENERATIONS
    exhausted: bool = False
    escalation_reason: str | None = None


class ReplanCycleDecision(BaseModel):
    proposed_mode: RepairMode
    effective_mode: RepairMode
    escalation_action: ReplanEscalationAction
    budget: ReplanCycleBudget
    bounded: bool = False


def goal_fingerprint(user_goal: str) -> str:
    normalized = " ".join(str(user_goal or "").strip().lower().split())
    if not normalized:
        return "empty-goal"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_replan_cycle_budget(
    *,
    user_goal: str,
    max_repairs: int = _DEFAULT_MAX_REPAIRS,
    max_regenerations: int = _DEFAULT_MAX_REGENERATIONS,
) -> ReplanCycleBudget:
    return ReplanCycleBudget(
        goal_fingerprint=goal_fingerprint(user_goal),
        max_repairs=max(1, int(max_repairs)),
        max_regenerations=max(0, int(max_regenerations)),
    )


def _repair_delta_kinds() -> frozenset[str]:
    return frozenset({"subtask_failed", "assumption_violated", "validation_failed", "budget_exceeded"})


def _regeneration_delta_kinds() -> frozenset[str]:
    return frozenset({"goal_drift", "user_goal_changed", "exhausted_path"})


def count_repair_cycles_from_deltas(deltas: list[PlanExecutionDelta]) -> tuple[int, int]:
    """Estimate repair/regeneration pressure from monitor deltas in one turn."""
    repair_count = sum(1 for delta in deltas if delta.kind in _repair_delta_kinds())
    regeneration_count = sum(1 for delta in deltas if delta.kind in _regeneration_delta_kinds())
    return repair_count, regeneration_count


def apply_replan_cycle_bounds(
    *,
    budget: ReplanCycleBudget,
    proposed_mode: RepairMode,
    deltas: list[PlanExecutionDelta] | None = None,
) -> ReplanCycleDecision:
    """Apply bounded replan policy. Diagnostic-only — never enables live replan."""
    updated = budget.model_copy(deep=True)
    delta_repair, delta_regen = count_repair_cycles_from_deltas(list(deltas or []))
    updated = updated.model_copy(
        update={
            "repair_attempts": updated.repair_attempts + delta_repair,
            "regeneration_attempts": updated.regeneration_attempts + delta_regen,
        }
    )

    effective_mode = proposed_mode
    escalation: ReplanEscalationAction = "allow_repair" if proposed_mode == "repair" else "allow_regeneration"
    bounded = False

    if proposed_mode == "repair" and updated.repair_attempts > updated.max_repairs:
        effective_mode = "abort_safely"
        escalation = "abort_safely"
        bounded = True
        updated = updated.model_copy(
            update={
                "exhausted": True,
                "escalation_reason": "repair_attempts_exceeded",
            }
        )
    elif proposed_mode == "regenerate" and updated.regeneration_attempts > updated.max_regenerations:
        effective_mode = "clarify_first"
        escalation = "ask_clarification"
        bounded = True
        updated = updated.model_copy(
            update={
                "exhausted": True,
                "escalation_reason": "regeneration_attempts_exceeded",
            }
        )
    elif proposed_mode == "regenerate" and updated.repair_attempts > updated.max_repairs:
        effective_mode = "abort_safely"
        escalation = "escalate_strategy"
        bounded = True
        updated = updated.model_copy(
            update={
                "exhausted": True,
                "escalation_reason": "combined_replan_pressure_exceeded",
            }
        )
    elif proposed_mode == "repair":
        escalation = "allow_repair"
    elif proposed_mode == "regenerate":
        escalation = "allow_regeneration"

    return ReplanCycleDecision(
        proposed_mode=proposed_mode,
        effective_mode=effective_mode,
        escalation_action=escalation,
        budget=updated,
        bounded=bounded,
    )


def build_replan_cycle_metadata(decision: ReplanCycleDecision) -> dict[str, str | int | bool | None]:
    budget = decision.budget
    return {
        "goalFingerprint": budget.goal_fingerprint,
        "repairAttempts": budget.repair_attempts,
        "regenerationAttempts": budget.regeneration_attempts,
        "maxRepairs": budget.max_repairs,
        "maxRegenerations": budget.max_regenerations,
        "exhausted": budget.exhausted,
        "escalationReason": budget.escalation_reason,
        "proposedMode": decision.proposed_mode,
        "effectiveMode": decision.effective_mode,
        "escalationAction": decision.escalation_action,
        "bounded": decision.bounded,
        "sameTurnOnly": True,
    }
