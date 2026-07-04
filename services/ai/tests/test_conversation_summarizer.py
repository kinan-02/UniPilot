"""Tests for conversation summarizer fallback (no OpenAI)."""

from __future__ import annotations

from app.services.conversation_summarizer import (
    ConversationSummaryResult,
    _fallback_summary,
    summarize_conversation_exchange,
)


def test_fallback_summary_new_conversation():
    result = _fallback_summary(None, "מה הסילבוס של 00440148?", "הסילבוס כולל מבוא.")
    assert isinstance(result, ConversationSummaryResult)
    assert "00440148" in result.title or "סילבוס" in result.title
    assert "Student:" in result.summary
    assert "Advisor:" in result.summary


def test_fallback_summary_appends_previous():
    result = _fallback_summary(
        "Earlier: asked about prerequisites.",
        "Am I eligible?",
        "Yes, you are eligible.",
    )
    assert "Earlier" in result.summary
    assert "Latest" in result.summary


def test_summarize_without_api_key_uses_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = summarize_conversation_exchange(
        previous_summary=None,
        user_message="What are student rights?",
        advisor_answer="Contact the ombudsman.",
    )
    assert result.summary
    assert result.title
