"""Unit tests for `app.agent.task_understanding.integration` (Layer 1 redesign).

Covers the contract that makes this call site safe to be load-bearing for
every turn: `run_task_understanding` never returns `None` and never raises,
and `to_intent_classification` bridges cleanly into `IntentClassification`.
"""

from __future__ import annotations

import pytest

from app.agent.schemas import IntentClassification
from app.agent.task_understanding import integration as integration_module
from app.agent.task_understanding.integration import (
    build_task_understanding_diagnostic_summary,
    run_task_understanding,
    to_intent_classification,
)
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings


def _make_output(**overrides) -> TaskUnderstandingOutput:
    defaults = dict(
        status="completed",
        user_goal="What am I missing to graduate?",
        normalized_request="What am I missing to graduate?",
        primary_intent="graduation_progress_check",
        secondary_intents=[],
        task_category="academic_analysis",
        task_complexity="medium",
        recommended_autonomy_level=2,
        suggested_next_layer="deterministic_workflow",
        required_context=["student_profile"],
        missing_context=[],
        extracted_entities={},
        assumptions=[],
        requires_user_confirmation=False,
        write_risk="none",
        clarifying_questions=[],
        intent_confidence=0.9,
        overall_confidence=0.85,
        decision_summary="test",
        warnings=[],
        source="llm_reasoning_block",
    )
    defaults.update(overrides)
    return TaskUnderstandingOutput(**defaults)


async def test_run_task_understanding_never_returns_none_when_flag_enabled(monkeypatch):
    async def _fake_understand_user_task(**_kwargs):
        return _make_output()

    monkeypatch.setattr(integration_module, "understand_user_task", _fake_understand_user_task)

    output = await run_task_understanding(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.8,
        deterministic_entities={},
        settings=Settings(**{"AGENT_TASK_UNDERSTANDING_ENABLED": True}),
    )

    assert output is not None
    assert isinstance(output, TaskUnderstandingOutput)


async def test_run_task_understanding_never_returns_none_when_flag_disabled(monkeypatch):
    # Flag disabled: `understand_user_task` itself resolves to its internal
    # deterministic fallback rather than the wrapper short-circuiting to `None`.
    output = await run_task_understanding(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.8,
        deterministic_entities={"courseNumber": "234218"},
        settings=Settings(**{"AGENT_TASK_UNDERSTANDING_ENABLED": False}),
    )

    assert output is not None
    assert isinstance(output, TaskUnderstandingOutput)
    assert output.source == "deterministic_fallback"
    assert output.primary_intent == "graduation_progress_check"
    assert output.extracted_entities == {"courseNumber": "234218"}


async def test_run_task_understanding_degrades_to_deterministic_fallback_on_unexpected_error(
    monkeypatch,
):
    async def _raising_understand_user_task(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(integration_module, "understand_user_task", _raising_understand_user_task)

    output = await run_task_understanding(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.75,
        deterministic_entities={"courseNumber": "234218"},
        settings=Settings(**{"AGENT_TASK_UNDERSTANDING_ENABLED": True}),
    )

    assert output.source == "deterministic_fallback"
    assert output.primary_intent == "graduation_progress_check"
    assert output.extracted_entities == {"courseNumber": "234218"}
    assert "task_understanding_integration_unexpected_error" in output.warnings


async def test_run_task_understanding_never_raises_even_on_unexpected_error(monkeypatch):
    async def _raising_understand_user_task(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(integration_module, "understand_user_task", _raising_understand_user_task)

    # Must not raise.
    output = await run_task_understanding(
        user_message="anything",
        deterministic_intent=None,
        deterministic_intent_confidence=None,
        deterministic_entities=None,
        settings=Settings(**{"AGENT_TASK_UNDERSTANDING_ENABLED": True}),
    )
    assert output.primary_intent == "unknown_or_unsupported"


def test_to_intent_classification_round_trips_supported_intent():
    output = _make_output(
        primary_intent="course_question",
        intent_confidence=0.92,
        requires_user_confirmation=True,
        required_context=["course_record"],
    )

    classification = to_intent_classification(output, requires_file=False)

    assert isinstance(classification, IntentClassification)
    assert classification.intent == "course_question"
    assert classification.confidence == pytest.approx(0.92)
    assert classification.requires_confirmation is True
    assert classification.required_context == ["course_record"]
    assert classification.requires_file is False


def test_to_intent_classification_carries_requires_file_through():
    output = _make_output(primary_intent="transcript_import")

    classification = to_intent_classification(output, requires_file=True)

    assert classification.requires_file is True


def test_to_intent_classification_handles_unsupported_intent_value_from_normalizer():
    # `reconcile_task_understanding_output` guarantees `primary_intent` is
    # always a valid `AgentIntent` (falls back to `unknown_or_unsupported`)
    # before this bridge ever runs — confirm the bridge doesn't reintroduce
    # a gap for that already-normalized value.
    output = _make_output(primary_intent="unknown_or_unsupported")

    classification = to_intent_classification(output)

    assert classification.intent == "unknown_or_unsupported"


def test_build_task_understanding_diagnostic_summary_is_storage_safe():
    output = _make_output(
        missing_context=[f"item-{i}" for i in range(20)],
        warnings=[f"warning-{i}" for i in range(20)],
    )

    summary = build_task_understanding_diagnostic_summary(output)

    assert len(summary["missingContext"]) <= 8
    assert len(summary["warnings"]) <= 8
    assert "user_goal" not in summary
    assert "normalized_request" not in summary
