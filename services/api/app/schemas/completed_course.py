"""Completed course request/response schemas (Technion numeric grades 0–100)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.student_profile import validate_object_id, validate_semester_code
from app.services.grade_evaluation import parse_numeric_grade

OBJECT_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)


def validate_grade_value(value: int | float | str) -> float:
    numeric = parse_numeric_grade(value)
    if numeric is None:
        raise ValueError("grade must be a number between 0 and 100")
    return numeric


def is_half_credit_increment(value: float) -> bool:
    return abs(value * 2 - round(value * 2)) < 1e-9


def validate_credits_earned(value: float) -> float:
    if value < 0:
        raise ValueError("creditsEarned must be at least 0")
    if value > 36:
        raise ValueError("creditsEarned must be at most 36")
    if not is_half_credit_increment(value):
        raise ValueError(
            "creditsEarned must be in 0.5 increments (for example 0, 1, 1.5, 2, 2.5, 3)"
        )
    return value


class CompletedCourseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=500)


class CreateCompletedCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseId: str
    semesterCode: str
    grade: float = Field(ge=0, le=100)
    gradePoints: float | None = Field(default=None, ge=0, le=100)
    creditsEarned: float
    attempt: int | None = Field(default=None, ge=1, le=10)
    source: Literal["manual"] | None = None
    metadata: CompletedCourseMetadata | None = None

    @field_validator("grade", mode="before")
    @classmethod
    def validate_grade(cls, value: int | float | str) -> float:
        return validate_grade_value(value)

    @field_validator("courseId")
    @classmethod
    def validate_course_id(cls, value: str) -> str:
        return validate_object_id(value)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester(cls, value: str) -> str:
        return validate_semester_code(value)

    @field_validator("creditsEarned")
    @classmethod
    def validate_credits(cls, value: float) -> float:
        return validate_credits_earned(value)


class UpdateCompletedCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semesterCode: str | None = None
    grade: float | None = Field(default=None, ge=0, le=100)
    gradePoints: float | None = Field(default=None, ge=0, le=100)
    creditsEarned: float | None = None
    metadata: CompletedCourseMetadata | None = None

    @field_validator("grade", mode="before")
    @classmethod
    def validate_grade(cls, value: int | float | str | None) -> float | None:
        if value is None:
            return None
        return validate_grade_value(value)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @field_validator("creditsEarned")
    @classmethod
    def validate_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credits_earned(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> UpdateCompletedCourseRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field is required for update")
        return self


class CompletedCourseListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)


class CompletedCourseResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    courseId: str
    courseNumber: str | None = None
    courseTitle: str | None = None
    semesterCode: str
    grade: float
    gradePoints: float | None = None
    creditsEarned: float
    attempt: int
    source: str
    metadata: dict
    recordedAt: str
    createdAt: str
    updatedAt: str


class CompletedCourseListResponse(BaseModel):
    completedCourses: list[CompletedCourseResponse]
    pagination: dict[str, int]
