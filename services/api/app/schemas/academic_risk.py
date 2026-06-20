"""Academic risk request schemas (Phase 17)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.semester_plan import validate_credit_load
from app.schemas.student_profile import validate_object_id, validate_semester_code


class AnalyzeByPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planId: str

    @field_validator("planId")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        return validate_object_id(value)


class AnalyzeAdhocRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semesterCode: str
    courseIds: list[str] = Field(min_length=1, max_length=20)
    maxCredits: float | None = None
    minCredits: float | None = None

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str) -> str:
        return validate_semester_code(value)

    @field_validator("courseIds")
    @classmethod
    def validate_course_ids(cls, value: list[str]) -> list[str]:
        return [validate_object_id(course_id) for course_id in value]

    @field_validator("maxCredits", "minCredits")
    @classmethod
    def validate_optional_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credit_load(value)

    @model_validator(mode="after")
    def validate_credit_bounds(self) -> "AnalyzeAdhocRequest":
        if (
            self.maxCredits is not None
            and self.minCredits is not None
            and self.minCredits > self.maxCredits
        ):
            raise ValueError("minCredits cannot be greater than maxCredits")
        return self


class AnalyzeAcademicRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planId: str | None = None
    semesterCode: str | None = None
    courseIds: list[str] | None = None
    maxCredits: float | None = None
    minCredits: float | None = None

    @field_validator("planId")
    @classmethod
    def validate_plan_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @field_validator("courseIds")
    @classmethod
    def validate_course_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("At least one courseId is required")
        if len(value) > 20:
            raise ValueError("At most 20 courseIds are allowed")
        return [validate_object_id(course_id) for course_id in value]

    @field_validator("maxCredits", "minCredits")
    @classmethod
    def validate_optional_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credit_load(value)

    @model_validator(mode="after")
    def validate_analyze_mode(self) -> "AnalyzeAcademicRiskRequest":
        if self.planId:
            if self.semesterCode is not None or self.courseIds is not None:
                raise ValueError(
                    "Provide either planId or semesterCode with courseIds, not both"
                )
            if self.maxCredits is not None or self.minCredits is not None:
                raise ValueError("maxCredits and minCredits are only valid for ad-hoc analysis")
            return self

        if not self.semesterCode or not self.courseIds:
            raise ValueError("Provide either planId or semesterCode with courseIds")

        if (
            self.maxCredits is not None
            and self.minCredits is not None
            and self.minCredits > self.maxCredits
        ):
            raise ValueError("minCredits cannot be greater than maxCredits")

        return self
