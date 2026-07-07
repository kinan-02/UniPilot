"""Tests for structured result normalization."""

from __future__ import annotations

from app.agent.reasoning.result_normalizer import normalize_structured_result
from app.agent.reasoning.schema_validator import validate_against_schema
from app.agent.reasoning.task_schemas import PLANNER_OUTPUT_SCHEMA, TASK_UNDERSTANDING_OUTPUT_SCHEMA


def test_task_understanding_normalizer_fills_optional_arrays_and_enums() -> None:
    raw = {
        "status": "complete",
        "user_goal": "Plan next semester",
        "normalized_request": "Plan next semester",
        "primary_intent": "semester_plan_generation",
        "task_category": "Planning",
        "task_complexity": "moderate",
        "recommended_autonomy_level": 2,
        "suggested_next_layer": "clarification",
        "intent_confidence": 0.8,
        "overall_confidence": 0.7,
        "decision_summary": "Needs preferences",
        "extra_field": "drop_me",
    }
    normalized = normalize_structured_result(
        raw,
        output_schema_name="task_understanding_output_v1",
        output_schema=TASK_UNDERSTANDING_OUTPUT_SCHEMA,
    )
    assert normalized is not None
    assert normalized["status"] == "completed"
    assert normalized["task_category"] == "planning"
    assert normalized["task_complexity"] == "medium"
    assert normalized["secondary_intents"] == []
    assert "extra_field" not in normalized
    validation = validate_against_schema(normalized, TASK_UNDERSTANDING_OUTPUT_SCHEMA)
    assert validation.valid, validation.errors


def test_planner_normalizer_fills_required_defaults() -> None:
    raw = {
        "status": "completed",
        "plan_id": "plan-1",
        "user_goal": "Plan semester",
        "execution_mode": "clarification",
        "recommended_autonomy_level": 2,
        "primary_intent": "semester_plan_generation",
        "decision_summary": "Need clarification",
        "confidence": 0.6,
        "subtasks": [],
        "unknown_key": True,
    }
    normalized = normalize_structured_result(
        raw,
        output_schema_name="planner_output_v1",
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )
    assert normalized is not None
    assert normalized["missing_context"] == []
    assert "unknown_key" not in normalized
    validation = validate_against_schema(normalized, PLANNER_OUTPUT_SCHEMA)
    assert validation.valid, validation.errors


# ---------------------------------------------------------------------------
# Generic, schema-driven fallback (any output_schema_name without a bespoke
# normalizer)
# ---------------------------------------------------------------------------

_GENERIC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_review"]},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["status", "summary"],
    "additionalProperties": False,
}


def test_generic_normalizer_fuzzy_matches_enum_casing_and_hyphenation() -> None:
    raw = {
        "status": "Needs-Review",
        "priority": "  HIGH  ",
        "tags": [],
        "summary": "looks fine",
    }
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert normalized["status"] == "needs_review"
    assert normalized["priority"] == "high"
    validation = validate_against_schema(normalized, _GENERIC_SCHEMA)
    assert validation.valid, validation.errors


def test_generic_normalizer_coerces_scalar_into_array_field() -> None:
    raw = {"status": "ok", "summary": "fine", "tags": "single-tag"}
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert normalized["tags"] == ["single-tag"]


def test_generic_normalizer_coerces_stringified_number() -> None:
    raw = {"status": "ok", "summary": "fine", "score": "0.75"}
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert normalized["score"] == 0.75


def test_generic_normalizer_fills_blank_required_string() -> None:
    raw = {"status": "ok", "summary": "   "}
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert normalized["summary"] == "unknown"


def test_generic_normalizer_strips_unknown_keys_when_schema_forbids_them() -> None:
    raw = {"status": "ok", "summary": "fine", "extra": "drop me"}
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert "extra" not in normalized


def test_generic_normalizer_leaves_unmatched_enum_value_untouched() -> None:
    """An enum value with no fuzzy match at all is left alone for schema
    validation (and, upstream, the LLM repair loop) to catch — never guessed."""
    raw = {"status": "completely_unrelated_value", "summary": "fine"}
    normalized = normalize_structured_result(
        raw, output_schema_name="some_new_contract_v1", output_schema=_GENERIC_SCHEMA
    )
    assert normalized["status"] == "completely_unrelated_value"
    validation = validate_against_schema(normalized, _GENERIC_SCHEMA)
    assert not validation.valid
