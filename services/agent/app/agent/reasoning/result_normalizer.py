"""Normalize structured ReasoningBlock `result` payloads before schema validation."""

from __future__ import annotations

import copy
from typing import Any

_TASK_CATEGORY_ALIASES = {
    "simple question": "simple_question",
    "academic analysis": "academic_analysis",
    "planning": "planning",
    "transcript processing": "transcript_processing",
    "requirement explanation": "requirement_explanation",
    "write or update request": "write_or_update_request",
    "multi step task": "multi_step_task",
    "unsupported": "unsupported",
}

_TASK_COMPLEXITY_ALIASES = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "simple": "low",
    "moderate": "medium",
    "complex": "high",
}

_NEXT_LAYER_ALIASES = {
    "deterministic workflow": "deterministic_workflow",
    "planner": "planner",
    "clarification": "clarification",
    "unsupported": "unsupported",
}

_STATUS_ALIASES = {
    "complete": "completed",
    "completed": "completed",
    "needs_more_context": "needs_more_context",
    "failed": "failed",
    "unsupported": "unsupported",
}

_WRITE_RISK_ALIASES = {
    "none": "none",
    "possible": "possible",
    "explicit": "explicit",
    "low": "none",
    "high": "explicit",
}


def _strip_unknown_keys(value: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("additionalProperties") is not False:
        return value
    allowed = set((schema.get("properties") or {}).keys())
    return {key: item for key, item in value.items() if key in allowed}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _as_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_enum(value: Any, aliases: dict[str, str], default: str) -> str:
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    lowered = raw.lower().replace("-", "_")
    if lowered in aliases:
        return aliases[lowered]
    if raw in aliases.values():
        return raw
    return default


def _normalize_task_understanding_result(result: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(result)
    normalized["status"] = _normalize_enum(normalized.get("status"), _STATUS_ALIASES, "completed")
    normalized["task_category"] = _normalize_enum(
        normalized.get("task_category"),
        _TASK_CATEGORY_ALIASES,
        "unsupported",
    )
    normalized["task_complexity"] = _normalize_enum(
        normalized.get("task_complexity"),
        _TASK_COMPLEXITY_ALIASES,
        "medium",
    )
    normalized["suggested_next_layer"] = _normalize_enum(
        normalized.get("suggested_next_layer"),
        _NEXT_LAYER_ALIASES,
        "deterministic_workflow",
    )
    normalized["write_risk"] = _normalize_enum(normalized.get("write_risk"), _WRITE_RISK_ALIASES, "none")

    for key in (
        "secondary_intents",
        "required_context",
        "missing_context",
        "assumptions",
        "clarifying_questions",
        "warnings",
    ):
        normalized[key] = _as_string_list(normalized.get(key))

    normalized["extracted_entities"] = _as_object(normalized.get("extracted_entities"))
    normalized["requires_user_confirmation"] = bool(normalized.get("requires_user_confirmation", False))

    for key in ("user_goal", "normalized_request", "primary_intent", "decision_summary"):
        if not str(normalized.get(key) or "").strip():
            normalized[key] = str(normalized.get("user_goal") or normalized.get("normalized_request") or "unknown")

    for key in ("intent_confidence", "overall_confidence"):
        try:
            normalized[key] = float(normalized.get(key, 0.5))
        except (TypeError, ValueError):
            normalized[key] = 0.5
        normalized[key] = max(0.0, min(1.0, float(normalized[key])))

    try:
        autonomy = int(normalized.get("recommended_autonomy_level", 2))
    except (TypeError, ValueError):
        autonomy = 2
    normalized["recommended_autonomy_level"] = autonomy if autonomy in {0, 1, 2, 3, 4, 5} else 2

    return _strip_unknown_keys(normalized, schema)


def _normalize_planner_subtask(item: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(item)
    for key in ("depends_on", "required_context_sections", "success_criteria", "validation_requirements"):
        normalized[key] = _as_string_list(normalized.get(key))
    normalized["requires_user_confirmation"] = bool(normalized.get("requires_user_confirmation", False))
    risk = str(normalized.get("risk_level") or "medium").lower()
    normalized["risk_level"] = risk if risk in {"low", "medium", "high"} else "medium"
    kind = str(normalized.get("kind") or "analyze").lower()
    allowed_kinds = {
        "understand",
        "retrieve_context",
        "analyze",
        "simulate",
        "validate",
        "compose",
        "propose_action",
        "clarify",
    }
    normalized["kind"] = kind if kind in allowed_kinds else "analyze"
    return normalized


def _normalize_planner_result(result: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(result)
    normalized["status"] = _normalize_enum(normalized.get("status"), _STATUS_ALIASES, "completed")
    normalized["write_risk"] = _normalize_enum(normalized.get("write_risk"), _WRITE_RISK_ALIASES, "none")

    execution_mode = str(normalized.get("execution_mode") or "deterministic_workflow").lower()
    allowed_modes = {
        "deterministic_workflow",
        "single_capability",
        "multi_capability_graph",
        "clarification",
        "unsupported",
    }
    normalized["execution_mode"] = execution_mode if execution_mode in allowed_modes else "deterministic_workflow"

    for key in (
        "required_context",
        "missing_context",
        "assumptions",
        "clarification_questions",
        "validation_strategy",
        "warnings",
    ):
        normalized[key] = _as_string_list(normalized.get(key))

    subtasks: list[dict[str, Any]] = []
    for item in normalized.get("subtasks") or []:
        if isinstance(item, dict):
            subtasks.append(_normalize_planner_subtask(item))
    normalized["subtasks"] = subtasks

    if not str(normalized.get("plan_id") or "").strip():
        normalized["plan_id"] = "plan-normalized"
    if not str(normalized.get("user_goal") or "").strip():
        normalized["user_goal"] = str(normalized.get("decision_summary") or "unknown")
    if not str(normalized.get("primary_intent") or "").strip():
        normalized["primary_intent"] = "unknown_or_unsupported"
    if not str(normalized.get("decision_summary") or "").strip():
        normalized["decision_summary"] = "Planner output normalized."

    try:
        autonomy = int(normalized.get("recommended_autonomy_level", 2))
    except (TypeError, ValueError):
        autonomy = 2
    normalized["recommended_autonomy_level"] = autonomy if autonomy in {0, 1, 2, 3, 4, 5} else 2

    try:
        normalized["confidence"] = max(0.0, min(1.0, float(normalized.get("confidence", 0.5))))
    except (TypeError, ValueError):
        normalized["confidence"] = 0.5

    normalized["requires_user_confirmation"] = bool(normalized.get("requires_user_confirmation", False))
    fallback = normalized.get("fallback_workflow_name")
    normalized["fallback_workflow_name"] = str(fallback) if fallback is not None else None

    return _strip_unknown_keys(normalized, schema)


def _coerce_type(value: Any, prop_schema: dict[str, Any]) -> Any:
    """Coerce an obvious type mismatch against a single JSON-schema property.

    Deliberately narrow: only handles the mismatches models actually produce
    (a scalar where a list was expected, a stringified number/bool). Never
    invents a value — a coercion that isn't obviously safe is left as-is for
    `schema_validator`/the LLM repair loop to catch.
    """
    prop_type = prop_schema.get("type")
    if prop_type == "array" and not isinstance(value, list):
        return [] if value is None else [value]
    if prop_type == "string" and value is not None and not isinstance(value, str):
        return str(value)
    if prop_type == "integer" and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    if prop_type == "number" and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    if prop_type == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return value


def _fuzzy_match_enum(value: Any, enum_values: list[Any]) -> Any:
    """Match `value` against `enum_values` using the same normalization as
    `_normalize_enum` (case-insensitive, hyphen/space collapsed to underscore).

    Returns `value` unchanged if nothing matches, so an already-valid or
    genuinely-wrong value passes through for schema validation to catch —
    this only recovers cosmetic near-misses (`"Task Category"` vs
    `"task_category"`), never guesses between unrelated options.
    """
    if value is None:
        return value
    raw = str(value).strip()
    if not raw:
        return value
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    for candidate in enum_values:
        candidate_normalized = str(candidate).lower().replace("-", "_").replace(" ", "_")
        if normalized == candidate_normalized:
            return candidate
    return value


def _normalize_generic_result(result: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Schema-driven fallback normalizer for any `output_schema_name` without a
    bespoke `_normalize_*_result` function.

    Walks `schema["properties"]`: fuzzy-matches enum fields, coerces obvious
    type mismatches, and fills empty required string fields with a safe
    placeholder — then strips unknown keys exactly as the previous
    `additionalProperties is False` fallback did. Adding a new prompt
    contract with a new output schema no longer requires hand-writing a new
    normalizer function to get this baseline cleanup.
    """
    normalized = copy.deepcopy(result)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}

    for key, prop_schema in properties.items():
        if key not in normalized or not isinstance(prop_schema, dict):
            continue
        enum_values = prop_schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            normalized[key] = _fuzzy_match_enum(normalized[key], enum_values)
        else:
            normalized[key] = _coerce_type(normalized[key], prop_schema)

    for key in schema.get("required") or []:
        # Only fill when the model *returned* this key but left it blank — an
        # entirely absent required key is a structural gap (e.g. a wrong
        # field name), not a blank value, and should still surface as a
        # genuine validation failure for the repair loop to handle rather
        # than being papered over with a synthesized placeholder.
        if key not in normalized:
            continue
        prop_schema = properties.get(key)
        if not isinstance(prop_schema, dict) or prop_schema.get("type") != "string":
            continue
        if not str(normalized.get(key) or "").strip():
            normalized[key] = "unknown"

    return _strip_unknown_keys(normalized, schema)


def normalize_structured_result(
    result: dict[str, Any] | None,
    *,
    output_schema_name: str | None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Best-effort structural cleanup without inventing academic facts."""
    if not isinstance(result, dict):
        return result

    schema = output_schema if isinstance(output_schema, dict) else {"additionalProperties": True}
    if output_schema_name == "task_understanding_output_v1":
        return _normalize_task_understanding_result(result, schema)
    if output_schema_name == "planner_output_v1":
        return _normalize_planner_result(result, schema)
    return _normalize_generic_result(result, schema)
