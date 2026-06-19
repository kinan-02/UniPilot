import pytest
from pydantic import ValidationError

from app.models.normalized_course import NormalizedCourse
from app.sources.sample_data import SAMPLE_COURSES
from app.validators.course_validator import validate_normalized_course


def test_sample_course_records_are_valid():
    for record in SAMPLE_COURSES:
        result = validate_normalized_course(record)
        assert result.is_valid is True


def test_normalized_course_rejects_invalid_credits():
    record = {
        **SAMPLE_COURSES[0],
        "credits": 99,
    }

    with pytest.raises(ValidationError):
        NormalizedCourse.model_validate(record)


def test_normalized_course_rejects_invalid_prerequisite_id():
    record = {
        **SAMPLE_COURSES[0],
        "prerequisiteCourseIds": ["not-valid"],
    }

    result = validate_normalized_course(record)
    assert result.is_valid is False
