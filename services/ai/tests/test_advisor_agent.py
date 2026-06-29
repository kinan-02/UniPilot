"""Tests for agentic retrieval loop helpers (no OpenAI calls)."""

from __future__ import annotations

from advisor_agent import (
    RetrievalAgentResult,
    UserContext,
    _dedupe_blocks,
    _default_fallback,
    _merge_user_profile,
    _normalize_advisor_response,
    _structured_output_method,
    synthesize_answer,
)
from graph_tools import _block_is_empty


def test_dedupe_blocks():
    existing = [
        {
            "intent": "syllabus",
            "course_id": "00440148",
            "wiki_slug": None,
            "search_query": None,
            "context": "a",
        }
    ]
    new = [
        {
            "intent": "syllabus",
            "course_id": "00440148",
            "wiki_slug": None,
            "search_query": None,
            "context": "b",
        },
        {
            "intent": "schedule",
            "course_id": "00440148",
            "wiki_slug": None,
            "search_query": None,
            "context": "c",
        },
    ]
    unique = _dedupe_blocks(existing, new)
    assert len(unique) == 1
    assert unique[0]["intent"] == "schedule"


def test_block_is_empty_markers():
    assert _block_is_empty("00440148 foo: no schedule data.")
    assert not _block_is_empty("00440148 schedule: Monday 10:00")


def test_default_fallback_hebrew():
    msg = _default_fallback("מה זכויות הסטודנט?")
    assert "לא מצאתי" in msg


def test_merge_user_profile():
    profile = _merge_user_profile(
        UserContext(
            track_slug="track-electrical-engineering",
            completed_courses=["00440105"],
            display_name="Test",
        )
    )
    assert profile["track_slug"] == "track-electrical-engineering"
    assert profile["completed_count"] == 1


def test_synthesize_fallback_without_llm():
    response = synthesize_answer(
        "מה הסילבוס?",
        [],
        UserContext(),
        retrieval_status="not_found",
        fallback_message="missing info",
        contacts=["ombudsman"],
    )
    assert response.answer == "missing info"
    assert response.confidence == "low"
    assert response.contacts == ["ombudsman"]


def test_retrieval_agent_result_model():
    result = RetrievalAgentResult(status="ok", blocks=[{"intent": "syllabus"}])
    assert result.status == "ok"
    assert len(result.blocks) == 1


def test_structured_output_method_openai_default(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert _structured_output_method() == "json_schema"


def test_structured_output_method_custom_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    assert _structured_output_method() == "json_mode"


def test_normalize_eligibility_only_json():
    response = _normalize_advisor_response(
        {
            "eligible": True,
            "missing_prerequisites": [],
            "course_id": "00440148",
        },
        "האם אני זכאי?",
        [],
    )
    assert "זכאי" in response.answer
    assert response.eligibility["eligible"] is True


def test_normalize_answer_json():
    response = _normalize_advisor_response(
        {"answer": "hello", "confidence": "high"},
        "test",
        [],
    )
    assert response.answer == "hello"
    assert response.confidence == "high"
