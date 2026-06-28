"""Typed bucket rule DSL parsed from catalog_rules exports."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from app.planning.prerequisite_resolver import canonical_course_number
from app.curriculum.pool_course_enrichment import resolve_pool_allowed_prefixes
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

DEDICATED_BUCKET_POOL_SUFFIXES = frozenset(
    {
        "elective-ds-pool",
        "elective-faculty-pool",
        "enrichment-pool",
        "physical-education-pool",
    }
)


def resolve_progress_display(
    rule_document: dict[str, Any],
    *,
    program_code: str | None = None,
) -> str:
    """How the explorer should show progress for this pool."""
    expression = rule_document.get("ruleExpression") or {}
    operator = expression.get("operator")
    group_id = str(rule_document.get("requirementGroupId") or "")
    prefix = f"{program_code}:" if program_code else ""
    suffix = group_id[len(prefix) :] if prefix and group_id.startswith(prefix) else group_id

    if operator in {"choose_n", "choose_chain"}:
        return "chain_steps"
    if suffix in DEDICATED_BUCKET_POOL_SUFFIXES:
        return "dedicated_bucket_credits"
    if "additional" in suffix or (
        operator == "min_credits" and expression.get("allowedPrefixes")
    ):
        return "shared_bucket_credits"
    return "none"


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


def summarize_pool_course_reference(
    course_ref: dict[str, Any],
    *,
    catalog_course: dict[str, Any] | None = None,
) -> dict[str, Any]:
    number = course_ref.get("courseNumber")
    catalog = catalog_course or {}
    title = catalog.get("title") or course_ref.get("titleHint") or number
    title_he = catalog.get("titleHebrew")
    credits = catalog.get("credits")
    if credits is None:
        credits = course_ref.get("creditsHint")

    from app.services.course_reference_keys import course_reference_number_keys

    alternatives = list(course_ref.get("alternatives") or [])
    if not alternatives:
        from app.curriculum.data_quality import parse_alternatives_from_text

        notes = course_ref.get("notes") or []
        notes_text = " ".join(str(note) for note in notes)
        alternatives = parse_alternatives_from_text(
            notes_text,
            course_ref.get("prerequisitesText"),
        )

    return {
        "courseNumber": number,
        "title": title,
        "titleHe": title_he,
        "credits": credits,
        "alternatives": alternatives,
        "notes": (course_ref.get("notes") or [])[:2],
    }


def summarize_elective_bucket(
    rule_document: dict[str, Any],
    *,
    program_code: str | None = None,
    courses_by_number: dict[str, dict[str, Any]] | None = None,
    linked_credit_bucket_id: str | None = None,
) -> dict[str, Any]:
    """Lightweight bucket summary for Phase 2 explorer (included in graph payload)."""
    expression = parse_rule_expression(rule_document.get("ruleExpression"))
    raw_expression = expression.get("raw") or {}
    courses_lookup = courses_by_number or {}
    courses = [
        summarize_pool_course_reference(
            course_ref,
            catalog_course=courses_lookup.get(
                canonical_course_number(str(course_ref.get("courseNumber") or "")) or ""
            ),
        )
        for course_ref in rule_document.get("courseReferences") or []
        if course_ref.get("courseNumber")
    ]

    list_source = rule_document.get("explorerCourseListSource")
    if not list_source:
        list_source = "explicit" if courses else "empty"

    return {
        "groupId": rule_document.get("requirementGroupId") or rule_document.get("groupId"),
        "title": rule_document.get("title"),
        "requirementType": rule_document.get("requirementType", "elective"),
        "minCredits": rule_document.get("minCredits"),
        "linkedCreditBucketId": linked_credit_bucket_id,
        "rule": expression,
        "allowedPrefixes": raw_expression.get("allowedPrefixes")
        or (
            resolve_pool_allowed_prefixes(rule_document, program_code=program_code or "")
            if program_code
            else []
        ),
        "courses": courses,
        "courseCount": len(courses),
        "courseListSource": list_source,
        "coursesTruncated": bool(rule_document.get("explorerCoursesTruncated", False)),
        "advisoryOnly": bool(rule_document.get("advisoryOnly", True)),
        "manualReviewRequired": bool(rule_document.get("manualReviewRequired", True)),
        "notes": (rule_document.get("notes") or [])[:5],
        "catalogDescription": rule_document.get("catalogDescription"),
        "phase": 2,
        "explorerReady": expression["type"] == BucketRuleType.COURSE_POOL.value,
        "progressDisplay": resolve_progress_display(
            rule_document,
            program_code=program_code,
        ),
    }
