"""Transcript PDF import schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.completed_course import (
    validate_credits_earned,
    validate_grade_value,
)
from app.schemas.student_profile import validate_semester_code


class ParsedCourseEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseNumber: str
    semesterCode: str
    grade: float
    creditsEarned: float
    attempt: int | None = None
    title: str | None = None
    confidence: float
    warnings: list[str] = Field(default_factory=list)


class ParseMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageCount: int
    extractor: str
    pipelineVersion: str
    textCharCount: int
    ocrUsed: bool = False


class ParseTranscriptPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: list[ParsedCourseEntryResponse]
    studentId: str | None = None
    studentName: str | None = None
    warnings: list[str] = Field(default_factory=list)
    parseMetadata: ParseMetadataResponse


class CommitTranscriptCourseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseNumber: str = Field(min_length=6, max_length=12)
    semesterCode: str
    grade: float = Field(ge=0, le=100)
    creditsEarned: float
    attempt: int | None = Field(default=1, ge=1, le=5)
    title: str | None = None

    @field_validator("courseNumber", mode="before")
    @classmethod
    def validate_course_number(cls, value: str) -> str:
        from app.planning.prerequisite_resolver import canonical_course_number

        normalized = canonical_course_number(value)
        if not normalized:
            raise ValueError("Invalid course number")
        return normalized

    @field_validator("grade", mode="before")
    @classmethod
    def validate_grade(cls, value: int | float | str) -> float:
        return validate_grade_value(value)

    @field_validator("semesterCode")
    @classmethod
    def validate_semester(cls, value: str) -> str:
        return validate_semester_code(value)

    @field_validator("creditsEarned")
    @classmethod
    def validate_credits(cls, value: float) -> float:
        return validate_credits_earned(value)


class CommitTranscriptImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: list[CommitTranscriptCourseInput] = Field(min_length=1, max_length=100)
    skipDuplicates: bool = True


class UnresolvedTranscriptCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseNumber: str
    semesterCode: str
    reason: str


class CommitTranscriptImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: list[dict]
    skippedDuplicates: list[str] = Field(default_factory=list)
    unresolved: list[UnresolvedTranscriptCourse] = Field(default_factory=list)
    createdCount: int
    skippedCount: int
    unresolvedCount: int
