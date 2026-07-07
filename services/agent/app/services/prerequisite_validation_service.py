"""Deterministic prerequisite validation for personal eligibility answers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.planning.prerequisite_resolver import canonical_course_number
from app.services.academic_lookup_service import course_by_code, course_prerequisites

EligibilityStatus = Literal["eligible", "not_eligible", "unknown"]

ELIGIBILITY_VALIDATION_SOURCE = "Deterministic prerequisite eligibility validation"


class PrerequisiteValidationResult(BaseModel):
    course_code: str
    has_prerequisites: bool
    required_prerequisite_codes: list[str] = Field(default_factory=list)
    completed_course_codes: list[str] = Field(default_factory=list)
    satisfied_prerequisite_codes: list[str] = Field(default_factory=list)
    missing_prerequisite_codes: list[str] = Field(default_factory=list)
    eligibility_status: EligibilityStatus
    reason: str
    source_paths: list[str] = Field(default_factory=list)
    completed_data_available: bool = True


def extract_completed_course_codes_from_context(
    *,
    user_context: dict[str, Any] | None,
) -> tuple[list[str], bool]:
    """Return canonical completed course numbers and whether transcript data was loaded."""
    ctx = user_context or {}
    if "completedCourses" in ctx:
        numbers = [
            canonical_course_number(str(item))
            for item in (ctx.get("completedCourses") or [])
            if str(item).strip()
        ]
        return [item for item in numbers if item], True

    if "completedCourseRecords" in ctx or "completedCourseIds" in ctx:
        # Completed-course query ran but only IDs/records are present without numbers.
        return [], True

    return [], False


def validate_course_prerequisites(
    course_code: str,
    *,
    completed_course_codes: list[str],
    completed_data_available: bool,
) -> PrerequisiteValidationResult:
    """Compare wiki/catalog prerequisites against the student's completed courses."""
    normalized_course = canonical_course_number(course_code)
    wiki_record = course_by_code(normalized_course) if normalized_course else None

    required_codes: list[str] = []
    source_paths: list[str] = []
    if wiki_record:
        source_path = str(wiki_record.get("sourcePath") or "").strip()
        if source_path:
            source_paths.append(source_path)
        for item in wiki_record.get("prerequisites") or course_prerequisites(normalized_course):
            code = canonical_course_number(str(item.get("courseNumber") or ""))
            if code and code not in required_codes:
                required_codes.append(code)

    completed_set = {
        canonical_course_number(code)
        for code in completed_course_codes
        if canonical_course_number(code)
    }
    satisfied = [code for code in required_codes if code in completed_set]
    missing = [code for code in required_codes if code not in completed_set]

    if not completed_data_available:
        return PrerequisiteValidationResult(
            course_code=normalized_course,
            has_prerequisites=bool(required_codes),
            required_prerequisite_codes=required_codes,
            completed_course_codes=sorted(completed_set),
            satisfied_prerequisite_codes=satisfied,
            missing_prerequisite_codes=missing,
            eligibility_status="unknown",
            reason=(
                "Cannot confirm eligibility because completed-course data is unavailable."
            ),
            source_paths=source_paths,
            completed_data_available=False,
        )

    if wiki_record is None:
        return PrerequisiteValidationResult(
            course_code=normalized_course,
            has_prerequisites=True,
            required_prerequisite_codes=[],
            completed_course_codes=sorted(completed_set),
            satisfied_prerequisite_codes=[],
            missing_prerequisite_codes=[],
            eligibility_status="unknown",
            reason="Cannot confirm eligibility because prerequisite catalog data is unavailable.",
            source_paths=source_paths,
            completed_data_available=completed_data_available,
        )

    if not required_codes:
        return PrerequisiteValidationResult(
            course_code=normalized_course,
            has_prerequisites=False,
            required_prerequisite_codes=[],
            completed_course_codes=sorted(completed_set),
            satisfied_prerequisite_codes=[],
            missing_prerequisite_codes=[],
            eligibility_status="eligible",
            reason="This course has no listed prerequisites.",
            source_paths=source_paths,
            completed_data_available=True,
        )

    if missing:
        return PrerequisiteValidationResult(
            course_code=normalized_course,
            has_prerequisites=True,
            required_prerequisite_codes=required_codes,
            completed_course_codes=sorted(completed_set),
            satisfied_prerequisite_codes=satisfied,
            missing_prerequisite_codes=missing,
            eligibility_status="not_eligible",
            reason=f"Missing {len(missing)} prerequisite(s) in your completed-course record.",
            source_paths=source_paths,
            completed_data_available=True,
        )

    return PrerequisiteValidationResult(
        course_code=normalized_course,
        has_prerequisites=True,
        required_prerequisite_codes=required_codes,
        completed_course_codes=sorted(completed_set),
        satisfied_prerequisite_codes=satisfied,
        missing_prerequisite_codes=[],
        eligibility_status="eligible",
        reason="All listed prerequisites appear in your completed-course record.",
        source_paths=source_paths,
        completed_data_available=True,
    )


def compose_eligibility_answer(
    validation: PrerequisiteValidationResult,
    *,
    target_semester: str | None = None,
    offering_unavailable: bool = False,
    contribution_summary: str | None = None,
) -> tuple[str, Literal["yes", "no", "maybe", "unknown"]]:
    """Build deterministic eligibility headline and verdict."""
    course = validation.course_code
    if offering_unavailable and target_semester:
        return (
            f"Course {course} does not appear to be offered in {target_semester}.",
            "no",
        )

    if validation.eligibility_status == "unknown":
        prereq_list = ", ".join(validation.required_prerequisite_codes)
        detail = f" Required prerequisites: {prereq_list}." if prereq_list else ""
        follow_up = (
            " Upload or enter completed courses to verify prerequisites."
            if not validation.completed_data_available
            else ""
        )
        return (f"{validation.reason}{detail}{follow_up}", "unknown")

    if validation.eligibility_status == "not_eligible":
        missing = ", ".join(validation.missing_prerequisite_codes)
        satisfied = ", ".join(validation.satisfied_prerequisite_codes)
        parts = [
            f"No — you do not appear eligible for course {course} yet.",
        ]
        if missing:
            parts.append(f"Missing prerequisites: {missing}.")
        if satisfied:
            parts.append(f"Completed prerequisites: {satisfied}.")
        return (" ".join(parts), "no")

    extra = ""
    if contribution_summary:
        extra = f" {contribution_summary}"
    semester_note = ""
    if target_semester:
        semester_note = f" for {target_semester}"
    return (
        f"Yes — you appear eligible to take course {course}{semester_note}.{extra} "
        "Final registration may still depend on official schedule and capacity rules.",
        "yes",
    )


def validation_to_prerequisite_result(validation: PrerequisiteValidationResult) -> dict[str, Any]:
    """Shape for structured PrerequisiteStatusBlock compatibility."""
    missing_prerequisites = [
        {"courseNumber": code, "courseId": code}
        for code in validation.missing_prerequisite_codes
    ]
    return {
        "eligible": validation.eligibility_status == "eligible",
        "missingPrerequisites": missing_prerequisites,
        "missingPrerequisiteIds": list(validation.missing_prerequisite_codes),
        "satisfiedPrerequisiteIds": list(validation.satisfied_prerequisite_codes),
        "reason": validation.reason,
        "eligibilityStatus": validation.eligibility_status,
        "requiredPrerequisiteCodes": list(validation.required_prerequisite_codes),
        "completedCourseCodes": list(validation.completed_course_codes),
        "sourcePaths": list(validation.source_paths),
    }
