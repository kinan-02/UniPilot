import pytest
from pydantic import ValidationError

from app.schemas.student_profile import (
    CreateStudentProfileRequest,
    UpdateStudentProfileRequest,
)

VALID_DEGREE_ID = "665f2b0f2a3f7b2a1a9a7f11"


def test_create_request_accepts_valid_payload():
    payload = CreateStudentProfileRequest(
        institutionId="uni-main",
        programType="BSc",
        degreeId=VALID_DEGREE_ID,
        catalogYear=2025,
        currentSemesterCode="2025-1",
        preferences={"maxCreditsPerSemester": 18},
    )

    assert payload.institutionId == "uni-main"
    assert payload.degreeId == VALID_DEGREE_ID


def test_create_request_accepts_missing_degree_id():
    payload = CreateStudentProfileRequest(
        institutionId="uni-main",
        programType="BSc",
        catalogYear=2025,
        currentSemesterCode="2025-1",
    )

    assert payload.degreeId is None


def test_create_request_rejects_invalid_semester_code():
    with pytest.raises(ValidationError):
        CreateStudentProfileRequest(
            institutionId="uni-main",
            programType="BSc",
            catalogYear=2025,
            currentSemesterCode="Fall-2025",
        )


def test_update_request_rejects_empty_payload():
    with pytest.raises(ValidationError):
        UpdateStudentProfileRequest.model_validate({})


def test_update_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        UpdateStudentProfileRequest.model_validate(
            {
                "institutionId": "uni-main",
                "userId": "malicious-user-id",
            }
        )


def test_create_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreateStudentProfileRequest.model_validate(
            {
                "institutionId": "uni-main",
                "programType": "BSc",
                "catalogYear": 2025,
                "currentSemesterCode": "2025-1",
                "userId": "malicious-user-id",
            }
        )


def test_update_request_rejects_id_field():
    with pytest.raises(ValidationError):
        UpdateStudentProfileRequest.model_validate(
            {
                "_id": VALID_DEGREE_ID,
                "programType": "BSc-Honors",
            }
        )


def test_create_request_rejects_invalid_degree_id():
    with pytest.raises(ValidationError):
        CreateStudentProfileRequest(
            institutionId="uni-main",
            programType="BSc",
            degreeId="not-an-object-id",
            catalogYear=2025,
            currentSemesterCode="2025-1",
        )


def test_preferences_reject_unknown_nested_fields():
    with pytest.raises(ValidationError):
        CreateStudentProfileRequest.model_validate(
            {
                "institutionId": "uni-main",
                "programType": "BSc",
                "catalogYear": 2025,
                "currentSemesterCode": "2025-1",
                "preferences": {
                    "maxCreditsPerSemester": 18,
                    "unknownField": True,
                },
            }
        )


def test_preferences_reject_out_of_range_max_credits():
    with pytest.raises(ValidationError):
        CreateStudentProfileRequest(
            institutionId="uni-main",
            programType="BSc",
            catalogYear=2025,
            currentSemesterCode="2025-1",
            preferences={"maxCreditsPerSemester": 37},
        )
