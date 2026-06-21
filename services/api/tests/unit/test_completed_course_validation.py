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
        grade=82,
        creditsEarned=3.5,
        attempt=1,
        metadata={"notes": "reviewed"},
    )

    assert payload.courseId == VALID_COURSE_ID
    assert payload.creditsEarned == 3.5
    assert payload.grade == 82


def test_create_request_accepts_string_numeric_grade():
    payload = CreateCompletedCourseRequest(
        courseId=VALID_COURSE_ID,
        semesterCode="2024-1",
        grade="82",
        creditsEarned=3,
    )
    assert payload.grade == 82.0


def test_create_request_rejects_invalid_course_id():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId="not-an-object-id",
            semesterCode="2024-1",
            grade=82,
            creditsEarned=3,
        )


def test_create_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest.model_validate(
            {
                "courseId": VALID_COURSE_ID,
                "semesterCode": "2024-1",
                "grade": 82,
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
                "grade": 82,
                "creditsEarned": 3,
                "_id": VALID_COURSE_ID,
            }
        )


def test_create_request_rejects_invalid_grade():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade="A+",
            creditsEarned=3,
        )


def test_create_request_rejects_grade_out_of_range():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade=101,
            creditsEarned=3,
        )


def test_create_request_rejects_invalid_credit_increment():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade=82,
            creditsEarned=2.25,
        )


def test_create_request_rejects_official_source():
    with pytest.raises(ValidationError):
        CreateCompletedCourseRequest.model_validate(
            {
                "courseId": VALID_COURSE_ID,
                "semesterCode": "2024-1",
                "grade": 82,
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
                "grade": 82,
            }
        )


def test_update_request_rejects_id_field():
    with pytest.raises(ValidationError):
        UpdateCompletedCourseRequest.model_validate(
            {
                "_id": VALID_COURSE_ID,
                "grade": 82,
            }
        )


def test_update_request_accepts_partial_payload():
    payload = UpdateCompletedCourseRequest(grade=78)
    assert payload.grade == 78


def test_create_request_rejects_credits_below_zero():
    with pytest.raises(ValidationError) as exc_info:
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade=80,
            creditsEarned=-1.0,
        )
    assert "at least 0" in str(exc_info.value)


def test_create_request_rejects_credits_above_36():
    with pytest.raises(ValidationError) as exc_info:
        CreateCompletedCourseRequest(
            courseId=VALID_COURSE_ID,
            semesterCode="2024-1",
            grade=80,
            creditsEarned=36.5,
        )
    assert "at most 36" in str(exc_info.value)


def test_update_request_accepts_explicit_none_grade():
    payload = UpdateCompletedCourseRequest(grade=None, semesterCode="2024-1")
    assert payload.grade is None


def test_update_request_accepts_explicit_none_semester_code():
    payload = UpdateCompletedCourseRequest(semesterCode=None, grade=85)
    assert payload.semesterCode is None


def test_update_request_accepts_explicit_none_credits_earned():
    payload = UpdateCompletedCourseRequest(creditsEarned=None, grade=75)
    assert payload.creditsEarned is None


def test_update_request_accepts_valid_credits_earned():
    payload = UpdateCompletedCourseRequest(creditsEarned=3.5)
    assert payload.creditsEarned == 3.5


def test_update_request_accepts_valid_semester_code():
    payload = UpdateCompletedCourseRequest(semesterCode="2025-2")
    assert payload.semesterCode == "2025-2"


def test_update_request_rejects_invalid_semester_code():
    with pytest.raises(ValidationError) as exc_info:
        UpdateCompletedCourseRequest(semesterCode="Fall-2025")
    assert "Semester code" in str(exc_info.value)


def test_update_request_rejects_credits_not_in_half_increments():
    with pytest.raises(ValidationError) as exc_info:
        UpdateCompletedCourseRequest(creditsEarned=2.7)
    assert "0.5 increments" in str(exc_info.value)
