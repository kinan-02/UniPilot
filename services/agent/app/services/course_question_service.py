"""Deterministic course-question analysis for the UniPilot Agent (spec §30.2)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import AgentContextPack
from app.services.academic_lookup_service import (
    classify_course_question_focus,
    try_compose_deterministic_answer,
)
from app.services.prerequisite_validation_service import (
    PrerequisiteValidationResult,
    compose_eligibility_answer,
    extract_completed_course_codes_from_context,
    validate_course_prerequisites,
)

QuestionFocus = Literal[
    "eligibility",
    "offering",
    "contribution",
    "prerequisites",
    "catalog_prerequisites",
    "tracks_requiring",
    "compound_catalog",
    "general",
]
Verdict = Literal["yes", "no", "maybe", "unknown"]


class CourseQuestionAnalysis(BaseModel):
    focus: QuestionFocus = "general"
    verdict: Verdict = "unknown"
    headline: str = ""
    course_number: str | None = None
    target_semester: str | None = None
    warnings: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    catalog_answer: str | None = None
    catalog_sources: list[str] = Field(default_factory=list)
    use_catalog_answer: bool = False
    prerequisite_validation: PrerequisiteValidationResult | None = None
    eligibility_answer: str | None = None
    use_eligibility_validation: bool = False


_OFFERING_PATTERNS = (
    re.compile(r"\b(offered|offer|availability|available)\b", re.I),
    re.compile(r"(מוצע|נפתח|קיים בסמסטר)", re.I),
)

_CONTRIBUTION_PATTERNS = (
    re.compile(r"\b(count|counts|count toward|fulfill|satisfy).*(requirement|track|degree)\b", re.I),
    re.compile(r"(סופר|נספר|דרישה|מסלול)", re.I),
)

_STUDENT_PREREQ_PATTERNS = (
    re.compile(r"\bmissing prerequisites?\b", re.I),
    re.compile(r"\bmissing\b.*\bprerequisites?\b", re.I),
    re.compile(r"\bprerequisites?\b.*\bmissing\b", re.I),
    re.compile(r"\bdo i have\b.*\bprerequisites?\b", re.I),
    re.compile(r"(חסרות לי|חסר לי).*(דרישות קדם|קדם)", re.I),
)

_ELIGIBILITY_PATTERNS = (
    re.compile(r"\b(can i take|am i allowed|eligible)\b", re.I),
    re.compile(r"(אפשר לקחת|זכאי)", re.I),
)


def classify_question_focus(message: str) -> QuestionFocus:
    text = (message or "").strip()
    if not text:
        return "general"
    if any(pattern.search(text) for pattern in _STUDENT_PREREQ_PATTERNS):
        return "prerequisites"
    if any(pattern.search(text) for pattern in _ELIGIBILITY_PATTERNS):
        return "eligibility"

    catalog_focus = classify_course_question_focus(message)
    if catalog_focus in {"compound_catalog", "tracks_requiring", "catalog_prerequisites"}:
        return catalog_focus  # type: ignore[return-value]

    if any(pattern.search(text) for pattern in _OFFERING_PATTERNS):
        return "offering"
    if any(pattern.search(text) for pattern in _CONTRIBUTION_PATTERNS):
        return "contribution"
    return "general"


def analyze_course_question(
    *,
    context: AgentContextPack,
    user_message: str,
) -> CourseQuestionAnalysis:
    focus = classify_question_focus(user_message)
    if context.intent == "prerequisite_check" and focus == "general":
        focus = "catalog_prerequisites"

    course_number = str(context.entities.get("courseNumber") or "").strip() or None
    target_semester = (
        str(context.entities.get("targetSemesterCode") or context.entities.get("targetSemester") or "").strip()
        or None
    )
    warnings = list(context.validation.warnings)

    deterministic = try_compose_deterministic_answer(user_message, entities=context.entities)
    if deterministic and focus in {"catalog_prerequisites", "tracks_requiring", "compound_catalog"}:
        text, sources = deterministic
        return CourseQuestionAnalysis(
            focus=focus,
            verdict="yes",
            headline=text,
            course_number=course_number,
            target_semester=target_semester,
            warnings=warnings,
            catalog_answer=text,
            catalog_sources=sources,
            use_catalog_answer=True,
        )

    academic = context.academic_context
    course = academic.get("course")
    offering = academic.get("offering")
    prereq = academic.get("prerequisiteResult") or {}
    contribution = academic.get("requirementContribution") or {}

    if not course_number:
        return CourseQuestionAnalysis(
            focus=focus,
            verdict="unknown",
            headline="I need a course number to answer this question.",
            warnings=[*warnings, "course_number_missing"],
        )

    if course is None and focus not in {"catalog_prerequisites", "tracks_requiring", "compound_catalog"}:
        if deterministic:
            text, sources = deterministic
            return CourseQuestionAnalysis(
                focus=focus,
                verdict="yes",
                headline=text,
                course_number=course_number,
                target_semester=target_semester,
                warnings=warnings,
                catalog_answer=text,
                catalog_sources=sources,
                use_catalog_answer=True,
            )
        return CourseQuestionAnalysis(
            focus=focus,
            verdict="no",
            headline=f"Course {course_number} was not found in the catalog.",
            course_number=course_number,
            target_semester=target_semester,
            warnings=[*warnings, "course_not_in_catalog"],
            recommendation="Verify the course number or search the catalog for the correct code.",
        )

    if focus == "offering":
        return _analyze_offering(
            course_number=course_number,
            target_semester=target_semester,
            offering=offering,
            warnings=warnings,
        )
    if focus == "contribution":
        return _analyze_contribution(
            course_number=course_number,
            contribution=contribution,
            warnings=warnings,
        )
    if focus == "catalog_prerequisites":
        if deterministic:
            text, sources = deterministic
            return CourseQuestionAnalysis(
                focus=focus,
                verdict="yes",
                headline=text,
                course_number=course_number,
                warnings=warnings,
                catalog_answer=text,
                catalog_sources=sources,
                use_catalog_answer=True,
            )
        return _analyze_catalog_prerequisites_fallback(
            course_number=course_number,
            prereq=prereq,
            warnings=warnings,
        )
    if focus in {"tracks_requiring", "compound_catalog"}:
        if deterministic:
            text, sources = deterministic
            return CourseQuestionAnalysis(
                focus=focus,
                verdict="yes",
                headline=text,
                course_number=course_number,
                warnings=warnings,
                catalog_answer=text,
                catalog_sources=sources,
                use_catalog_answer=True,
            )
        return CourseQuestionAnalysis(
            focus=focus,
            verdict="maybe",
            headline=f"I could not load track requirement data for course {course_number}.",
            course_number=course_number,
            warnings=[*warnings, "tracks_requiring_data_unavailable"],
        )
    if focus == "prerequisites":
        return _analyze_student_prerequisites(
            course_number=course_number,
            warnings=warnings,
            context=context,
        )

    return _analyze_eligibility(
        course_number=course_number,
        target_semester=target_semester,
        prereq=prereq,
        offering=offering,
        contribution=contribution,
        warnings=warnings,
        context=context,
    )


def step_label_for_focus(focus: QuestionFocus) -> str:
    labels = {
        "catalog_prerequisites": "Looking up course prerequisites",
        "tracks_requiring": "Looking up required tracks",
        "compound_catalog": "Looking up course catalog details",
        "offering": "Checking course offering",
        "contribution": "Checking degree contribution",
        "prerequisites": "Checking prerequisite status",
        "eligibility": "Analyzing course eligibility",
        "general": "Answering course question",
    }
    return labels.get(focus, "Answering course question")


def _analyze_offering(
    *,
    course_number: str,
    target_semester: str | None,
    offering: dict[str, Any] | None,
    warnings: list[str],
) -> CourseQuestionAnalysis:
    if offering:
        semester_label = target_semester or _format_offering_semester(offering)
        return CourseQuestionAnalysis(
            focus="offering",
            verdict="yes",
            headline=f"Yes — course {course_number} is offered{f' in {semester_label}' if semester_label else ''}.",
            course_number=course_number,
            target_semester=target_semester,
            warnings=warnings,
            recommendation="You can review lecture and tutorial groups before adding this course to a plan.",
        )

    if target_semester:
        return CourseQuestionAnalysis(
            focus="offering",
            verdict="no",
            headline=f"No — I could not find an offering for course {course_number} in {target_semester}.",
            course_number=course_number,
            target_semester=target_semester,
            warnings=[*warnings, "offering_not_found"],
            recommendation="Try another semester or check the official course catalog schedule.",
        )

    return CourseQuestionAnalysis(
        focus="offering",
        verdict="maybe",
        headline=f"I could not confirm a specific semester offering for course {course_number}.",
        course_number=course_number,
        warnings=[*warnings, "semester_not_specified"],
        recommendation="Tell me which semester you mean, for example next semester or 2025-2.",
    )


def _analyze_contribution(
    *,
    course_number: str,
    contribution: dict[str, Any],
    warnings: list[str],
) -> CourseQuestionAnalysis:
    if contribution.get("countsTowardDegree"):
        return CourseQuestionAnalysis(
            focus="contribution",
            verdict="yes",
            headline=str(contribution.get("summary") or f"Yes — course {course_number} can count toward your degree."),
            course_number=course_number,
            warnings=warnings,
            recommendation="This is based on catalog requirement pools for your selected program.",
        )
    return CourseQuestionAnalysis(
        focus="contribution",
        verdict="no",
        headline=str(
            contribution.get("summary")
            or f"I could not match course {course_number} to a requirement bucket for your program."
        ),
        course_number=course_number,
        warnings=[*warnings, "no_requirement_match"],
        recommendation="The course may still be allowed as a free elective depending on your track rules.",
    )


def _analyze_catalog_prerequisites_fallback(
    *,
    course_number: str,
    prereq: dict[str, Any],
    warnings: list[str],
) -> CourseQuestionAnalysis:
    if not prereq:
        return CourseQuestionAnalysis(
            focus="catalog_prerequisites",
            verdict="maybe",
            headline=f"Prerequisite data is unavailable for course {course_number}.",
            course_number=course_number,
            warnings=[*warnings, "prerequisite_data_unavailable"],
        )

    missing = prereq.get("missingPrerequisites") or []
    if prereq.get("eligible") and not missing:
        return CourseQuestionAnalysis(
            focus="catalog_prerequisites",
            verdict="yes",
            headline=f"Course {course_number} has no unsatisfied catalog prerequisites on file.",
            course_number=course_number,
            warnings=warnings,
        )

    labels = [
        str(item.get("courseNumber") or item.get("courseTitle") or item.get("courseId") or "")
        for item in missing
        if isinstance(item, dict)
    ]
    labels = [label for label in labels if label]
    if labels:
        return CourseQuestionAnalysis(
            focus="catalog_prerequisites",
            verdict="yes",
            headline=f"Prerequisites for course {course_number}: {', '.join(labels)}.",
            course_number=course_number,
            warnings=warnings,
        )

    return CourseQuestionAnalysis(
        focus="catalog_prerequisites",
        verdict="maybe",
        headline=f"Prerequisite data is unavailable for course {course_number}.",
        course_number=course_number,
        warnings=[*warnings, "prerequisite_data_unavailable"],
    )


def _analyze_student_prerequisites(
    *,
    course_number: str,
    warnings: list[str],
    context: AgentContextPack,
) -> CourseQuestionAnalysis:
    completed_codes, data_available = extract_completed_course_codes_from_context(
        user_context=context.user_context,
    )
    validation = validate_course_prerequisites(
        course_number,
        completed_course_codes=completed_codes,
        completed_data_available=data_available,
    )
    headline, verdict = compose_eligibility_answer(validation)
    recommendation = None
    if validation.eligibility_status == "not_eligible":
        recommendation = "Complete the missing prerequisite courses before registering for this course."
    elif validation.eligibility_status == "unknown":
        recommendation = "Upload or enter your completed courses so I can verify prerequisites."

    return CourseQuestionAnalysis(
        focus="prerequisites",
        verdict=verdict,
        headline=headline,
        course_number=course_number,
        warnings=warnings,
        recommendation=recommendation,
        prerequisite_validation=validation,
        eligibility_answer=headline,
        use_eligibility_validation=True,
    )


def _analyze_eligibility(
    *,
    course_number: str,
    target_semester: str | None,
    prereq: dict[str, Any],
    offering: dict[str, Any] | None,
    contribution: dict[str, Any],
    warnings: list[str],
    context: AgentContextPack,
) -> CourseQuestionAnalysis:
    completed_codes, data_available = extract_completed_course_codes_from_context(
        user_context=context.user_context,
    )
    validation = validate_course_prerequisites(
        course_number,
        completed_course_codes=completed_codes,
        completed_data_available=data_available,
    )
    offering_unavailable = bool(target_semester and offering is None)
    contribution_summary = (
        str(contribution.get("summary"))
        if contribution.get("countsTowardDegree") and contribution.get("summary")
        else None
    )
    headline, verdict = compose_eligibility_answer(
        validation,
        target_semester=target_semester,
        offering_unavailable=offering_unavailable,
        contribution_summary=contribution_summary,
    )
    recommendation = None
    if verdict == "yes":
        recommendation = "Confirm the exact group schedule before final registration."
    elif verdict == "no":
        recommendation = "Complete prerequisites first, then ask again about this course."
    elif verdict == "unknown":
        recommendation = "Upload or enter your completed courses so I can verify prerequisites."

    return CourseQuestionAnalysis(
        focus="eligibility",
        verdict=verdict,
        headline=headline,
        course_number=course_number,
        target_semester=target_semester,
        warnings=warnings,
        recommendation=recommendation,
        prerequisite_validation=validation,
        eligibility_answer=headline,
        use_eligibility_validation=True,
    )


def _format_offering_semester(offering: dict[str, Any]) -> str | None:
    academic_year = offering.get("academicYear")
    semester_code = offering.get("semesterCode")
    if academic_year and semester_code:
        from app.planning.semester_codes import offering_keys_to_plan_semester_code

        plan_code = offering_keys_to_plan_semester_code(int(academic_year), int(semester_code))
        if plan_code:
            return plan_code
    return None
