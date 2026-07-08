"""Unit tests for `app.agent.specialists.candidate_response.build_specialist_candidate_response` (Layer 3)."""

from __future__ import annotations

from app.agent.specialists.candidate_response import build_specialist_candidate_response
from app.agent.specialists.schemas import SpecialistAgentOutput
from app.config import Settings

_SETTINGS = Settings()

_NORMAL_TEXT = (
    "You still need 40 more credits to graduate. Focus on completing your remaining "
    "core courses in the data engineering track next semester."
)


def _output(**overrides) -> SpecialistAgentOutput:
    defaults = dict(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="check_progress",
        decision_summary="You still need 40 credits.",
        confidence=0.9,
        result={"answer_text": _NORMAL_TEXT},
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


# ---------------------------------------------------------------------------
# 1. Happy path.
# ---------------------------------------------------------------------------


def test_builds_text_only_candidate_when_every_gate_passes() -> None:
    candidate = build_specialist_candidate_response(
        _output(), conversation_id="c1", run_id="r1", settings=_SETTINGS
    )

    assert candidate is not None
    assert candidate.text == _NORMAL_TEXT
    assert candidate.conversation_id == "c1"
    assert candidate.run_id == "r1"
    assert candidate.blocks == []
    assert candidate.used_sources == []
    assert candidate.warnings == []
    assert candidate.proposed_actions == []


# ---------------------------------------------------------------------------
# 2. Each gate independently blocks.
# ---------------------------------------------------------------------------


def test_blocks_when_status_not_completed() -> None:
    output = _output(status="needs_more_context")
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_confidence_below_floor() -> None:
    output = _output(confidence=0.5)
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_missing_context_present() -> None:
    output = _output(missing_context=["degree program"])
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_answer_text_absent() -> None:
    output = _output(result={})
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_answer_text_empty_string() -> None:
    output = _output(result={"answer_text": "   "})
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_answer_text_unsafe() -> None:
    output = _output(result={"answer_text": "Your plan has been saved to your account."})
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


def test_blocks_when_answer_text_too_long() -> None:
    output = _output(result={"answer_text": "x" * 5000})
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None


# ---------------------------------------------------------------------------
# 3. `sources`/`warnings` are never passed through, regardless of content.
# ---------------------------------------------------------------------------


def test_never_passes_through_sources_or_warnings() -> None:
    output = _output(
        sources=[{"type": "graduation_audit", "id": "abc"}],
        warnings=["some specialist warning"],
    )

    candidate = build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS)

    assert candidate is not None
    assert candidate.used_sources == []
    assert candidate.warnings == []


def test_never_raises_when_result_has_no_answer_text_key_at_all() -> None:
    output = _output(result={"some_other_field": "value"})
    assert build_specialist_candidate_response(output, conversation_id="c1", run_id="r1", settings=_SETTINGS) is None
