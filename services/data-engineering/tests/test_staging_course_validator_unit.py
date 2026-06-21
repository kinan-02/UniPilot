"""Unit tests for app/validators/staging_course_validator.py (69% → ~100%)."""

from __future__ import annotations

import pytest

from app.validators.staging_course_validator import (
    StagingCourseValidationResult,
    validate_staged_technion_course,
    validate_staged_technion_offering,
)
from app.models.staging_course import StagedTechnionCourse, StagedTechnionCourseOffering


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_course(**overrides) -> StagedTechnionCourse:
    defaults = dict(
        stagingKey="technion:course:01234567",
        courseNumber="01234567",
        titleHebrew="מבוא לתכנות",
        sourceFiles=["courses_2025_200.json"],
        semestersOffered=[200],
        isStaging=True,
        productionEligible=False,
        sourceName="technion-course-json",
        sourceType="technion_semester_offerings",
    )
    defaults.update(overrides)
    return StagedTechnionCourse(**defaults)


def _make_offering(**overrides) -> StagedTechnionCourseOffering:
    defaults = dict(
        stagingKey="technion:course-offering:01234567:2025:200",
        courseNumber="01234567",
        academicYear=2025,
        semesterCode=200,
        semesterName="winter",
        sourceFile="courses_2025_200.json",
        isStaging=True,
        productionEligible=False,
    )
    defaults.update(overrides)
    return StagedTechnionCourseOffering(**defaults)


# ---------------------------------------------------------------------------
# validate_staged_technion_course
# ---------------------------------------------------------------------------

class TestValidateStagedTechnionCourse:
    def test_valid_course_passes(self):
        course = _make_course()
        result = validate_staged_technion_course(course)
        assert result.is_valid

    def test_invalid_course_number_fails(self):
        # Use model_construct to bypass Pydantic validation, then test our validator
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:12345678",
                "courseNumber": "12345678",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("courseNumber" in e for e in result.errors)

    def test_empty_source_files_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": [],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("sourceFiles" in e for e in result.errors)

    def test_negative_credits_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
                "credits": -1.0,
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("credits" in e for e in result.errors)

    def test_excessive_credits_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
                "credits": 35.0,
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("credits" in e for e in result.errors)

    def test_invalid_semester_code_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [999],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("semesterCode" in e for e in result.errors)

    def test_production_eligible_true_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": True,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("productionEligible" in e for e in result.errors)

    def test_is_staging_false_fails(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": False,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert not result.is_valid
        assert any("isStaging" in e for e in result.errors)

    def test_missing_title_generates_warning(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": None,
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": [],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert result.is_valid
        assert any("titleHebrew" in w for w in result.warnings)

    def test_existing_warnings_propagated(self):
        raw = StagedTechnionCourse.model_construct(
            **{
                "stagingKey": "technion:course:01234567",
                "courseNumber": "01234567",
                "titleHebrew": "test",
                "sourceFiles": ["f.json"],
                "semestersOffered": [],
                "isStaging": True,
                "productionEligible": False,
                "sourceName": "technion-course-json",
                "sourceType": "technion_semester_offerings",
                "warnings": ["pre-existing warning"],
                "institutionId": "technion",
                "metadata": {},
                "rawFieldKeys": [],
                "offerings": [],
            }
        )
        result = validate_staged_technion_course(raw)
        assert "pre-existing warning" in result.warnings


# ---------------------------------------------------------------------------
# validate_staged_technion_offering
# ---------------------------------------------------------------------------

class TestValidateStagedTechnionOffering:
    def test_valid_offering_passes(self):
        offering = _make_offering()
        result = validate_staged_technion_offering(offering)
        assert result.is_valid

    def test_invalid_semester_code_fails(self):
        raw = StagedTechnionCourseOffering.model_construct(
            **{
                "stagingKey": "technion:course-offering:01234567:2025:999",
                "courseNumber": "01234567",
                "academicYear": 2025,
                "semesterCode": 999,
                "semesterName": "unknown",
                "sourceFile": "f.json",
                "isStaging": True,
                "productionEligible": False,
                "scheduleGroups": [],
                "warnings": [],
            }
        )
        result = validate_staged_technion_offering(raw)
        assert not result.is_valid
        assert any("semesterCode" in e for e in result.errors)

    def test_invalid_course_number_fails(self):
        raw = StagedTechnionCourseOffering.model_construct(
            **{
                "stagingKey": "technion:course-offering:12345678:2025:200",
                "courseNumber": "12345678",
                "academicYear": 2025,
                "semesterCode": 200,
                "semesterName": "winter",
                "sourceFile": "f.json",
                "isStaging": True,
                "productionEligible": False,
                "scheduleGroups": [],
                "warnings": [],
            }
        )
        result = validate_staged_technion_offering(raw)
        assert not result.is_valid
        assert any("courseNumber" in e for e in result.errors)

    def test_production_eligible_true_fails(self):
        raw = StagedTechnionCourseOffering.model_construct(
            **{
                "stagingKey": "x",
                "courseNumber": "01234567",
                "academicYear": 2025,
                "semesterCode": 200,
                "semesterName": "winter",
                "sourceFile": "f.json",
                "isStaging": True,
                "productionEligible": True,
                "scheduleGroups": [],
                "warnings": [],
            }
        )
        result = validate_staged_technion_offering(raw)
        assert not result.is_valid
        assert any("productionEligible" in e for e in result.errors)

    def test_is_staging_false_fails(self):
        raw = StagedTechnionCourseOffering.model_construct(
            **{
                "stagingKey": "x",
                "courseNumber": "01234567",
                "academicYear": 2025,
                "semesterCode": 200,
                "semesterName": "winter",
                "sourceFile": "f.json",
                "isStaging": False,
                "productionEligible": False,
                "scheduleGroups": [],
                "warnings": [],
            }
        )
        result = validate_staged_technion_offering(raw)
        assert not result.is_valid
        assert any("isStaging" in e for e in result.errors)

    def test_existing_warnings_propagated(self):
        raw = StagedTechnionCourseOffering.model_construct(
            **{
                "stagingKey": "x",
                "courseNumber": "01234567",
                "academicYear": 2025,
                "semesterCode": 200,
                "semesterName": "winter",
                "sourceFile": "f.json",
                "isStaging": True,
                "productionEligible": False,
                "scheduleGroups": [],
                "warnings": ["pre-existing"],
            }
        )
        result = validate_staged_technion_offering(raw)
        assert "pre-existing" in result.warnings
