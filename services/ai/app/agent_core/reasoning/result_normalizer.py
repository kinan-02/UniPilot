"""Normalize structured ReasoningBlock `result` payloads before schema validation."""

from __future__ import annotations

import copy
from typing import Any

# Shared with callers (e.g. `llm_response_composer.py`, `general_academic_workflow.py`)
# that need to tell a genuine model answer apart from this structural
# safe-filler: `_normalize_generic_result` substitutes this for any *required*
# string field the model returned but left blank. It is a placeholder to keep
# schema validation from hard-failing on a structural gap -- never real
# content -- so any caller that would otherwise show a composed `text` field
# straight to the user must treat an exact match against this constant the
# same as "no usable answer," not as a genuine (if terse) response.
GENERIC_BLANK_FIELD_PLACEHOLDER = "unknown"


def _strip_unknown_keys(value: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("additionalProperties") is not False:
        return value
    allowed = set((schema.get("properties") or {}).keys())
    return {key: item for key, item in value.items() if key in allowed}


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
            normalized[key] = GENERIC_BLANK_FIELD_PLACEHOLDER

    return _strip_unknown_keys(normalized, schema)


def normalize_structured_result(
    result: dict[str, Any] | None,
    *,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Best-effort structural cleanup without inventing academic facts."""
    if not isinstance(result, dict):
        return result

    schema = output_schema if isinstance(output_schema, dict) else {"additionalProperties": True}
    return _normalize_generic_result(result, schema)
