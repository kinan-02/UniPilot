"""Parse result schemas shared with the API gateway."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ParsedCourseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseNumber: str = Field(min_length=8, max_length=8)
    semesterCode: str
    grade: float = Field(ge=0, le=100)
    creditsEarned: float = Field(ge=0, le=36)
    attempt: int | None = Field(default=None, ge=1, le=5)
    title: str | None = None
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class ParseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageCount: int = Field(ge=0)
    extractor: str
    pipelineVersion: str
    textCharCount: int = Field(ge=0)
    ocrUsed: bool = False


class ParseTranscriptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: list[ParsedCourseEntry]
    studentId: str | None = None
    studentName: str | None = None
    warnings: list[str] = Field(default_factory=list)
    parseMetadata: ParseMetadata
