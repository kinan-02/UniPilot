"""Behavioral tests for academic risk request schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.academic_risk import (
    AnalyzeAcademicRiskRequest,
    AnalyzeAdhocRequest,
    AnalyzeByPlanRequest,
)

VALID_PLAN_ID = "665f2b0f2a3f7b2a1a9a7f11"
VALID_COURSE_ID = "665f2b0f2a3f7b2a1a9a7c01"
VALID_SEMESTER = "2025-1"


class TestAnalyzeByPlanRequest:
    def test_valid_plan_id_accepted(self):
        req = AnalyzeByPlanRequest(planId=VALID_PLAN_ID)
        assert req.planId == VALID_PLAN_ID

    def test_invalid_plan_id_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeByPlanRequest(planId="not-an-object-id")
        assert "valid ObjectId" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            AnalyzeByPlanRequest.model_validate({"planId": VALID_PLAN_ID, "extra": "field"})


class TestAnalyzeAdhocRequest:
    def test_valid_request_accepted(self):
        req = AnalyzeAdhocRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
        )
        assert req.semesterCode == VALID_SEMESTER
        assert len(req.courseIds) == 1

    def test_invalid_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAdhocRequest(
                semesterCode="Fall-2025",
                courseIds=[VALID_COURSE_ID],
            )
        assert "Semester code" in str(exc_info.value)

    def test_invalid_course_id_in_list_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAdhocRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=["not-an-objectid"],
            )
        assert "valid ObjectId" in str(exc_info.value)

    def test_max_credits_none_accepted(self):
        req = AnalyzeAdhocRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
            maxCredits=None,
        )
        assert req.maxCredits is None

    def test_valid_max_credits_accepted(self):
        req = AnalyzeAdhocRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
            maxCredits=12.0,
        )
        assert req.maxCredits == 12.0

    def test_min_credits_greater_than_max_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAdhocRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[VALID_COURSE_ID],
                maxCredits=10.0,
                minCredits=12.0,
            )
        assert "minCredits cannot be greater than maxCredits" in str(exc_info.value)

    def test_equal_min_and_max_credits_accepted(self):
        req = AnalyzeAdhocRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
            maxCredits=12.0,
            minCredits=12.0,
        )
        assert req.maxCredits == req.minCredits == 12.0

    def test_empty_course_ids_rejected_by_min_length(self):
        with pytest.raises(ValidationError):
            AnalyzeAdhocRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[],
            )

    def test_too_many_course_ids_rejected_by_max_length(self):
        with pytest.raises(ValidationError):
            AnalyzeAdhocRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[VALID_COURSE_ID] * 21,
            )


class TestAnalyzeAcademicRiskRequest:
    def test_plan_id_mode_valid(self):
        req = AnalyzeAcademicRiskRequest(planId=VALID_PLAN_ID)
        assert req.planId == VALID_PLAN_ID

    def test_adhoc_mode_valid(self):
        req = AnalyzeAcademicRiskRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
        )
        assert req.semesterCode == VALID_SEMESTER
        assert req.courseIds == [VALID_COURSE_ID]

    def test_invalid_plan_id_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(planId="bad-id")
        assert "valid ObjectId" in str(exc_info.value)

    def test_invalid_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                semesterCode="Spring-2025",
                courseIds=[VALID_COURSE_ID],
            )
        assert "Semester code" in str(exc_info.value)

    def test_course_ids_none_is_allowed(self):
        req = AnalyzeAcademicRiskRequest(planId=VALID_PLAN_ID)
        assert req.courseIds is None

    def test_empty_course_ids_list_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[],
            )
        assert "At least one courseId is required" in str(exc_info.value)

    def test_more_than_twenty_course_ids_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[VALID_COURSE_ID] * 21,
            )
        assert "At most 20 courseIds are allowed" in str(exc_info.value)

    def test_max_credits_accepted_in_adhoc_mode(self):
        req = AnalyzeAcademicRiskRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
            maxCredits=15.0,
        )
        assert req.maxCredits == 15.0

    def test_plan_id_combined_with_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                planId=VALID_PLAN_ID,
                semesterCode=VALID_SEMESTER,
                courseIds=[VALID_COURSE_ID],
            )
        assert "not both" in str(exc_info.value)

    def test_plan_id_combined_with_course_ids_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                planId=VALID_PLAN_ID,
                courseIds=[VALID_COURSE_ID],
            )
        assert "not both" in str(exc_info.value)

    def test_plan_id_combined_with_max_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                planId=VALID_PLAN_ID,
                maxCredits=12.0,
            )
        assert "ad-hoc analysis" in str(exc_info.value)

    def test_plan_id_combined_with_min_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                planId=VALID_PLAN_ID,
                minCredits=6.0,
            )
        assert "ad-hoc analysis" in str(exc_info.value)

    def test_neither_plan_id_nor_adhoc_fields_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest()
        assert "planId or semesterCode" in str(exc_info.value)

    def test_semester_code_without_course_ids_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(semesterCode=VALID_SEMESTER)
        assert "planId or semesterCode" in str(exc_info.value)

    def test_adhoc_min_credits_greater_than_max_credits_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=[VALID_COURSE_ID],
                minCredits=15.0,
                maxCredits=10.0,
            )
        assert "minCredits cannot be greater than maxCredits" in str(exc_info.value)

    def test_invalid_course_id_in_adhoc_list_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeAcademicRiskRequest(
                semesterCode=VALID_SEMESTER,
                courseIds=["not-a-valid-id"],
            )
        assert "valid ObjectId" in str(exc_info.value)


class TestAnalyzeAcademicRiskRequestExplicitNone:
    """Tests that explicitly pass None for optional fields to hit None-return branches."""

    def test_explicit_none_plan_id_accepted(self):
        req = AnalyzeAcademicRiskRequest(
            planId=None,
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
        )
        assert req.planId is None

    def test_explicit_none_semester_code_with_valid_plan_id(self):
        req = AnalyzeAcademicRiskRequest(
            planId=VALID_PLAN_ID,
            semesterCode=None,
        )
        assert req.semesterCode is None

    def test_explicit_none_course_ids_with_valid_plan_id(self):
        req = AnalyzeAcademicRiskRequest(
            planId=VALID_PLAN_ID,
            courseIds=None,
        )
        assert req.courseIds is None

    def test_explicit_none_max_credits_with_valid_plan_id(self):
        req = AnalyzeAcademicRiskRequest(
            planId=VALID_PLAN_ID,
            maxCredits=None,
        )
        assert req.maxCredits is None

    def test_explicit_none_min_credits_in_adhoc_mode(self):
        req = AnalyzeAcademicRiskRequest(
            semesterCode=VALID_SEMESTER,
            courseIds=[VALID_COURSE_ID],
            minCredits=None,
        )
        assert req.minCredits is None
