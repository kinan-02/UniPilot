"""Tests for robust LLM JSON parsing."""

from __future__ import annotations

from app.agent.llm_json import parse_llm_json_content, parse_llm_json_detailed


def test_parse_plain_json() -> None:
    assert parse_llm_json_content('{"intent": "course_question", "confidence": 0.9}') == {
        "intent": "course_question",
        "confidence": 0.9,
    }


def test_parse_fenced_json() -> None:
    raw = '```json\n{"sufficient": true, "gaps": []}\n```'
    assert parse_llm_json_content(raw) == {"sufficient": True, "gaps": []}


def test_parse_json_with_prose_wrapper() -> None:
    raw = 'Here is the JSON response:\n```json\n{"status": "ok", "result": {"plan_id": "p1"}}\n```\nThanks.'
    payload = parse_llm_json_content(raw)
    assert payload is not None
    assert payload["status"] == "ok"


def test_parse_embedded_object_without_fences() -> None:
    raw = 'Sure. {"status": "completed", "plan_id": "abc", "confidence": 0.8}'
    payload = parse_llm_json_content(raw)
    assert payload == {"status": "completed", "plan_id": "abc", "confidence": 0.8}


def test_parse_invalid_returns_none() -> None:
    assert parse_llm_json_content("not json") is None
    assert parse_llm_json_content("") is None


def test_parse_detailed_reports_failure_code() -> None:
    outcome = parse_llm_json_detailed("not json at all")
    assert outcome.payload is None
    assert outcome.failure_code in {"json_extraction_failed", "json_parse_failed"}
