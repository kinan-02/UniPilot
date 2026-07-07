"""Static safety tests for synthesis package (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.safety import assert_synthesis_package_safe, scan_synthesis_package_forbidden_patterns


def test_synthesis_package_has_no_forbidden_patterns() -> None:
    violations = scan_synthesis_package_forbidden_patterns()
    assert violations == []


def test_assert_synthesis_package_safe() -> None:
    assert_synthesis_package_safe()
