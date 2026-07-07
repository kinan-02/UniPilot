"""Unit tests for offline eval static safety scan (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.safety import assert_eval_replay_safe, scan_eval_replay_forbidden_patterns


def test_eval_replay_has_no_forbidden_patterns() -> None:
    assert scan_eval_replay_forbidden_patterns() == []


def test_assert_eval_replay_safe() -> None:
    assert_eval_replay_safe()
