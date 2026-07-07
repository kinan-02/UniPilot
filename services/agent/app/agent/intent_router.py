"""Rules-first intent classification (spec §8)."""

from __future__ import annotations

import re

from app.agent.schemas import AgentIntent, IntentClassification

_COURSE_NUMBER = re.compile(r"\b\d{5,9}\b")

_PROGRAM_MINOR_PATTERNS = (
    re.compile(r"\b(minor|program|excellence|specialization|specialisation)\b", re.I),
    re.compile(r"\b(מינור|תוכנית|התמחות|מצוינות)\b"),
    re.compile(r"\brobotics minor\b", re.I),
    re.compile(r"\binter-faculty robotics\b", re.I),
)

_TRACK_STRUCTURE_PATTERNS = (
    re.compile(r"\btrack code\b", re.I),
    re.compile(r"\b(total\s+)?credits?\b.*\b(graduat(?:e|ion)?|breakdown|category|categories)\b", re.I),
    re.compile(r"\bhow many credits\b.*\bgraduat(?:e|ion)?\b", re.I),
    re.compile(r"\bbroken down by category\b", re.I),
    re.compile(r"\b(bsc|b\.sc\.|track)\b.*\b(credits?|credit requirement)\b", re.I),
    re.compile(r"\bfirst semester\b.*\b(track|courses?)\b", re.I),
    re.compile(r"\b(biomedical engineering|industrial engineering|data information engineering)\b", re.I),
)

_REGULATION_LOOKUP_PATTERNS = (
    # Max course load
    re.compile(r"\bmaximum number of credits\b", re.I),
    re.compile(r"\bmax(?:imum)?\s+credits\b.*\bsemester\b", re.I),
    re.compile(r"\bwithout special approval\b", re.I),
    re.compile(r"\b29\s+credits\b", re.I),
    re.compile(r"\b(עומס|29\s+נק|כמה נקודות.*סמסטר|מקסימום נקודות)\b", re.I),
    # Retaking / grade improvement
    re.compile(r"\b(retake|re-take|grade improvement|improve\s+(?:my\s+)?grade)\b", re.I),
    re.compile(r"\btake\s+(?:it|the course|this course)\s+again\b", re.I),
    re.compile(r"\buntil when\b.*\bregister\b", re.I),
    re.compile(r"\bשיפור ציון|לחזור על הקורס\b", re.I),
    # Grade appeal
    re.compile(r"\bgrade appeal\b", re.I),
    re.compile(r"\b(?:how many\s+)?days?\b.*\b(?:appeal|submit an appeal)\b", re.I),
    re.compile(r"\bbקשת ערר|ערר על ציון\b", re.I),
    # Graduation honors
    re.compile(r"\b(cum laude|summa cum laude)\b", re.I),
    re.compile(r"\b(graduation\s+)?honors?\b.*\b(gpa|average|require|threshold|graduate)\b", re.I),
    re.compile(r"\b(graduate|graduation)\b.*\bhonors?\b", re.I),
    re.compile(r"\bהצטיינות\b", re.I),
    # Per-semester excellence
    re.compile(r"\b(dean'?s?|president'?s?)\s+excellence\b", re.I),
    re.compile(r"\bהצטיינות\s+(דיקן|נשיא)\b", re.I),
    # Track transfer
    re.compile(r"\btransfer\b.*\btrack\b", re.I),
    re.compile(r"\bchange\b.*\btrack\b", re.I),
    re.compile(r"\btop quartile\b", re.I),
    re.compile(r"\boption\s+[abc]\b.*\btransfer\b", re.I),
    re.compile(r"\bמעבר מסלול|העברה בין מסלולים\b", re.I),
    # Graduate admission GPA
    re.compile(r"\b(?:minimum\s+)?gpa\b.*\b(?:msc|phd|master|doctorate|graduate\s+(?:school|program|admission))\b", re.I),
    re.compile(r"\b(?:msc|phd|master|doctorate)\b.*\b(?:admission|admitted|minimum\s+gpa|requirement)\b", re.I),
    re.compile(r"\bממוצע.*(?:קבלה|מוסמך|דוקטורט)\b", re.I),
    re.compile(r"\bקבלה.*(?:מוסמך|תואר שני|פ''ד)\b", re.I),
    # Scholarship
    re.compile(r"\bscholarship\b.*\b(?:duration|months|gpa|minimum|eligib)\b", re.I),
    re.compile(r"\b(?:msc|phd)\b.*\bscholarship\b", re.I),
    re.compile(r"\bמלגה.*(?:תקופה|חודשים|ממוצע)\b", re.I),
    # Re-admission
    re.compile(r"\b(re-?admission|return after|come back)\b.*\b(academic|standing|years?)\b", re.I),
    re.compile(r"\bחזרה ללימודים|חזור ללמוד\b", re.I),
)

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

_DUAL_DEGREE_PATTERNS = (
    re.compile(r"\bdual[-\s]degree\b", re.I),
    re.compile(r"\b(second degree|additional degree|both degrees|two degrees)\b", re.I),
    re.compile(r"\badd a second degree\b", re.I),
    re.compile(r"\bcomplete both degrees\b", re.I),
    re.compile(r"\btואר כפול|תואר נוסף\b", re.I),
)

_REGULATION_MOED_PATTERNS = (
    re.compile(r"\bmoed\s+a\b", re.I),
    re.compile(r"\bmoed\s+b\b", re.I),
    re.compile(r"\bfinal grade\b", re.I),
    re.compile(r"(מועד\s*א|מועד\s*ב)", re.I),
)

_REGULATION_STANDING_PATTERNS = (
    re.compile(r"\bnon[- ]regular academic standing\b", re.I),
    re.compile(r"\bcomplete list\b.*\bconditions?\b", re.I),
    re.compile(r"\ball the conditions\b", re.I),
    re.compile(r"\bמצב אקדמי לא תקין\b", re.I),
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

    if _matches_any(_PROGRAM_MINOR_PATTERNS, lowered):
        return IntentClassification(
            intent="program_minor_lookup",
            confidence=0.92,
            required_context=["catalog_wiki"],
        )

    if _matches_any(_REGULATION_LOOKUP_PATTERNS, lowered) or _matches_any(_DUAL_DEGREE_PATTERNS, lowered):
        return IntentClassification(
            intent="regulation_lookup",
            confidence=0.9,
            required_context=["catalog_wiki"],
        )

    if _matches_any(_REGULATION_STANDING_PATTERNS, lowered) or _matches_any(_REGULATION_MOED_PATTERNS, lowered):
        return IntentClassification(
            intent="regulation_lookup",
            confidence=0.9,
            required_context=["catalog_wiki"],
        )

    if _matches_any(_TRACK_STRUCTURE_PATTERNS, lowered):
        return IntentClassification(
            intent="track_structure_lookup",
            confidence=0.9,
            required_context=["catalog_wiki"],
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
