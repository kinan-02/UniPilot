"""Unit tests for `orchestrator/replan_ledger.py` (Phase 0 scaffolding).

`ReplanLedger` generalizes `UnresolvableEntityRegistry` from entities to
step/region objectives: it counts how many times the Monitor has flagged the
same step objective for replan, so the loop can stop re-attempting a dead
region (W3a). Turn-scoped, plain mutable collaborator -- never serialized.
"""

from __future__ import annotations

from app.agent_core.orchestrator.replan_ledger import ReplanLedger


def test_records_and_counts_attempts_normalizing_case_and_whitespace() -> None:
    ledger = ReplanLedger()
    ledger.record("Resolve the course Algorithms", "not found")
    ledger.record("  resolve the course algorithms ", "still not found")
    assert ledger.attempts("resolve the course ALGORITHMS") == 2


def test_distinct_objectives_counted_separately() -> None:
    ledger = ReplanLedger()
    ledger.record("resolve algorithms", "r1")
    ledger.record("compute gpa", "r2")
    assert ledger.attempts("resolve algorithms") == 1
    assert ledger.attempts("compute gpa") == 1


def test_unrecorded_objective_has_zero_attempts() -> None:
    ledger = ReplanLedger()
    assert ledger.attempts("never seen") == 0


def test_exhausted_returns_objectives_at_or_over_threshold() -> None:
    ledger = ReplanLedger()
    ledger.record("A objective", "r1")
    assert ledger.exhausted(threshold=2) == []
    ledger.record("a objective", "r2")
    assert ledger.exhausted(threshold=2) == ["A objective"]  # first-seen casing preserved for display


def test_exhausted_default_threshold_is_two() -> None:
    ledger = ReplanLedger()
    ledger.record("x objective", "r")
    ledger.record("x objective", "r")
    assert ledger.exhausted() == ["x objective"]


def test_exhausted_is_sorted_for_deterministic_output() -> None:
    ledger = ReplanLedger()
    for obj in ("zeta task", "alpha task"):
        ledger.record(obj, "r")
        ledger.record(obj, "r")
    assert ledger.exhausted() == ["alpha task", "zeta task"]
