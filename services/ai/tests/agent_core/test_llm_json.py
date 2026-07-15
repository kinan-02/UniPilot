"""Tests for `parse_llm_json_detailed` / `parse_llm_json_content`.

Regression coverage for the live-eval finding that a synthesis answer with
literal newlines inside its `answer_text` string (a normal multi-paragraph
markdown answer) was rejected as `json_parse_failed`, hard-failing the whole
turn -- because strict `json.loads` forbids raw control characters inside a
string. The model output was otherwise valid JSON; only the un-escaped newline
was illegal in strict mode.
"""

from __future__ import annotations

from app.agent_core.reasoning.llm_json import (
    parse_llm_json_content,
    parse_llm_json_detailed,
)


def test_parses_answer_text_with_literal_newlines() -> None:
    # Arrange -- a real-shaped synthesis payload with un-escaped newlines
    # inside the string value, exactly as the composition model emits for a
    # multi-paragraph markdown answer.
    content = (
        '{\n  "answer_text": "Here is the analysis.\n\n'
        "First, a crucial point: you have already passed 00440105.\n\n"
        '**Your Current Status:** eligible."\n}'
    )

    # Act
    outcome = parse_llm_json_detailed(content)

    # Assert
    assert outcome.failure_code is None
    assert outcome.payload is not None
    assert "answer_text" in outcome.payload
    assert "First, a crucial point" in outcome.payload["answer_text"]


def test_parses_string_with_literal_tab() -> None:
    content = '{"answer_text": "column1\tcolumn2"}'

    payload = parse_llm_json_content(content)

    assert payload is not None
    assert payload["answer_text"] == "column1\tcolumn2"


def test_still_rejects_genuinely_malformed_json() -> None:
    # strict=False must only relax control characters, not accept other
    # invalid JSON such as a trailing comma.
    content = '{"answer_text": "ok",}'

    outcome = parse_llm_json_detailed(content)

    assert outcome.payload is None
    assert outcome.failure_code == "json_parse_failed"
