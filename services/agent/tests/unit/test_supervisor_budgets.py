"""Unit tests for the Phase 6 `BudgetTracker`."""

from __future__ import annotations

from app.agent.supervisor.budgets import BudgetTracker
from app.agent.supervisor.schemas import ExecutionBudget


def test_subtasks_exceeded_after_max_reached() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_subtasks=2))
    assert not tracker.subtasks_exceeded()
    tracker.record_subtask_started()
    assert not tracker.subtasks_exceeded()
    tracker.record_subtask_started()
    assert tracker.subtasks_exceeded()


def test_runtime_exceeded_with_zero_budget() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_runtime_ms=0))
    assert tracker.runtime_exceeded()


def test_runtime_not_exceeded_with_generous_budget() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_runtime_ms=60_000))
    assert not tracker.runtime_exceeded()


def test_per_subtask_retry_budget() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_retries_per_subtask=1, max_total_retries=10))
    assert tracker.per_subtask_retry_available("a")
    tracker.record_retry("a")
    assert not tracker.per_subtask_retry_available("a")
    # A different subtask has its own independent per-subtask budget.
    assert tracker.per_subtask_retry_available("b")


def test_total_retry_budget_shared_across_subtasks() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_retries_per_subtask=10, max_total_retries=1))
    assert tracker.total_retry_available()
    tracker.record_retry("a")
    assert not tracker.total_retry_available()
    # Even though "b" has its own per-subtask room, the shared total is spent.
    assert tracker.per_subtask_retry_available("b")
    assert not tracker.can_retry("b")


def test_can_retry_requires_both_budgets() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_retries_per_subtask=1, max_total_retries=1))
    assert tracker.can_retry("a")
    tracker.record_retry("a")
    assert not tracker.can_retry("a")


def test_context_preview_budget() -> None:
    tracker = BudgetTracker(ExecutionBudget(max_context_previews=1))
    assert tracker.can_compile_context_preview()
    tracker.record_context_preview()
    assert not tracker.can_compile_context_preview()


def test_to_summary_shape() -> None:
    tracker = BudgetTracker(ExecutionBudget())
    summary = tracker.to_summary()
    assert set(summary) == {"elapsedMs", "subtasksStarted", "totalRetries", "contextPreviewsCompiled"}
    assert summary["subtasksStarted"] == 0


def test_defaults_match_spec() -> None:
    budget = ExecutionBudget()
    assert budget.max_subtasks == 20
    assert budget.max_retries_per_subtask == 1
    assert budget.max_total_retries == 5
    assert budget.max_runtime_ms == 30000
    assert budget.max_context_previews == 20
