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

# A model asked for a numeric confidence very often gives a word instead
# (e.g. top-level "confidence": "high" instead of 0.9) -- found alongside
# the facts-list-vs-object mismatch this module also recovers from.
_CONFIDENCE_WORD_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}


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
        lowered = value.strip().lower()
        if lowered in _CONFIDENCE_WORD_MAP:
            return _CONFIDENCE_WORD_MAP[lowered]
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


def _coerce_confidence_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _CONFIDENCE_WORD_MAP:
            return _CONFIDENCE_WORD_MAP[lowered]
        try:
            return max(0.0, min(1.0, float(lowered)))
        except ValueError:
            return None
    return None


def _flatten_fact_list_to_object(items: list[Any]) -> tuple[dict[str, Any], float | None, str | None]:
    """A model asked for `facts` as a flat object plus a separate top-level
    certainty_basis/confidence very often instead produces a LIST of
    individually-confidence-tagged fact items (`{label, value, source,
    confidence}` or `{fact, source, confidence}`, `confidence` sometimes a
    word like "high" instead of a number, sometimes nested under a
    `certainty` sub-object) -- a reasonable instinct when facts genuinely
    carry different certainty levels, but not the shape the schema accepts.
    Found via a live-eval run to be the single most common repair trigger:
    53 of 96 schema-repair calls across every case that night were exactly
    this one mismatch.

    Converts the list into the required flat object, keyed by whatever
    label-ish field each item has (never guessing which sub-field is "the"
    value -- the whole item is preserved), and derives the missing
    top-level certainty_basis/confidence from the items' own per-fact tags
    via the same min-confidence-aggregation convention already used
    elsewhere in this codebase (compose_answer.py's `_aggregate_certainty`).
    """
    flat: dict[str, Any] = {}
    confidences: list[float] = []
    bases: set[str] = set()

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            flat[f"fact_{index}"] = item
            continue
        # "key" belongs in this label-field list: the Retrieval agent
        # routinely emits facts as [{key: "currentSemesterCode", value: ...}]
        # (its own prompt tells it to label a fact by the tool's field name).
        # Without recognizing "key", such an item fell through to a generic
        # fact_N bucket -- a live-eval run showed a correct
        # currentSemesterCode="2025-2" buried at facts.fact_0.value, which the
        # downstream success-criteria check then could not recognize as
        # satisfying "current semester code returned", false-negative-ing a
        # correct result into an expensive replan loop. Ordered before "fact"
        # because "fact" is often a whole sentence, "key" a clean short label.
        key = (
            item.get("label")
            or item.get("name")
            or item.get("key")
            or item.get("fact")
            or f"fact_{index}"
        )
        flat[str(key)[:80]] = item

        certainty = item.get("certainty") if isinstance(item.get("certainty"), dict) else {}
        confidence = _coerce_confidence_value(item.get("confidence"))
        if confidence is None:
            confidence = _coerce_confidence_value(certainty.get("confidence"))
        if confidence is not None:
            confidences.append(confidence)

        basis = item.get("basis") or certainty.get("basis")
        if isinstance(basis, str) and basis:
            bases.add(basis)

    aggregate_confidence = min(confidences) if confidences else None
    aggregate_basis = bases.pop() if len(bases) == 1 else ("llm_interpretation" if bases else None)
    return flat, aggregate_confidence, aggregate_basis


def _recover_facts_list_and_missing_certainty(
    result: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Applies `_flatten_fact_list_to_object` to whichever object-typed
    property received a list instead, and backfills top-level
    certainty_basis/confidence from it when the model omitted those
    required fields entirely (having pushed per-fact confidence into the
    list items instead). Only touches keys the model left genuinely
    absent -- never overwrites a certainty_basis/confidence the model did
    provide, even if a facts-list is also present.
    """
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = set(schema.get("required") or [])
    has_certainty_fields = "certainty_basis" in properties and "confidence" in properties

    for key, prop_schema in properties.items():
        if not isinstance(prop_schema, dict) or prop_schema.get("type") != "object":
            continue
        value = result.get(key)
        if not isinstance(value, list):
            continue
        flat, agg_confidence, agg_basis = _flatten_fact_list_to_object(value)
        result[key] = flat
        if (
            has_certainty_fields
            and "certainty_basis" in required
            and "confidence" in required
            and "certainty_basis" not in result
            and "confidence" not in result
        ):
            if agg_confidence is not None:
                result["confidence"] = agg_confidence
            if agg_basis is not None:
                result["certainty_basis"] = agg_basis

    return result


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
    normalized = _recover_facts_list_and_missing_certainty(normalized, schema)
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
