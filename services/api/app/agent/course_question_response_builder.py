"""Structured UI blocks for course question responses (Agent_UI_UX.md §17–19)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentContextPack, StructuredBlock
from app.services.course_question_service import CourseQuestionAnalysis


def build_course_question_blocks(
    *,
    context: AgentContextPack,
    analysis: CourseQuestionAnalysis,
) -> list[StructuredBlock]:
    academic = context.academic_context
    course = academic.get("course") or {}
    offering = academic.get("offering")
    prereq = academic.get("prerequisiteResult") or {}
    contribution = academic.get("requirementContribution") or {}

    blocks: list[StructuredBlock] = [
        _course_recommendation_block(
            course=course,
            analysis=analysis,
            offering=offering,
            prereq=prereq,
            contribution=contribution,
        ),
        _prerequisite_status_block(course=course, prereq=prereq),
        _offering_status_block(
            offering=offering,
            target_semester=analysis.target_semester,
            course_number=analysis.course_number,
        ),
        _source_summary_block(context=context, analysis=analysis),
    ]

    for warning in analysis.warnings[:4]:
        blocks.append(StructuredBlock(type="WarningBlock", data={"message": warning}))

    return [block for block in blocks if block is not None]


def build_course_question_text(*, analysis: CourseQuestionAnalysis) -> str:
    parts = [analysis.headline]
    if analysis.recommendation:
        parts.append(analysis.recommendation)
    return " ".join(parts)


def build_course_question_followups(*, analysis: CourseQuestionAnalysis) -> list[str]:
    course = analysis.course_number or "this course"
    if analysis.focus == "offering":
        return [
            f"What prerequisites do I need for {course}?",
            f"Add {course} to my semester plan",
        ]
    if analysis.focus == "contribution":
        return [
            "What am I missing to graduate?",
            f"Can I take {course} next semester?",
        ]
    if analysis.verdict == "no":
        return [
            f"What prerequisites am I missing for {course}?",
            "Suggest alternative courses",
        ]
    return [
        f"Is {course} offered next semester?",
        f"Does {course} count toward my track?",
    ]


def _course_recommendation_block(
    *,
    course: dict[str, Any],
    analysis: CourseQuestionAnalysis,
    offering: dict[str, Any] | None,
    prereq: dict[str, Any],
    contribution: dict[str, Any],
) -> StructuredBlock:
    return StructuredBlock(
        type="CourseRecommendationBlock",
        data={
            "courseNumber": course.get("courseNumber") or analysis.course_number,
            "courseName": course.get("title") or course.get("titleHebrew"),
            "credits": course.get("credits"),
            "verdict": analysis.verdict,
            "focus": analysis.focus,
            "headline": analysis.headline,
            "semesterAvailability": _offering_label(offering, analysis.target_semester),
            "requirementContribution": contribution.get("summary"),
            "countsTowardDegree": contribution.get("countsTowardDegree"),
            "prerequisiteStatus": _prerequisite_label(prereq),
            "recommendationReason": analysis.recommendation,
            "faculty": course.get("faculty"),
        },
    )


def _prerequisite_status_block(
    *,
    course: dict[str, Any],
    prereq: dict[str, Any],
) -> StructuredBlock:
    if not prereq:
        status = "unknown"
    elif prereq.get("eligible"):
        status = "satisfied"
    elif prereq.get("missingPrerequisites"):
        status = "missing"
    else:
        status = "needs_review"

    return StructuredBlock(
        type="PrerequisiteStatusBlock",
        data={
            "courseNumber": course.get("courseNumber"),
            "courseName": course.get("title") or course.get("titleHebrew"),
            "status": status,
            "satisfiedPrerequisites": [],
            "missingPrerequisites": prereq.get("missingPrerequisites") or [],
            "reason": prereq.get("reason"),
            "notes": prereq.get("reason"),
        },
    )


def _offering_status_block(
    *,
    offering: dict[str, Any] | None,
    target_semester: str | None,
    course_number: str | None,
) -> StructuredBlock:
    groups = (offering or {}).get("scheduleGroups") or []
    lecture_count = sum(1 for group in groups if str(group.get("type") or "").lower() == "lecture")
    tutorial_count = sum(1 for group in groups if str(group.get("type") or "").lower() == "tutorial")
    lab_count = sum(1 for group in groups if str(group.get("type") or "").lower() == "lab")

    return StructuredBlock(
        type="OfferingStatusBlock",
        data={
            "courseNumber": course_number,
            "semester": target_semester or _offering_label(offering, None),
            "isOffered": offering is not None,
            "lectureGroupCount": lecture_count,
            "tutorialGroupCount": tutorial_count,
            "labGroupCount": lab_count,
            "examDates": (offering or {}).get("examDates") or {},
            "instructors": (offering or {}).get("instructors"),
            "notes": None if offering else "No offering record found for the requested semester.",
        },
    )


def _source_summary_block(
    *,
    context: AgentContextPack,
    analysis: CourseQuestionAnalysis,
) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "provenance": context.provenance,
            "wikiSnippetCount": len(context.retrieved_wiki_context),
            "validationStatus": context.validation.status,
            "questionFocus": analysis.focus,
            "usedSources": list(context.provenance) if context.provenance else [
                "mongodb:completed_courses",
                "catalog:course_record",
                "catalog:prerequisites",
            ],
        },
    )


def _prerequisite_label(prereq: dict[str, Any]) -> str:
    if not prereq:
        return "Unknown"
    if prereq.get("eligible"):
        return "Satisfied"
    if prereq.get("missingPrerequisites"):
        return "Missing requirements"
    return "Needs review"


def _offering_label(offering: dict[str, Any] | None, target_semester: str | None) -> str | None:
    if target_semester:
        return target_semester
    if not offering:
        return None
    academic_year = offering.get("academicYear")
    semester_code = offering.get("semesterCode")
    if academic_year and semester_code:
        from app.planning.semester_codes import offering_keys_to_plan_semester_code

        return offering_keys_to_plan_semester_code(int(academic_year), int(semester_code))
    return offering.get("semesterName")
