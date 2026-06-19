import pytest
from pydantic import ValidationError

from app.schemas.completed_course import (
    CreateCompletedCourseRequest,
    UpdateCompletedCourseRequest,
)

VALID_COURSE_ID = "665f2b0f2a3f7b2a1a9a7c01"


def test_create_request_accepts_valid_payload():
    payload = CreateCompletedCourseRequest(
        courseId=VALID_COURSE_ID,
        semesterCode="2024-1",
        grade="A",
        creditsEarned=3.5,
        attempt=1,
        metadata={"notes": "reviewed"},
    )

    assert payload.courseId == VALID_COURSE_ID
    assert payload.creditsEarned == 3.5


def test_create_request_rejects_invalid_course_id():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId="not-an-object-id",
            semesterCode="2024-1",
            grade="A",
            creditsEarned=3,
        )


def test_create_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest.model_validate(
            {
                "courseId": VALID_COURSE_ID,
                "semesterCode": "2024-1",
                "grade": "A",
                "creditsEarned": 3,
                "userId": "malicious-user",
            }
        )


def test_create_request_rejects_id_field():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest.model_validate(
            {
                "courseId": VALID_COURSE_ID,
                "semesterCode": "2024-1",
                "grade": "A",
                "creditsEarned": 3,
                "_id": VALID_COURSE_ID,
            }
        )


def test_create_request_rejects_invalid_grade():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade="Z",
            creditsEarned=3,
        )


def test_create_request_rejects_invalid_credit_increment():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade="A",
            creditsEarned=2.25,
        )


def test_create_request_rejects_official_source():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest.model_validate(
            {
                "courseId": VALID_COURSE_ID,
                "semesterCode": "2024-1",
                "grade": "A",
                "creditsEarned": 3,
                "source": "official",
            }
        )


def test_update_request_rejects_empty_payload():
    with pytest.raises(ValidationError):
        UpdateCompletedCourseRequest.model_validate({})


def test_update_request_rejects_user_id():
    with pytest.raises(ValidationError):
        UpdateCompletedCourseRequest.model_validate(
            {
                "userId": VALID_COURSE_ID,
                "grade": "A",
            }
        )


def test_update_request_rejects_id_field():
    with pytest.raises(ValidationError):
        UpdateCompletedCourseRequest.model_validate(
            {
                "_id": VALID_COURSE_ID,
                "grade": "A",
            }
        )


def test_update_request_accepts_partial_payload():
    payload = UpdateCompletedCourseRequest(grade="A-")
    assert payload.grade == "A-"
