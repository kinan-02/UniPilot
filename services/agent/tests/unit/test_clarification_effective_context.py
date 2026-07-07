"""Unit tests for effective clarification context (Phase 19)."""

from __future__ import annotations

from app.agent.clarification.resume import build_effective_clarification_context


def test_builds_compact_context_from_confirmed_answers() -> None:
    context = build_effective_clarification_context(
        original_user_message="Help me plan next semester",
        confirmed_answers=[{"value": "prioritize mandatory requirements", "provenance": "confirmed"}],
    )
    assert context["originalUserMessage"] == "Help me plan next semester"
    assert context["confirmedClarifications"][0]["value"] == "prioritize mandatory requirements"


def test_provenance_confirmed_preserved() -> None:
    context = build_effective_clarification_context(
        original_user_message="Plan courses",
        confirmed_answers=[{"value": "evening classes", "provenance": "confirmed"}],
    )
    assert context["confirmedClarifications"][0]["provenance"] == "confirmed"


def test_assumptions_created_included_compactly() -> None:
    context = build_effective_clarification_context(
        original_user_message="Plan courses",
        confirmed_answers=[{"value": "evening classes", "provenance": "confirmed"}],
        assumptions_created=[{"kind": "user_preference", "provenance": "confirmed", "confidence": 1.0}],
    )
    assert context["assumptionsCreated"][0]["kind"] == "user_preference"


def test_original_user_message_included() -> None:
    context = build_effective_clarification_context(
        original_user_message="What should I take next semester?",
        confirmed_answers=[{"value": "CS courses", "provenance": "confirmed"}],
    )
    assert "next semester" in context["originalUserMessage"]


def test_persisted_user_message_not_mutated() -> None:
    original = "What should I take next semester?"
    build_effective_clarification_context(
        original_user_message=original,
        confirmed_answers=[{"value": "CS courses", "provenance": "confirmed"}],
    )
    assert original == "What should I take next semester?"


def test_raw_context_omitted() -> None:
    context = build_effective_clarification_context(
        original_user_message="Plan courses",
        confirmed_answers=[{"value": "evening classes", "compiled_context": {"hidden": True}}],
    )
    assert "compiled_context" not in str(context)


def test_malformed_answers_never_raise() -> None:
    context = build_effective_clarification_context(
        original_user_message="Plan courses",
        confirmed_answers=[None, "bad", {"value": ""}],  # type: ignore[list-item]
    )
    assert context["confirmedClarifications"] == []
