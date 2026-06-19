"""Proposed catalog models for manual curation and future staging import.

Not wired to MongoDB in Phase 6 / 6.5.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConfidenceLevel = Literal["low", "medium", "high"]


class CuratedCatalogSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institutionId: str = Field(min_length=1, max_length=100)
    sourceType: str = Field(min_length=1, max_length=100)
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    sourceFile: str = Field(min_length=1, max_length=500)
    pageReferences: list[int] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"
    notes: list[str] = Field(default_factory=list)


class CatalogCourseReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courseNumber: str = Field(min_length=8, max_length=8, pattern=r"^0\d{7}$")
    titleHint: str | None = None
    creditsHint: float | None = Field(default=None, ge=0)
    pageNumbers: list[int] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"


class CatalogRequirementGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groupId: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    requirementType: str = Field(min_length=1, max_length=50)
    minCredits: float | None = Field(default=None, ge=0)
    courseReferences: list[CatalogCourseReference] = Field(default_factory=list)
    ruleExpression: dict[str, Any] = Field(default_factory=dict)
    pageNumbers: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"


class NormalizedDegreePath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathCode: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    requirementGroupIds: list[str] = Field(default_factory=list)
    pageNumbers: list[int] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"


class NormalizedDegreeProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institutionId: str = Field(min_length=1, max_length=100)
    programCode: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=300)
    nameEn: str | None = None
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    totalCredits: float | None = Field(default=None, ge=0)
    paths: list[NormalizedDegreePath] = Field(default_factory=list)
    requirementGroups: list[CatalogRequirementGroup] = Field(default_factory=list)
    pageNumbers: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"


class CuratedCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: CuratedCatalogSource
    programs: list[NormalizedDegreeProgram] = Field(default_factory=list)
    parserReport: dict[str, Any] = Field(default_factory=dict)
