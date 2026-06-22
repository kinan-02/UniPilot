"""Typed bucket rule DSL parsed from catalog_rules exports."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

RuleOperator = Literal[
    "all_of",
    "choose_n",
    "choose_chain",
    "min_credits",
    "one_of",
    "sequence",
]


class BucketRuleType(str, Enum):
    SEMESTER_MATRIX = "semester_matrix"
    CREDIT_BUCKET = "credit_bucket"
    COURSE_POOL = "course_pool"
    TRACK_REQUIREMENT = "track_requirement"
    ADVISORY = "advisory"


PLANNING_ONLY_TYPES = frozenset({BucketRuleType.SEMESTER_MATRIX.value})
HARD_ENFORCEMENT_TYPES = frozenset({BucketRuleType.CREDIT_BUCKET.value})


def parse_rule_expression(rule_expression: dict[str, Any] | None) -> dict[str, Any]:
    expression = rule_expression or {}
    rule_type = str(expression.get("type") or "unknown")
    return {
        "type": rule_type,
        "operator": expression.get("operator"),
        "semester": expression.get("semester"),
        "chooseCount": expression.get("chooseCount"),
        "minCredits": expression.get("minCredits"),
        "chain": expression.get("chain"),
        "isPlanningOnly": rule_type in PLANNING_ONLY_TYPES,
        "isHardRule": rule_type in HARD_ENFORCEMENT_TYPES,
        "raw": expression,
    }


def summarize_elective_bucket(rule_document: dict[str, Any]) -> dict[str, Any]:
    """Lightweight bucket summary for Phase 2 explorer (included in graph payload)."""
    expression = parse_rule_expression(rule_document.get("ruleExpression"))
    return {
        "groupId": rule_document.get("requirementGroupId") or rule_document.get("groupId"),
        "title": rule_document.get("title"),
        "requirementType": rule_document.get("requirementType", "elective"),
        "minCredits": rule_document.get("minCredits"),
        "rule": expression,
        "courseCount": len(rule_document.get("courseReferences") or []),
        "advisoryOnly": bool(rule_document.get("advisoryOnly", True)),
        "manualReviewRequired": bool(rule_document.get("manualReviewRequired", True)),
        "notes": (rule_document.get("notes") or [])[:3],
        "phase": 2,
        "explorerReady": expression["type"] == BucketRuleType.COURSE_POOL.value,
    }
