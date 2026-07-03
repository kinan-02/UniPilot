"""Unit tests for LLM JSON parsing."""

from app.agent.llm_json import parse_llm_json_content


def test_parse_plain_json():
    assert parse_llm_json_content('{"intent": "course_question", "confidence": 0.9}') == {
        "intent": "course_question",
        "confidence": 0.9,
    }


def test_parse_fenced_json():
    raw = '```json\n{"sufficient": true, "gaps": []}\n```'
    assert parse_llm_json_content(raw) == {"sufficient": True, "gaps": []}


def test_parse_invalid_returns_none():
    assert parse_llm_json_content("not json") is None
    assert parse_llm_json_content("") is None
