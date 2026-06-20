"""Semester plan request/response schemas (Phase 16)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.completed_course import is_half_credit_increment
from app.schemas.student_profile import validate_object_id, validate_semester_code

OBJECT_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)


def validate_credit_load(value: float) -> float:
    if value < 0:
        raise ValueError("Credits must be at least 0")
    if value > 36:
        raise ValueError("Credits must be at most 36")
    if not is_half_credit_increment(value):
        raise ValueError("Credits must be in 0.5 increments")
    return value


class GenerateSemesterPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semesterCode: str
    maxCredits: float | None = None
    minCredits: float | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str) -> str:
        return validate_semester_code(value)

    @field_validator("maxCredits", "minCredits")
    @classmethod
    def validate_optional_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credit_load(value)

    @model_validator(mode="after")
    def validate_credit_bounds(self) -> "GenerateSemesterPlanRequest":
        if (
            self.maxCredits is not None
            and self.minCredits is not None
            and self.minCredits > self.maxCredits
        ):
            raise ValueError("minCredits cannot be greater than maxCredits")
        return self


class SemesterPlanListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
