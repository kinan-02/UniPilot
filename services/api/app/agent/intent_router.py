"""Rules-first intent classification (spec §8)."""

from __future__ import annotations

import re

from app.agent.schemas import AgentIntent, IntentClassification

_COURSE_NUMBER = re.compile(r"\b\d{5,9}\b")

_GRADUATION_PATTERNS = (
    re.compile(r"\b(graduat|graduation progress|missing to graduate|what am i missing|credits (do i|left)|can i graduate)\b", re.I),
    re.compile(r"(מה חסר|להתקבל לתואר|כמה נקודות נשאר|התקדמות בלימודים)", re.I),
)

_TRANSCRIPT_PATTERNS = (
    re.compile(r"\b(import|upload|parse).*(transcript|gradesheet)\b", re.I),
    re.compile(r"(ייבא|העלה|טען).*(גיליון|תעודה|ציונים)", re.I),
)

_SEMESTER_PLAN_PATTERNS = (
    re.compile(r"\b(build|plan|suggest|create).*(semester|schedule)\b", re.I),
    re.compile(r"\b(no friday|lighter|max credits|credit limit)\b", re.I),
    re.compile(r"(תכנן|בנה|הצע).*(סמסטר|מערכת)", re.I),
)

_SEMESTER_PLAN_MODIFY_PATTERNS = (
    re.compile(r"\b(modify|update|change|adjust|replace|remove|make).*(plan|schedule)\b", re.I),
    re.compile(r"\bmake (this|the|my) plan lighter\b", re.I),
    re.compile(r"\bremove friday\b", re.I),
    re.compile(r"\breplace (this|the) course\b", re.I),
    re.compile(r"\bavoid morning\b", re.I),
    re.compile(r"(שנה|עדכן|החלף).*(תוכנית|מערכת)", re.I),
)

_PROFILE_UPDATE_PATTERNS = (
    re.compile(r"\b(update|change|set).*(profile|degree|track|catalog year)\b", re.I),
    re.compile(r"(עדכן|שנה).*(פרופיל|מסלול|תואר)", re.I),
)

_COURSE_QUESTION_PATTERNS = (
    re.compile(r"\b(can i take|am i allowed to take|is .+ offered|prerequisite|does .+ count)\b", re.I),
    re.compile(r"\btake (this|the) course\b", re.I),
    re.compile(r"\b(offered next semester|next semester)\b.*\bcourse\b", re.I),
    re.compile(r"\bcourse\b.*\b(offered|prerequisite|count)\b", re.I),
    re.compile(r"(אפשר לקחת|מוצע|דרישות קדם|סופר ל)", re.I),
)

_REQUIREMENT_EXPLAIN_PATTERNS = (
    re.compile(r"\b(explain|what is|tell me about).*(requirement|bucket|elective)\b", re.I),
    re.compile(r"(הסבר|מה זה).*(דרישה|מכללה|בחירה)", re.I),
)


def _matches_any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def classify_intent(message: str) -> IntentClassification:
    """Classify user message using deterministic rules (LLM fallback deferred to Phase 2+)."""
    normalized = (message or "").strip()
    lowered = normalized.lower()

    if not normalized:
        return IntentClassification(
            intent="unknown_or_unsupported",
            confidence=1.0,
            required_context=[],
        )

    if _matches_any(_TRANSCRIPT_PATTERNS, lowered):
        return IntentClassification(
            intent="transcript_import",
            confidence=0.9,
            requires_file=True,
            required_context=["uploaded_file"],
        )

    if _matches_any(_SEMESTER_PLAN_MODIFY_PATTERNS, lowered):
        return IntentClassification(
            intent="semester_plan_modification",
            confidence=0.9,
            requires_confirmation=True,
            required_context=[
                "student_profile",
                "completed_courses",
                "saved_semester_plans",
                "course_offerings",
            ],
        )

    if _matches_any(_PROFILE_UPDATE_PATTERNS, lowered):
        return IntentClassification(
            intent="profile_update",
            confidence=0.86,
            requires_confirmation=True,
            required_context=["student_profile"],
        )

    if _matches_any(_SEMESTER_PLAN_PATTERNS, lowered):
        return IntentClassification(
            intent="semester_plan_generation",
            confidence=0.88,
            required_context=[
                "student_profile",
                "completed_courses",
                "degree_requirements",
                "course_offerings",
                "user_preferences",
            ],
        )

    if _COURSE_NUMBER.search(normalized) and _matches_any(_COURSE_QUESTION_PATTERNS, lowered):
        return IntentClassification(
            intent="course_question",
            confidence=0.92,
            required_context=[
                "student_profile",
                "completed_courses",
                "course_record",
                "course_offering",
            ],
        )

    if _COURSE_NUMBER.search(normalized):
        return IntentClassification(
            intent="course_question",
            confidence=0.75,
            required_context=[
                "student_profile",
                "completed_courses",
                "course_record",
            ],
        )

    if _matches_any(_COURSE_QUESTION_PATTERNS, lowered):
        return IntentClassification(
            intent="course_question",
            confidence=0.85,
            required_context=[
                "student_profile",
                "completed_courses",
                "course_record",
            ],
        )

    if _matches_any(_GRADUATION_PATTERNS, lowered):
        return IntentClassification(
            intent="graduation_progress_check",
            confidence=0.9,
            required_context=[
                "student_profile",
                "completed_courses",
                "degree_requirements",
            ],
        )

    if _matches_any(_REQUIREMENT_EXPLAIN_PATTERNS, lowered) or any(
        phrase in lowered
        for phrase in (
            "why is this requirement incomplete",
            "why did this course not count",
            "missing electives",
            "what does this bucket mean",
            "incomplete requirement",
        )
    ):
        return IntentClassification(
            intent="requirement_explanation",
            confidence=0.85,
            required_context=["degree_requirements", "catalog_wiki", "completed_courses"],
        )

    if "prerequisite" in lowered or "דרישות קדם" in normalized:
        return IntentClassification(
            intent="prerequisite_check",
            confidence=0.8,
            required_context=["student_profile", "completed_courses", "course_record"],
        )

    if "catalog" in lowered or "search" in lowered:
        return IntentClassification(
            intent="catalog_search",
            confidence=0.7,
            required_context=["catalog"],
        )

    return IntentClassification(
        intent="general_academic_question",
        confidence=0.5,
        required_context=["student_profile"],
    )
