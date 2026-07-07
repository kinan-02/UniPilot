"""Regression assertion helpers for golden-set anti-overfit validation (Phase 27.2)."""

from __future__ import annotations

import re
from typing import Any

from app.agent.evaluation.final_answer_eval import derive_source_warnings
from app.services.academic_lookup_service import (
    classify_course_question_focus,
    detect_academic_query_kind,
    try_compose_deterministic_answer,
)

_ELIGIBILITY_DRIFT_STARTERS = (
    re.compile(r"^\s*yes\s*[—\-]\s*you appear eligible\b", re.I),
    re.compile(r"^\s*yes\s*[—\-]\s*you can take\b", re.I),
)

_CATALOG_INFO_PROMPTS = (
    re.compile(r"\bwhat are the prerequisites\b", re.I),
    re.compile(r"\blist the prerequisites\b", re.I),
    re.compile(r"\bprerequisite courses?\b", re.I),
    re.compile(r"\bwhich tracks require\b", re.I),
    re.compile(r"\btracks require\b", re.I),
    re.compile(r"(דרישות קדם|אילו מסלולים)", re.I),
)

_TRACK_STRUCTURE_PROMPTS = (
    re.compile(r"\btrack code\b", re.I),
    re.compile(r"\bcredit breakdown\b", re.I),
    re.compile(r"\bbroken down by category\b", re.I),
    re.compile(r"\bhow many credits\b.*\bgraduat\b", re.I),
    re.compile(r"(נקודות|זכות).*(מסלול|תואר)", re.I),
)

_COURSE_NOT_FOUND = re.compile(r"\bcourse\s+\d{5,9}\s+was not found\b", re.I)


def is_information_lookup_prompt(user_request: str) -> bool:
    text = (user_request or "").strip()
    if not text:
        return False
    if any(pattern.search(text) for pattern in _CATALOG_INFO_PROMPTS):
        return classify_course_question_focus(text) != "eligibility"
    if any(pattern.search(text) for pattern in _TRACK_STRUCTURE_PROMPTS):
        return True
    kind = detect_academic_query_kind(text)
    return kind in {
        "course_catalog_prerequisites",
        "course_tracks_requiring",
        "course_compound_catalog",
        "track_credit_breakdown",
        "regulation_moed_grade",
        "regulation_standing_list",
    }


def is_eligibility_prompt(user_request: str) -> bool:
    return classify_course_question_focus(user_request) == "eligibility"


def has_eligibility_drift(*, user_request: str, final_answer: str) -> bool:
    """True when an information lookup prompt produced a personal eligibility stub."""
    if not is_information_lookup_prompt(user_request):
        return False
    answer = (final_answer or "").strip()
    if not answer:
        return False
    return any(pattern.search(answer) for pattern in _ELIGIBILITY_DRIFT_STARTERS)


def has_track_course_confusion(*, user_request: str, final_answer: str) -> bool:
    """True when a track-structure prompt was answered with course-not-found."""
    if not any(pattern.search(user_request or "") for pattern in _TRACK_STRUCTURE_PROMPTS):
        return False
    return bool(_COURSE_NOT_FOUND.search(final_answer or ""))


def count_numbered_items(text: str) -> int:
    """Count lines like '1. ...' or 'Condition 1:'."""
    if not text:
        return 0
    numbered = re.findall(r"(?:^|\n)\s*\d+\.\s+", text)
    condition_numbered = re.findall(r"(?:^|\n)\s*\d+\.\s+", text)
    return max(len(numbered), len(condition_numbered))


def count_track_slugs(text: str) -> int:
    return len(re.findall(r"\btrack-[a-z0-9-]+(?:-[a-z0-9-]+)*\b", text or ""))


def assert_complete_track_list(text: str, *, minimum: int) -> bool:
    return count_track_slugs(text) >= minimum


def assert_complete_standing_conditions(text: str, *, expected: int = 8) -> bool:
    if not text:
        return False
    hits = sum(1 for number in range(1, expected + 1) if re.search(rf"(?:^|\n)\s*{number}\.\s+", text))
    return hits >= expected


def assert_credit_breakdown_values(text: str) -> bool:
    haystack = text or ""
    required_tokens = ("155", "87", "56", "12")
    return all(token in haystack for token in required_tokens)


def assert_wiki_sources_grounded(
    *,
    final_answer: str,
    used_sources: list[str] | None,
    expected_pages: list[str],
) -> tuple[bool, list[str]]:
    warnings = derive_source_warnings(
        answer=final_answer,
        used_sources=used_sources,
        expected_pages=expected_pages,
    )
    return len(warnings) == 0, warnings


def deterministic_answer_for_prompt(
    user_request: str,
    *,
    entities: dict[str, Any] | None = None,
) -> tuple[str, list[str]] | None:
    return try_compose_deterministic_answer(user_request, entities=entities or {})
