"""`apply_deterministic_rule` -- arithmetic/validation given an already-identified
rule and already-retrieved facts (docs/agent/AGENT_VISION.md §5, primitive 6).
Never involves an LLM call at execution time -- only the LLM's decision to
invoke it does (§4).

`rule`'s shape and the `rule["type"]` vocabulary implemented here are defined
in docs/agent/DETERMINISTIC_RULE_CONTRACT.md -- the single source of truth
for both, since nothing else in the codebase defines a "rule" shape. Update
that doc whenever this file's vocabulary changes.
"""

from __future__ import annotations

from numbers import Number
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "apply_deterministic_rule"

_COMPARATORS = {
    ">=": lambda value, threshold: value >= threshold,
    ">": lambda value, threshold: value > threshold,
    "<=": lambda value, threshold: value <= threshold,
    "<": lambda value, threshold: value < threshold,
    "==": lambda value, threshold: value == threshold,
    "!=": lambda value, threshold: value != threshold,
}

_HandlerResult = tuple[dict[str, Any] | None, str | None]


class ApplyDeterministicRuleInput(BaseModel):
    rule: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _matches_filter(record: dict[str, Any], record_filter: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in record_filter.items())


def _require_fields(rule: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        if rule.get(field) in (None, ""):
            return f"{field}_required"
    return None


def _resolve_comparator(rule: dict[str, Any]) -> tuple[Any, str | None]:
    comparator = rule.get("comparator")
    if comparator not in _COMPARATORS:
        return None, f"unknown_comparator: {comparator}"
    return _COMPARATORS[comparator], None


def _resolve_list_source(facts: dict[str, Any], source: str) -> tuple[list[Any] | None, str | None]:
    if source not in facts:
        return None, f"facts_source_missing: {source}"
    value = facts[source]
    if not isinstance(value, list):
        return None, f"facts_source_wrong_shape: {source}"
    return value, None


def _sum_threshold(rule: dict[str, Any], facts: dict[str, Any]) -> _HandlerResult:
    missing = _require_fields(rule, ("source", "field", "comparator", "threshold"))
    if missing:
        return None, missing
    comparator_fn, error = _resolve_comparator(rule)
    if error:
        return None, error

    source = rule["source"]
    field = rule["field"]
    record_filter = rule.get("filter") or {}
    records, error = _resolve_list_source(facts, source)
    if error:
        return None, error

    matched = [record for record in records if _matches_filter(record, record_filter)]
    total = 0
    for record in matched:
        value = record.get(field)
        if not _is_number(value):
            return None, f"non_numeric_field_value: {source}.{field}"
        total += value

    threshold = rule["threshold"]
    return {
        "type": "sum_threshold",
        "sum": total,
        "comparator": rule["comparator"],
        "threshold": threshold,
        "satisfied": comparator_fn(total, threshold),
        "matchedCount": len(matched),
    }, None


def _count_threshold(rule: dict[str, Any], facts: dict[str, Any]) -> _HandlerResult:
    missing = _require_fields(rule, ("source", "comparator", "threshold"))
    if missing:
        return None, missing
    comparator_fn, error = _resolve_comparator(rule)
    if error:
        return None, error

    source = rule["source"]
    record_filter = rule.get("filter") or {}
    records, error = _resolve_list_source(facts, source)
    if error:
        return None, error

    count = sum(1 for record in records if _matches_filter(record, record_filter))
    threshold = rule["threshold"]
    return {
        "type": "count_threshold",
        "count": count,
        "comparator": rule["comparator"],
        "threshold": threshold,
        "satisfied": comparator_fn(count, threshold),
    }, None


def _field_comparison(rule: dict[str, Any], facts: dict[str, Any]) -> _HandlerResult:
    missing = _require_fields(rule, ("source", "field", "comparator", "threshold"))
    if missing:
        return None, missing
    comparator_fn, error = _resolve_comparator(rule)
    if error:
        return None, error

    source = rule["source"]
    field = rule["field"]
    if source not in facts:
        return None, f"facts_source_missing: {source}"
    record = facts[source]
    if not isinstance(record, dict):
        return None, f"facts_source_wrong_shape: {source}"

    value = record.get(field)
    if not _is_number(value):
        return None, f"non_numeric_field_value: {source}.{field}"

    threshold = rule["threshold"]
    return {
        "type": "field_comparison",
        "value": value,
        "comparator": rule["comparator"],
        "threshold": threshold,
        "satisfied": comparator_fn(value, threshold),
    }, None


_HANDLERS: dict[str, Any] = {
    "sum_threshold": _sum_threshold,
    "count_threshold": _count_threshold,
    "field_comparison": _field_comparison,
}


async def run_apply_deterministic_rule(payload: ApplyDeterministicRuleInput) -> ToolOutputEnvelope:
    rule_type = str(payload.rule.get("type") or "").strip()
    if not rule_type:
        return ToolOutputEnvelope(ok=False, data=None, error="rule_type_required")

    handler = _HANDLERS.get(rule_type)
    if handler is None:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_rule_type: {rule_type}")

    data, error = handler(payload.rule, payload.facts)
    if error is not None:
        return ToolOutputEnvelope(ok=False, data=None, error=error)

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Apply a deterministic rule to given facts (credit totals, threshold checks, "
    "academic-standing checks). Pure computation -- returns 'insufficient to determine' "
    "(ok=False) rather than a best guess. See docs/agent/DETERMINISTIC_RULE_CONTRACT.md "
    "for the rule shape and rule-type vocabulary.",
    input_model=ApplyDeterministicRuleInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_apply_deterministic_rule,
)
