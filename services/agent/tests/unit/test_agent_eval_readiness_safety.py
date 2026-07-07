"""Unit tests for readiness static safety scan (Phase 24)."""

from __future__ import annotations

from app.agent.evaluation.readiness_safety import assert_readiness_eval_safe, scan_readiness_forbidden_patterns


def test_readiness_eval_has_no_forbidden_patterns() -> None:
    assert scan_readiness_forbidden_patterns() == []


def test_assert_readiness_eval_safe() -> None:
    assert_readiness_eval_safe()
