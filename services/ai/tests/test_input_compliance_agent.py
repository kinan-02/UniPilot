"""Unit tests for Input Compliance Agent (AGT-9b)."""

from __future__ import annotations

from app.services.input_compliance_agent import (
    InputScopeVerdict,
    run_input_compliance_guard,
)


def test_run_input_compliance_guard_blocks_homework_request():
    result = run_input_compliance_guard("Please solve my homework assignment for calculus.")
    assert result.blocked is True
    assert result.status == "blocked"
    assert result.category == "homework_help"
    assert result.method == "rules"
    assert result.refusal_message
    assert "homework" in result.refusal_message.lower() or "מטלות" in result.refusal_message


def test_run_input_compliance_guard_blocks_code_generation():
    result = run_input_compliance_guard("Write a Python script to sort a linked list.")
    assert result.blocked is True
    assert result.category == "code_generation"


def test_run_input_compliance_guard_blocks_hebrew_homework():
    result = run_input_compliance_guard("תפתור לי את שיעורי הבית במתמטיקה")
    assert result.blocked is True
    assert result.category == "homework_help"


def test_run_input_compliance_guard_passes_eligibility_question():
    result = run_input_compliance_guard("Am I eligible for course 00440148 based on my transcript?")
    assert result.blocked is False
    assert result.status == "passed"
    assert result.category == "academic_advising"


def test_run_input_compliance_guard_uses_llm_when_available():
    class _FakeStructured:
        def invoke(self, _messages):
            return InputScopeVerdict(
                status="out_of_scope",
                category="general_chat",
                reason="Weather question.",
                confidence="high",
            )

    class _FakeLlm:
        def with_structured_output(self, _schema):
            return _FakeStructured()

        def bind(self, **_kwargs):
            return self

    result = run_input_compliance_guard(
        "What is the weather in Haifa?",
        llm_factory=lambda: _FakeLlm(),
    )
    assert result.blocked is True
    assert result.method == "llm"
    assert result.category == "general_chat"
