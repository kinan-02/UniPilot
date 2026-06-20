import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OBJECT_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)
SEMESTER_CODE_PATTERN = re.compile(r"^\d{4}-[12]$")


def validate_object_id(value: str) -> str:
    if not OBJECT_ID_PATTERN.match(str(value)):
        raise ValueError("Identifier must be a valid ObjectId")
    return str(value)


def validate_semester_code(value: str) -> str:
    if not SEMESTER_CODE_PATTERN.match(str(value)):
        raise ValueError("Semester code must match YYYY-1 or YYYY-2 format")
    return str(value)


def strip_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip()


class StudentProfilePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maxCreditsPerSemester: int | None = Field(default=None, ge=1, le=36)


class CreateStudentProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institutionId: str = Field(min_length=1, max_length=100)
    programType: str = Field(min_length=1, max_length=100)
    degreeId: str | None = None
    catalogYear: int = Field(ge=1990, le=2100)
    currentSemesterCode: str
    preferences: StudentProfilePreferences | None = None

    @field_validator("institutionId", "programType", mode="before")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = str(value).strip()
        if not stripped:
            raise ValueError("Value must not be empty")
        return stripped

    @field_validator("degreeId")
    @classmethod
    def validate_degree_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)

    @field_validator("currentSemesterCode")
    @classmethod
    def validate_current_semester_code(cls, value: str) -> str:
        return validate_semester_code(value)


class UpdateStudentProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institutionId: str | None = Field(default=None, min_length=1, max_length=100)
    programType: str | None = Field(default=None, min_length=1, max_length=100)
    degreeId: str | None = None
    catalogYear: int | None = Field(default=None, ge=1990, le=2100)
    currentSemesterCode: str | None = None
    preferences: StudentProfilePreferences | None = None

    @field_validator("institutionId", "programType", mode="before")
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        return strip_optional_string(value)

    @field_validator("degreeId")
    @classmethod
    def validate_degree_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)

    @field_validator("currentSemesterCode")
    @classmethod
    def validate_current_semester_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UpdateStudentProfileRequest":
        payload = self.model_dump(exclude_none=True)
        if not payload:
            raise ValueError("At least one field is required for update")
        return self
