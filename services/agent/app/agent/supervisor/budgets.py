"""Execution budget tracking for the Supervisor Orchestrator Runtime (Phase 6).

Purely deterministic bookkeeping — no I/O, no LLM calls. `BudgetTracker` is
mutable, per-run state; a fresh instance is created for every
`run_supervisor_shadow` call.
"""

from __future__ import annotations

import time

from app.agent.supervisor.schemas import ExecutionBudget


class BudgetTracker:
    """Tracks consumption against an `ExecutionBudget` for one supervisor run."""

    def __init__(self, budget: ExecutionBudget) -> None:
        self.budget = budget
        self._started_at = time.monotonic()
        self.subtasks_started: int = 0
        self.total_retries: int = 0
        self.retries_per_subtask: dict[str, int] = {}
        self.context_previews_compiled: int = 0

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    def runtime_exceeded(self) -> bool:
        return self.elapsed_ms() >= self.budget.max_runtime_ms

    def subtasks_exceeded(self) -> bool:
        return self.subtasks_started >= self.budget.max_subtasks

    def record_subtask_started(self) -> None:
        self.subtasks_started += 1

    def per_subtask_retry_available(self, subtask_id: str) -> bool:
        return self.retries_per_subtask.get(subtask_id, 0) < self.budget.max_retries_per_subtask

    def total_retry_available(self) -> bool:
        return self.total_retries < self.budget.max_total_retries

    def can_retry(self, subtask_id: str) -> bool:
        return self.per_subtask_retry_available(subtask_id) and self.total_retry_available()

    def record_retry(self, subtask_id: str) -> None:
        self.retries_per_subtask[subtask_id] = self.retries_per_subtask.get(subtask_id, 0) + 1
        self.total_retries += 1

    def can_compile_context_preview(self) -> bool:
        return self.context_previews_compiled < self.budget.max_context_previews

    def record_context_preview(self) -> None:
        self.context_previews_compiled += 1

    def to_summary(self) -> dict[str, int]:
        return {
            "elapsedMs": self.elapsed_ms(),
            "subtasksStarted": self.subtasks_started,
            "totalRetries": self.total_retries,
            "contextPreviewsCompiled": self.context_previews_compiled,
        }
