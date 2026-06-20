"""Semester plan request/response schemas (Phase 16)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.completed_course import is_half_credit_increment
from app.schemas.student_profile import validate_object_id, validate_semester_code

OBJECT_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)
ALLOWED_PLAN_STATUSES = frozenset({"draft", "active"})


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


class ManualPlannedCourseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseId: str
    category: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str | None = Field(default=None, min_length=1, max_length=240)

    @field_validator("courseId")
    @classmethod
    def validate_course_id(cls, value: str) -> str:
        return validate_object_id(value)


class WeeklyScheduleEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseId: str
    academicYear: int = Field(ge=2000, le=2100)
    semesterCode: int = Field(ge=200, le=202)
    scheduleGroups: list[dict[str, Any]] | None = None

    @field_validator("courseId")
    @classmethod
    def validate_course_id(cls, value: str) -> str:
        return validate_object_id(value)


class WeeklyScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[WeeklyScheduleEntryInput] = Field(default_factory=list)


class ManualSemesterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semesterCode: str
    goalCredits: float | None = None
    order: int | None = Field(default=None, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=500)
    plannedCourses: list[ManualPlannedCourseInput] = Field(min_length=1)
    weeklySchedule: WeeklyScheduleInput | None = None

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str) -> str:
        return validate_semester_code(value)

    @field_validator("goalCredits")
    @classmethod
    def validate_goal_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credit_load(value)


class CreateManualSemesterPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    status: str = Field(default="draft")
    semesterCode: str | None = None
    goalCredits: float | None = None
    notes: str | None = Field(default=None, max_length=500)
    plannedCourses: list[ManualPlannedCourseInput] | None = None
    weeklySchedule: WeeklyScheduleInput | None = None
    semesters: list[ManualSemesterInput] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_PLAN_STATUSES:
            raise ValueError("status must be draft or active")
        return value

    @field_validator("semesterCode")
    @classmethod
    def validate_optional_semester_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @field_validator("goalCredits")
    @classmethod
    def validate_goal_credits(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return validate_credit_load(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "CreateManualSemesterPlanRequest":
        if self.semesters:
            if self.plannedCourses or self.semesterCode:
                raise ValueError("Use either semesters or semesterCode/plannedCourses, not both")
            return self
        if not self.semesterCode or not self.plannedCourses:
            raise ValueError("semesterCode and plannedCourses are required when semesters is omitted")
        return self


class CreateSemesterPlanVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)


class UpdateSemesterPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = None
    semesters: list[ManualSemesterInput] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_PLAN_STATUSES:
            raise ValueError("status must be draft or active")
        return value


class SemesterPlanListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
