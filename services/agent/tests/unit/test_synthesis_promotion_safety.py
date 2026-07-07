"""Static safety tests for synthesis promotion modules (Phase 22)."""

from __future__ import annotations

from app.agent.synthesis.promotion_safety import (
    assert_synthesis_promotion_safe,
    scan_synthesis_promotion_forbidden_patterns,
)


def test_synthesis_promotion_has_no_forbidden_patterns() -> None:
    assert scan_synthesis_promotion_forbidden_patterns() == []


def test_assert_synthesis_promotion_safe() -> None:
    assert_synthesis_promotion_safe()
