"""What-if simulation scenario and result schemas (AGT-3 / DEC-2)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.semester_plan import validate_credit_load
from app.schemas.student_profile import validate_object_id, validate_semester_code

SimulationOpType = Literal["drop_course", "add_course", "add_planned_course", "change_track"]


class DropCourseOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["drop_course"] = "drop_course"
    courseNumber: str = Field(min_length=8, max_length=8)

    @field_validator("courseNumber")
    @classmethod
    def validate_course_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit() or len(normalized) != 8:
            raise ValueError("courseNumber must be an 8-digit catalog number")
        return normalized


class AddCourseOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["add_course"] = "add_course"
    courseNumber: str = Field(min_length=8, max_length=8)
    grade: float = Field(default=90.0, ge=0, le=100)
    semesterCode: str | None = None

    @field_validator("courseNumber")
    @classmethod
    def validate_course_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit() or len(normalized) != 8:
            raise ValueError("courseNumber must be an 8-digit catalog number")
        return normalized

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)


class AddPlannedCourseOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["add_planned_course"] = "add_planned_course"
    courseNumber: str = Field(min_length=8, max_length=8)

    @field_validator("courseNumber")
    @classmethod
    def validate_course_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit() or len(normalized) != 8:
            raise ValueError("courseNumber must be an 8-digit catalog number")
        return normalized


class ChangeTrackOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["change_track"] = "change_track"
    trackSlug: str = Field(min_length=1, max_length=120)


SimulationOperation = Annotated[
    DropCourseOp | AddCourseOp | AddPlannedCourseOp | ChangeTrackOp,
    Field(discriminator="type"),
]


class CreateSimulationScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    operations: list[SimulationOperation] = Field(min_length=1, max_length=20)
    semesterCode: str | None = None
    planId: str | None = None
    naturalLanguagePrompt: str | None = Field(default=None, max_length=4000)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @field_validator("planId")
    @classmethod
    def validate_plan_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)


class CreateSimulationFromTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    name: str | None = Field(default=None, max_length=200)
    semesterCode: str | None = None
    planId: str | None = None

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_semester_code(value)

    @field_validator("planId")
    @classmethod
    def validate_plan_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)


class RunSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executionMode: Literal["auto", "sync", "async"] = "auto"


def operations_to_storage(operations: list[SimulationOperation]) -> list[dict]:
    return [operation.model_dump() for operation in operations]


def validate_operations_payload(operations: list[dict]) -> list[dict]:
    validated: list[dict] = []
    for item in operations:
        op_type = item.get("type")
        if op_type == "drop_course":
            validated.append(DropCourseOp.model_validate(item).model_dump())
        elif op_type == "add_course":
            validated.append(AddCourseOp.model_validate(item).model_dump())
        elif op_type == "add_planned_course":
            validated.append(AddPlannedCourseOp.model_validate(item).model_dump())
        elif op_type == "change_track":
            validated.append(ChangeTrackOp.model_validate(item).model_dump())
        else:
            raise ValueError(f"Unsupported simulation operation type: {op_type}")
    return validated
