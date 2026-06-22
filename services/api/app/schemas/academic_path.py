"""Student academic path selections (Phase 0)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PathSelectionKind(str, Enum):
    BSC_TRACK = "bsc_track"
    MINOR = "minor"
    SPECIAL_PROGRAM = "special_program"
    GRADUATE_PROGRAM = "graduate_program"
    DNE_SPECIALIZATION = "dne_specialization"


class AcademicPathSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PathSelectionKind
    trackSlug: str | None = Field(default=None, max_length=120)
    programCode: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=200)

    @field_validator("trackSlug", "programCode", "label", mode="before")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class StudentAcademicPath(BaseModel):
    """DDS-focused path profile; minors/programs reserved for later phases."""

    model_config = ConfigDict(extra="forbid")

    trackSlug: str | None = Field(default=None, max_length=120)
    minors: list[AcademicPathSelection] = Field(default_factory=list, max_length=8)
    specialPrograms: list[AcademicPathSelection] = Field(default_factory=list, max_length=8)
    graduatePrograms: list[AcademicPathSelection] = Field(default_factory=list, max_length=4)
    specializations: list[AcademicPathSelection] = Field(default_factory=list, max_length=4)

    @field_validator("trackSlug", mode="before")
    @classmethod
    def strip_track_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


CurriculumViewMode = Literal["semester_swimlanes", "mind_map"]
