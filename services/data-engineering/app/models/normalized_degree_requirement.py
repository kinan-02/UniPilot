from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.normalized_course import SourceRef

OBJECT_ID_PATTERN = __import__("re").compile(r"^[a-f0-9]{24}$", __import__("re").IGNORECASE)
ALLOWED_REQUIREMENT_TYPES = {"core", "elective", "credit", "capstone", "gpa"}


class RuleExpression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    operator: str = Field(min_length=1)


class NormalizedDegreeRequirement(BaseModel):
    """Normalized degree requirement for staging import (not production catalog)."""

    model_config = ConfigDict(extra="forbid")

    degreeId: str
    version: str = Field(min_length=1, max_length=50)
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    requirementType: str
    title: str = Field(min_length=1, max_length=300)
    ruleExpression: RuleExpression
    minCredits: float | None = Field(default=None, ge=0)
    courseIds: list[str] = Field(default_factory=list)
    priority: int = Field(ge=0)
    isMandatory: bool
    status: str = Field(min_length=1, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sourceRefs: list[SourceRef] = Field(min_length=1)

    @field_validator("degreeId")
    @classmethod
    def validate_degree_id(cls, value: str) -> str:
        if not OBJECT_ID_PATTERN.match(value):
            raise ValueError("degreeId must be a valid ObjectId string")
        return value

    @field_validator("requirementType")
    @classmethod
    def validate_requirement_type(cls, value: str) -> str:
        if value not in ALLOWED_REQUIREMENT_TYPES:
            raise ValueError(f"requirementType must be one of: {sorted(ALLOWED_REQUIREMENT_TYPES)}")
        return value

    @field_validator("courseIds")
    @classmethod
    def validate_course_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            if not OBJECT_ID_PATTERN.match(value):
                raise ValueError("courseIds must contain valid ObjectId strings")
        return values

    def staging_key(self) -> str:
        return f"{self.degreeId}:{self.version}:{self.requirementType}:{self.priority}:{self.title}"
