"""Validation for Technion staged course records (Phase 9)."""

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models.staging_course import StagedTechnionCourse, StagedTechnionCourseOffering
from app.sources.technion_course_json import SEMESTER_CODE_LABELS

COURSE_NUMBER_PATTERN = re.compile(r"^0\d{7}$")
MAX_CREDITS = 30.0


@dataclass(frozen=True)
class StagingCourseValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_staged_technion_course(course: StagedTechnionCourse) -> StagingCourseValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(course.warnings)

    if not COURSE_NUMBER_PATTERN.fullmatch(course.courseNumber):
        errors.append("courseNumber must be 8 digits starting with 0")
    if not course.sourceFiles:
        errors.append("sourceFiles must not be empty")
    if course.credits is not None and (course.credits < 0 or course.credits > MAX_CREDITS):
        errors.append(f"credits must be between 0 and {MAX_CREDITS}")
    if course.faculty is not None and not isinstance(course.faculty, str):
        errors.append("faculty must be a string when present")
    if not course.titleHebrew:
        warnings.append(f"{course.courseNumber}: titleHebrew missing")
    for semester in course.semestersOffered:
        if semester not in SEMESTER_CODE_LABELS:
            errors.append(f"invalid semesterCode in semestersOffered: {semester}")
    if course.productionEligible is not False:
        errors.append("productionEligible must be false for staging import")
    if course.isStaging is not True:
        errors.append("isStaging must be true for staging import")

    try:
        StagedTechnionCourse.model_validate(course.model_dump())
    except ValidationError as exc:
        errors.extend(error.get("msg", "validation failed") for error in exc.errors())

    return StagingCourseValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
    )


def validate_staged_technion_offering(
    offering: StagedTechnionCourseOffering,
) -> StagingCourseValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(offering.warnings)

    if offering.semesterCode not in SEMESTER_CODE_LABELS:
        errors.append(f"semesterCode must be one of {sorted(SEMESTER_CODE_LABELS)}")
    if not COURSE_NUMBER_PATTERN.fullmatch(offering.courseNumber):
        errors.append("courseNumber must be 8 digits starting with 0")
    if offering.productionEligible is not False:
        errors.append("productionEligible must be false")
    if offering.isStaging is not True:
        errors.append("isStaging must be true")
    if not isinstance(offering.scheduleGroups, list):
        errors.append("scheduleGroups must be a list")

    try:
        StagedTechnionCourseOffering.model_validate(offering.model_dump())
    except ValidationError as exc:
        errors.extend(error.get("msg", "validation failed") for error in exc.errors())

    return StagingCourseValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
    )
