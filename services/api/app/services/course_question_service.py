"""Deterministic course-question analysis for the UniPilot Agent (spec §30.2)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import AgentContextPack

QuestionFocus = Literal["eligibility", "offering", "contribution", "prerequisites", "general"]
Verdict = Literal["yes", "no", "maybe", "unknown"]


class CourseQuestionAnalysis(BaseModel):
    focus: QuestionFocus = "general"
    verdict: Verdict = "unknown"
    headline: str = ""
    course_number: str | None = None
    target_semester: str | None = None
    warnings: list[str] = Field(default_factory=list)
    recommendation: str | None = None


_OFFERING_PATTERNS = (
    re.compile(r"\b(offered|offer|availability|available)\b", re.I),
    re.compile(r"(מוצע|נפתח|קיים בסמסטר)", re.I),
)

_CONTRIBUTION_PATTERNS = (
    re.compile(r"\b(count|counts|count toward|fulfill|satisfy).*(requirement|track|degree)\b", re.I),
    re.compile(r"(סופר|נספר|דרישה|מסלול)", re.I),
)

_PREREQ_PATTERNS = (
    re.compile(r"\b(prerequisite|prereq|missing prerequisite)\b", re.I),
    re.compile(r"(דרישות קדם|קדם)", re.I),
)

_ELIGIBILITY_PATTERNS = (
    re.compile(r"\b(can i take|am i allowed|eligible)\b", re.I),
    re.compile(r"(אפשר לקחת|זכאי)", re.I),
)


def classify_question_focus(message: str) -> QuestionFocus:
    text = (message or "").strip()
    if not text:
        return "general"
    if any(pattern.search(text) for pattern in _PREREQ_PATTERNS):
        return "prerequisites"
    if any(pattern.search(text) for pattern in _OFFERING_PATTERNS):
        return "offering"
    if any(pattern.search(text) for pattern in _CONTRIBUTION_PATTERNS):
        return "contribution"
    if any(pattern.search(text) for pattern in _ELIGIBILITY_PATTERNS):
        return "eligibility"
    return "general"


def analyze_course_question(
    *,
    context: AgentContextPack,
    user_message: str,
) -> CourseQuestionAnalysis:
    focus = classify_question_focus(user_message)
    if context.intent == "prerequisite_check":
        focus = "prerequisites"

    course_number = str(context.entities.get("courseNumber") or "").strip() or None
    target_semester = (
        str(context.entities.get("targetSemesterCode") or context.entities.get("targetSemester") or "").strip()
        or None
    )
    warnings = list(context.validation.warnings)
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

    if course is None:
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
    if focus == "prerequisites":
        return _analyze_prerequisites(
            course_number=course_number,
            prereq=prereq,
            warnings=warnings,
        )

    return _analyze_eligibility(
        course_number=course_number,
        target_semester=target_semester,
        prereq=prereq,
        offering=offering,
        contribution=contribution,
        warnings=warnings,
    )


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


def _analyze_prerequisites(
    *,
    course_number: str,
    prereq: dict[str, Any],
    warnings: list[str],
) -> CourseQuestionAnalysis:
    if not prereq:
        return CourseQuestionAnalysis(
            focus="prerequisites",
            verdict="maybe",
            headline=f"Prerequisite data is unavailable for course {course_number}.",
            course_number=course_number,
            warnings=[*warnings, "prerequisite_data_unavailable"],
        )

    if prereq.get("eligible"):
        return CourseQuestionAnalysis(
            focus="prerequisites",
            verdict="yes",
            headline=f"Your prerequisites for course {course_number} are satisfied.",
            course_number=course_number,
            warnings=warnings,
        )

    missing = prereq.get("missingPrerequisites") or []
    labels = [
        str(item.get("courseNumber") or item.get("courseTitle") or item.get("courseId") or "")
        for item in missing
        if isinstance(item, dict)
    ]
    labels = [label for label in labels if label]
    detail = f" Missing: {', '.join(labels)}." if labels else ""
    return CourseQuestionAnalysis(
        focus="prerequisites",
        verdict="no",
        headline=f"You are missing prerequisites for course {course_number}.{detail}",
        course_number=course_number,
        warnings=warnings,
        recommendation="Complete the missing prerequisite courses before registering for this course.",
    )


def _analyze_eligibility(
    *,
    course_number: str,
    target_semester: str | None,
    prereq: dict[str, Any],
    offering: dict[str, Any] | None,
    contribution: dict[str, Any],
    warnings: list[str],
) -> CourseQuestionAnalysis:
    prereq_ok = bool(prereq.get("eligible")) if prereq else None
    offering_ok = offering is not None if target_semester else None

    if prereq_ok is False:
        missing = prereq.get("missingPrerequisites") or []
        labels = [
            str(item.get("courseNumber") or item.get("courseTitle") or "")
            for item in missing
            if isinstance(item, dict)
        ]
        labels = [label for label in labels if label]
        detail = f" Missing prerequisites: {', '.join(labels)}." if labels else ""
        return CourseQuestionAnalysis(
            focus="eligibility",
            verdict="no",
            headline=f"No — you cannot take course {course_number} yet.{detail}",
            course_number=course_number,
            target_semester=target_semester,
            warnings=warnings,
            recommendation="Complete prerequisites first, then ask again about this course.",
        )

    if target_semester and offering_ok is False:
        return CourseQuestionAnalysis(
            focus="eligibility",
            verdict="no",
            headline=f"Course {course_number} does not appear to be offered in {target_semester}.",
            course_number=course_number,
            target_semester=target_semester,
            warnings=warnings,
        )

    if prereq_ok and (offering_ok is True or offering_ok is None):
        extra = ""
        if contribution.get("countsTowardDegree") and contribution.get("summary"):
            extra = f" {contribution['summary']}"
        return CourseQuestionAnalysis(
            focus="eligibility",
            verdict="yes",
            headline=f"Yes — you appear eligible to take course {course_number}.{extra}",
            course_number=course_number,
            target_semester=target_semester,
            warnings=warnings,
            recommendation="Confirm the exact group schedule before final registration.",
        )

    return CourseQuestionAnalysis(
        focus="eligibility",
        verdict="maybe",
        headline=f"Maybe — course {course_number} may be possible, but I need more confirmation.",
        course_number=course_number,
        target_semester=target_semester,
        warnings=[*warnings, "eligibility_needs_review"],
        recommendation="Specify the target semester or ask about prerequisites separately.",
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
