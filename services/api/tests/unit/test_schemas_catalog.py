"""Behavioral tests for catalog query schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.catalog import CourseListQuery, CourseOfferingsQuery


class TestCourseListQuery:
    def test_default_query_accepted(self):
        q = CourseListQuery()
        assert q.limit == 50
        assert q.offset == 0
        assert q.includeOfferings is False

    def test_valid_course_number_accepted(self):
        q = CourseListQuery(courseNumber="01234567")
        assert q.courseNumber == "01234567"

    def test_invalid_course_number_too_short_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseListQuery(courseNumber="CS101")
        assert "8-digit" in str(exc_info.value)

    def test_invalid_course_number_wrong_prefix_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseListQuery(courseNumber="11234567")
        assert "8-digit" in str(exc_info.value)

    def test_valid_semester_code_200_accepted(self):
        q = CourseListQuery(academicYear=2025, semesterCode=200)
        assert q.semesterCode == 200

    def test_valid_semester_code_201_accepted(self):
        q = CourseListQuery(academicYear=2025, semesterCode=201)
        assert q.semesterCode == 201

    def test_valid_semester_code_202_accepted(self):
        q = CourseListQuery(academicYear=2025, semesterCode=202)
        assert q.semesterCode == 202

    def test_invalid_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseListQuery(academicYear=2025, semesterCode=999)
        assert "semesterCode" in str(exc_info.value)

    def test_academic_year_without_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseListQuery(academicYear=2025)
        assert "together" in str(exc_info.value)

    def test_semester_code_without_academic_year_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseListQuery(semesterCode=200)
        assert "together" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CourseListQuery.model_validate({"unknownField": "value"})

    def test_course_number_none_accepted(self):
        q = CourseListQuery(courseNumber=None)
        assert q.courseNumber is None


class TestCourseOfferingsQuery:
    def test_empty_query_accepted(self):
        q = CourseOfferingsQuery()
        assert q.academicYear is None
        assert q.semesterCode is None

    def test_semester_code_200_accepted(self):
        q = CourseOfferingsQuery(semesterCode=200)
        assert q.semesterCode == 200

    def test_semester_code_201_accepted(self):
        q = CourseOfferingsQuery(semesterCode=201)
        assert q.semesterCode == 201

    def test_semester_code_202_accepted(self):
        q = CourseOfferingsQuery(semesterCode=202)
        assert q.semesterCode == 202

    def test_invalid_semester_code_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            CourseOfferingsQuery(semesterCode=999)
        assert "semesterCode" in str(exc_info.value)

    def test_semester_code_none_accepted(self):
        q = CourseOfferingsQuery(semesterCode=None)
        assert q.semesterCode is None

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CourseOfferingsQuery.model_validate({"unknownField": "value"})
