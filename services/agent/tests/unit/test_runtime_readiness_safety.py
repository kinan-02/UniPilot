"""Unit tests for runtime readiness static safety scan (Phase 25)."""

from __future__ import annotations

from app.agent.readiness.safety import assert_runtime_readiness_safe, scan_runtime_readiness_forbidden_patterns


def test_runtime_readiness_has_no_forbidden_patterns() -> None:
    assert scan_runtime_readiness_forbidden_patterns() == []


def test_assert_runtime_readiness_safe() -> None:
    assert_runtime_readiness_safe()
