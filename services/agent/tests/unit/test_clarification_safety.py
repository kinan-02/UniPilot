"""Unit tests for clarification safety (Phase 17)."""

from __future__ import annotations

from pathlib import Path

from app.agent.clarification.safety import scan_clarification_package_for_forbidden_tokens, validate_question_safety
from app.agent.clarification.schemas import ClarificationQuestion


def test_static_scan_finds_no_forbidden_tokens() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "clarification"
    assert scan_clarification_package_for_forbidden_tokens(package_root=root) == []


def test_runtime_question_safety_rejects_exposed_ids() -> None:
    question = ClarificationQuestion(
        id="q-exposed",
        need_id="need-exposed",
        prompt="Please clarify need-exposed for q-exposed",
        consequence="high",
        ambiguity_type="preference",
    )
    issues = validate_question_safety(question)
    assert issues
