"""Extract academic entities from user text (spec §10 — Phase 1 basics)."""

from __future__ import annotations

import re
from typing import Any

_COURSE_NUMBER = re.compile(r"\b(\d{5,9})\b")
_GRADUATION_CONTEXT = re.compile(r"\b(graduat|graduate|תואר)\b", re.I)
_TRACK_CODE_CONTEXT = re.compile(r"\btrack code\b", re.I)
_TRACK_CODE_NUMBER = re.compile(r"\btrack code\s+(\d{5,6})\b", re.I)
_TRACK_NAME_HINT = re.compile(
    r"\b4[- ]year\s+general\s+computer\s+science\b|\bgeneral\s+cs\b.*\b4[- ]year\b",
    re.I,
)
_REQUIREMENT_BUCKET = re.compile(
    r"\b(elective|bucket|requirement|mandatory|math|physics|faculty|english)\b",
    re.I,
)
_REPLACE_COURSE = re.compile(r"\breplace\s+(?:course\s+)?(\d{5,9})\b", re.I)
_ADD_COURSE = re.compile(r"\badd\s+(?:course\s+)?(\d{5,9})\b", re.I)
_SEMESTER_CODE = re.compile(r"\b(20\d{2})[-/]([12])\b")
_MAX_CREDITS = re.compile(r"\b(?:max|up to|not more than|at most)\s+(\d{1,2})\s*credits?\b", re.I)
_AVOID_FRIDAY = re.compile(r"\bno friday\b", re.I)
_DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _resolve_wiki_entity_slugs(text: str) -> list[str]:
    try:
        from app.config import get_settings
        from app.retrieval.graph_engine.graph_registry import graph_registry

        cfg = get_settings()
        if not cfg.is_graph_retrieval_configured():
            return []
        engine = graph_registry.get_engine(cfg)
        return engine.resolve_slugs_from_query(text)
    except Exception:
        return []


def resolve_entities(message: str, *, conversation_entities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return normalized entities; merges with prior conversation state."""
    base = dict(conversation_entities or {})
    text = (message or "").strip()
    if not text:
        return base

    track_code_match = _TRACK_CODE_NUMBER.search(text)
    if track_code_match:
        base["trackCode"] = track_code_match.group(1)
        base.pop("courseNumber", None)
    elif _TRACK_NAME_HINT.search(text):
        base["trackSlug"] = "track-computer-science-general-4year"
        base.pop("courseNumber", None)
    elif _TRACK_CODE_CONTEXT.search(text):
        numbers = _COURSE_NUMBER.findall(text)
        if numbers:
            base["trackCode"] = numbers[0]
            base.pop("courseNumber", None)

    numbers = _COURSE_NUMBER.findall(text)
    if numbers and "trackCode" not in base and "trackSlug" not in base:
        first = numbers[0]
        digit_len = len(re.sub(r"\D", "", first))
        if digit_len == 6 and _GRADUATION_CONTEXT.search(text):
            base["trackCode"] = first
        else:
            base["courseNumber"] = first
        if len(numbers) > 1:
            base["courseNumbers"] = numbers

    credit_match = _MAX_CREDITS.search(text)
    if credit_match:
        base["maxCredits"] = int(credit_match.group(1))

    if _AVOID_FRIDAY.search(text):
        avoid = list(base.get("avoidDays") or [])
        if "Friday" not in avoid:
            avoid.append("Friday")
        base["avoidDays"] = avoid

    lowered = text.lower()
    for day in _DAY_NAMES:
        if f"no {day}" in lowered:
            avoid = list(base.get("avoidDays") or [])
            label = day.capitalize()
            if label not in avoid:
                avoid.append(label)
            base["avoidDays"] = avoid

    if "lighter" in lowered or "easier" in lowered:
        base["planningObjective"] = "lighter_workload"
    elif "heavier" in lowered or "more challenging" in lowered:
        base["planningObjective"] = "heavier_workload"

    if "next semester" in lowered:
        base["targetSemester"] = "next"

    semester_match = _SEMESTER_CODE.search(text)
    if semester_match:
        base["targetSemesterCode"] = f"{semester_match.group(1)}-{semester_match.group(2)}"

    replace_match = _REPLACE_COURSE.search(text)
    if replace_match:
        base["replaceCourseNumber"] = replace_match.group(1)
        base["modificationType"] = "replace_course"

    add_match = _ADD_COURSE.search(text)
    if add_match:
        base["addCourseNumber"] = add_match.group(1)
        base["modificationType"] = "add_course"

    if any(
        phrase in lowered
        for phrase in ("make this plan lighter", "make the plan lighter", "lighter plan")
    ):
        base["modificationType"] = "lighter"
        base["planningObjective"] = "lighter_workload"

    if "remove friday" in lowered or "no friday classes" in lowered:
        base["modificationType"] = "avoid_days"

    if "avoid morning" in lowered:
        base["modificationType"] = "avoid_morning"

    if _REQUIREMENT_BUCKET.search(text):
        for token in ("elective", "electives", "math", "physics", "english", "faculty"):
            if token in lowered:
                base["requirementBucket"] = token
                break

    resolved_slugs = _resolve_wiki_entity_slugs(text)
    if resolved_slugs:
        base["resolvedWikiSlugs"] = resolved_slugs
        primary = resolved_slugs[0]
        if primary.startswith("track-"):
            base["trackSlug"] = primary
            base.pop("courseNumber", None)
        elif primary.startswith("minor-") or primary.startswith("program-"):
            base["programSlug"] = primary
        elif primary.startswith("regulations-"):
            base["wikiSlug"] = primary

    return base
