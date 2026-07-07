"""Deterministic controller for the Supervisor Orchestrator Runtime (Phase 6).

Decides what the runtime should do next after one subtask attempt, given
its result and the run's budget. Purely deterministic — no LLM calls, no
I/O. A future optional `supervisor_controller_v1` LLM contract could
eventually replace/augment this, but Phase 6 stays fully deterministic:
any such contract must go through `ReasoningBlock`, default to disabled,
and not be wired into runtime behavior until a dedicated later phase
decides to turn it on.
"""

from __future__ import annotations

from typing import Literal

from app.agent.supervisor.budgets import BudgetTracker
from app.agent.supervisor.schemas import SubtaskResult

ControllerDecision = Literal["continue", "retry", "skip_dependents", "fail_run"]


def decide_next_action(
    result: SubtaskResult,
    *,
    subtask_id: str,
    budget: BudgetTracker,
    total_subtasks: int,
) -> ControllerDecision:
    """Decide the runtime's next move after one subtask attempt.

    - `completed`/`skipped` -> `continue` (nothing more to do for this subtask).
    - `failed` and retries remain (per-subtask *and* global budget) -> `retry`.
    - `failed`, no retries left, and this was the plan's only subtask -> `fail_run`
      (a single-subtask plan failing means the whole run failed).
    - `failed`, no retries left, otherwise -> `skip_dependents` (independent
      branches of the graph may still complete).
    """
    if result.status in ("completed", "skipped"):
        return "continue"

    if budget.can_retry(subtask_id):
        return "retry"

    if total_subtasks <= 1:
        return "fail_run"

    return "skip_dependents"
