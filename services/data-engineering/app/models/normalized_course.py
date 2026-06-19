from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

OBJECT_ID_PATTERN = __import__("re").compile(r"^[a-f0-9]{24}$", __import__("re").IGNORECASE)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    retrievedAt: datetime


class NormalizedCourse(BaseModel):
    """Normalized course record for staging import (not production catalog)."""

    model_config = ConfigDict(extra="forbid")

    institutionId: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=32)
    number: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=300)
    credits: float = Field(ge=0.5, le=36)
    description: str = Field(min_length=1, max_length=4000)
    level: str = Field(min_length=1, max_length=50)
    tags: list[str] = Field(default_factory=list)
    prerequisiteCourseIds: list[str] = Field(default_factory=list)
    corequisiteCourseIds: list[str] = Field(default_factory=list)
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    version: str = Field(min_length=1, max_length=50)
    status: str = Field(min_length=1, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sourceRefs: list[SourceRef] = Field(min_length=1)

    @field_validator("prerequisiteCourseIds", "corequisiteCourseIds")
    @classmethod
    def validate_course_id_references(cls, values: list[str]) -> list[str]:
        for value in values:
            if not OBJECT_ID_PATTERN.match(value):
                raise ValueError("Course reference ids must be valid ObjectId strings")
        return values

    def staging_key(self) -> str:
        return f"{self.institutionId}:{self.subject}:{self.number}:{self.version}"
