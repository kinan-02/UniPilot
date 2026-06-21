"""Behavioral tests for semester plan request schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.semester_plan import (
    CreateManualSemesterPlanRequest,
    GenerateSemesterPlanRequest,
    ManualPlannedCourseInput,
    ManualSemesterInput,
    UpdateSemesterPlanRequest,
    validate_credit_load,
)

VALID_COURSE_ID = "665f2b0f2a3f7b2a1a9a7c01"
VALID_SEMESTER = "2025-1"


def make_planned_course(course_id: str = VALID_COURSE_ID) -> ManualPlannedCourseInput:
    return ManualPlannedCourseInput(courseId=course_id)


def make_valid_manual_semester() -> ManualSemesterInput:
    return ManualSemesterInput(
        semesterCode=VALID_SEMESTER,
        plannedCourses=[make_planned_course()],
    )


class TestValidateCreditLoad:
    def test_valid_credit_accepted(self):
        assert validate_credit_load(3.0) == 3.0

    def test_zero_credits_accepted(self):
        assert validate_credit_load(0.0) == 0.0

    def test_half_credit_accepted(self):
        assert validate_credit_load(1.5) == 1.5

    def test_negative_credits_rejected(self):
        with pytest.raises(ValueError, match="at least 0"):
            validate_credit_load(-1.0)

    def test_credits_above_36_rejected(self):
        with pytest.raises(ValueError, match="at most 36"):
            validate_credit_load(36.5)

    def test_non_half_increment_rejected(self):
        with pytest.raises(ValueError, match="0.5 increments"):
            validate_credit_load(2.3)


class TestGenerateSemesterPlanRequest:
    def test_valid_request_accepted(self):
        req = GenerateSemesterPlanRequest(semesterCode=VALID_SEMESTER)
        assert req.semesterCode == VALID_SEMESTER
        assert req.maxCredits is None
        assert req.minCredits is None

    def test_max_credits_none_explicitly_accepted(self):
        req = GenerateSemesterPlanRequest(
            semesterCode=VALID_SEMESTER,
            maxCredits=None,
        )
        assert req.maxCredits is None

    def test_valid_max_credits_accepted(self):
        req = GenerateSemesterPlanRequest(
            semesterCode=VALID_SEMESTER,
            maxCredits=18.0,
        )
        assert req.maxCredits == 18.0

    def test_invalid_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            GenerateSemesterPlanRequest(semesterCode="Fall2025")
        assert "Semester code" in str(exc_info.value)

    def test_min_credits_greater_than_max_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            GenerateSemesterPlanRequest(
                semesterCode=VALID_SEMESTER,
                maxCredits=10.0,
                minCredits=12.0,
            )
        assert "minCredits cannot be greater than maxCredits" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            GenerateSemesterPlanRequest.model_validate(
                {"semesterCode": VALID_SEMESTER, "userId": "malicious"}
            )


class TestManualSemesterInput:
    def test_valid_semester_with_planned_courses_accepted(self):
        sem = ManualSemesterInput(
            semesterCode=VALID_SEMESTER,
            plannedCourses=[make_planned_course()],
        )
        assert sem.semesterCode == VALID_SEMESTER

    def test_goal_credits_none_explicitly_accepted(self):
        sem = ManualSemesterInput(
            semesterCode=VALID_SEMESTER,
            plannedCourses=[make_planned_course()],
            goalCredits=None,
        )
        assert sem.goalCredits is None

    def test_valid_goal_credits_accepted(self):
        sem = ManualSemesterInput(
            semesterCode=VALID_SEMESTER,
            plannedCourses=[make_planned_course()],
            goalCredits=15.0,
        )
        assert sem.goalCredits == 15.0

    def test_empty_planned_and_maybe_courses_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ManualSemesterInput(semesterCode=VALID_SEMESTER)
        assert "at least one course" in str(exc_info.value)

    def test_maybe_courses_only_accepted(self):
        sem = ManualSemesterInput(
            semesterCode=VALID_SEMESTER,
            maybeCourses=[make_planned_course()],
        )
        assert len(sem.maybeCourses) == 1


class TestCreateManualSemesterPlanRequest:
    def test_valid_flat_request_accepted(self):
        req = CreateManualSemesterPlanRequest(
            name="My Plan",
            semesterCode=VALID_SEMESTER,
            plannedCourses=[make_planned_course()],
        )
        assert req.name == "My Plan"

    def test_valid_semesters_request_accepted(self):
        req = CreateManualSemesterPlanRequest(
            name="Multi-Semester Plan",
            semesters=[make_valid_manual_semester()],
        )
        assert len(req.semesters) == 1

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                status="published",
                semesters=[make_valid_manual_semester()],
            )
        assert "draft or active" in str(exc_info.value)

    def test_active_status_accepted(self):
        req = CreateManualSemesterPlanRequest(
            name="Plan",
            status="active",
            semesters=[make_valid_manual_semester()],
        )
        assert req.status == "active"

    def test_semester_code_none_accepted(self):
        req = CreateManualSemesterPlanRequest(
            name="Plan",
            semesterCode=None,
            semesters=[make_valid_manual_semester()],
        )
        assert req.semesterCode is None

    def test_goal_credits_none_accepted(self):
        req = CreateManualSemesterPlanRequest(
            name="Plan",
            goalCredits=None,
            semesters=[make_valid_manual_semester()],
        )
        assert req.goalCredits is None

    def test_semesters_combined_with_planned_courses_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                semesters=[make_valid_manual_semester()],
                plannedCourses=[make_planned_course()],
            )
        assert "not both" in str(exc_info.value)

    def test_semesters_combined_with_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                semesters=[make_valid_manual_semester()],
                semesterCode=VALID_SEMESTER,
            )
        assert "not both" in str(exc_info.value)

    def test_no_semesters_and_no_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                plannedCourses=[make_planned_course()],
            )
        assert "semesterCode and plannedCourses are required" in str(exc_info.value)

    def test_no_semesters_and_no_planned_courses_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                semesterCode=VALID_SEMESTER,
            )
        assert "semesterCode and plannedCourses are required" in str(exc_info.value)

    def test_neither_semesters_nor_flat_fields_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(name="Plan")
        assert "semesterCode and plannedCourses are required" in str(exc_info.value)


class TestCreateManualSemesterPlanGoalCredits:
    def test_valid_goal_credits_applied_when_using_semesters(self):
        req = CreateManualSemesterPlanRequest(
            name="Plan",
            goalCredits=15.0,
            semesters=[make_valid_manual_semester()],
        )
        assert req.goalCredits == 15.0

    def test_invalid_goal_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateManualSemesterPlanRequest(
                name="Plan",
                goalCredits=36.5,
                semesters=[make_valid_manual_semester()],
            )
        assert "at most 36" in str(exc_info.value)


class TestUpdateSemesterPlanRequest:
    def test_update_name_only_accepted(self):
        req = UpdateSemesterPlanRequest(name="New Name")
        assert req.name == "New Name"

    def test_status_none_explicitly_accepted(self):
        req = UpdateSemesterPlanRequest(name="Plan", status=None)
        assert req.status is None

    def test_valid_status_draft_accepted(self):
        req = UpdateSemesterPlanRequest(status="draft")
        assert req.status == "draft"

    def test_valid_status_active_accepted(self):
        req = UpdateSemesterPlanRequest(status="active")
        assert req.status == "active"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateSemesterPlanRequest(status="archived")
        assert "draft or active" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            UpdateSemesterPlanRequest.model_validate({"userId": "hack"})
