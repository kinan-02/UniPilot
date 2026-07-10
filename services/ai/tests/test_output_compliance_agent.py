"""Unit tests for Output Compliance Agent (AGT-9c)."""

from __future__ import annotations

from app.services.advisor_agent import AdvisorResponse
from app.services.output_compliance_agent import (
    OutputScopeVerdict,
    compact_blocks_for_verifier,
    run_output_compliance_guard,
)


def test_compact_blocks_for_verifier_truncates_context():
    blocks = [
        {
            "source": "profile_agent",
            "intent": "course_fit",
            "course_id": "00440148",
            "context": "x" * 1200,
            "facts": {"eligible": False},
        }
    ]
    compact = compact_blocks_for_verifier(blocks)
    assert len(compact[0]["context"]) == 800
    assert compact[0]["courseId"] == "00440148"


def test_run_output_compliance_guard_skips_without_blocks():
    response = AdvisorResponse(answer="Hello", confidence="high")
    result = run_output_compliance_guard(
        question="test",
        response=response,
        retrieval_blocks=[],
    )
    assert result.status == "skipped"
    assert result.method == "skipped"


def test_run_output_compliance_guard_passes_clean_verdict():
    class _FakeStructured:
        def invoke(self, _messages):
            return OutputScopeVerdict(
                status="passed",
                unsupported_claims=[],
                reasoning="All claims grounded.",
                confidence="high",
            )

    class _FakeLlm:
        def with_structured_output(self, _schema):
            return _FakeStructured()

        def bind(self, **_kwargs):
            return self

    response = AdvisorResponse(
        answer="You are not eligible for 00440148; missing 00440105.",
        confidence="high",
    )
    blocks = [
        {
            "source": "profile_agent",
            "intent": "course_fit",
            "course_id": "00440148",
            "context": "00440148: not eligible. Missing prerequisites: 00440105.",
            "facts": {
                "course_id": "00440148",
                "eligible": False,
                "missing_prerequisites": ["00440105"],
            },
        }
    ]
    result = run_output_compliance_guard(
        question="Am I eligible?",
        response=response,
        retrieval_blocks=blocks,
        llm_factory=lambda: _FakeLlm(),
    )
    assert result.status == "passed"
    assert result.unsupported_claims == []


def test_run_output_compliance_guard_remediates_unsupported_claims():
    class _FakeStructured:
        def invoke(self, _messages):
            return OutputScopeVerdict(
                status="failed",
                unsupported_claims=["You will graduate next semester"],
                reasoning="Graduation timeline not in blocks.",
                confidence="high",
            )

    class _FakeLlm:
        def with_structured_output(self, _schema):
            return _FakeStructured()

        def bind(self, **_kwargs):
            return self

    response = AdvisorResponse(
        answer="You will graduate next semester.",
        confidence="high",
    )
    blocks = [
        {
            "source": "planning_agent",
            "intent": "graduation_progress",
            "context": "42% complete.",
            "facts": {"completionPercentage": 42},
        }
    ]
    result = run_output_compliance_guard(
        question="When do I graduate?",
        response=response,
        retrieval_blocks=blocks,
        llm_factory=lambda: _FakeLlm(),
    )
    assert result.status == "failed"
    assert result.response is not None
    assert result.response.confidence == "medium"
    assert "Semantic compliance note" in result.response.answer
    assert any(item.startswith("downgraded_confidence") for item in result.remediations)
