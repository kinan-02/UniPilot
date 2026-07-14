"""Turn-scoped ledger of how many times each step objective has been flagged
for replan (docs/planning/ADAPTIVE_PLANNING_EXTRACTION_PLAN.md §4.1).

The direct generalization of `UnresolvableEntityRegistry` from *entities* to
*steps/regions*: that registry stops the Planner re-searching a dead-end
entity; this one stops the loop re-attempting a dead-end step. When the same
objective has been re-tried past a threshold and still fails, its objective is
surfaced to the Planner as an `exhausted_step` -- "do not reschedule
equivalent work; conclude or clarify." This is the general cure for the replan
thrash the Algorithms case was one instance of.

Plain mutable collaborator (like `UnresolvableEntityRegistry` / `ToolCallCache`),
created fresh per turn and threaded through the loop -- never a module-level
global (that would leak one student's dead ends into another's) and never
serialized or part of any schema.
"""

from __future__ import annotations


def _normalize(objective: str) -> str:
    return objective.strip().lower()


class ReplanLedger:
    def __init__(self) -> None:
        self._attempts: dict[str, int] = {}  # normalized objective -> attempt count
        self._display: dict[str, str] = {}  # normalized objective -> first-seen original casing

    def record(self, step_objective: str, reason: str) -> None:
        """Count one replan attempt for this objective. `reason` is accepted
        for symmetry with `UnresolvableEntityRegistry.record` and future
        diagnostics; the count is what drives escalation."""
        key = _normalize(step_objective)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        self._display.setdefault(key, step_objective.strip())

    def attempts(self, step_objective: str) -> int:
        return self._attempts.get(_normalize(step_objective), 0)

    def exhausted(self, *, threshold: int = 2) -> list[str]:
        """Objectives re-attempted at least `threshold` times, in the original
        casing first seen, sorted for deterministic output. Suitable for
        `PlannerInvocationInput.exhausted_steps`."""
        return sorted(
            self._display[key] for key, count in self._attempts.items() if count >= threshold
        )


__all__ = ["ReplanLedger"]
