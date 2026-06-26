"""Proposed catalog models for manual curation and future staging import.

Not wired to MongoDB in Phase 6 / 6.5.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConfidenceLevel = Literal["low", "medium", "high"]


class CuratedCatalogSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institutionId: str = Field(min_length=1, max_length=100)
    facultyId: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Technion faculty slug (e.g. dds) when export is faculty-scoped.",
    )
    sourceName: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Staging/production source name (e.g. technion-dds-catalog).",
    )
    expectedProgramCodes: list[str] = Field(
        default_factory=list,
        description="Program codes expected in this faculty export.",
    )
    exportMode: str | None = Field(
        default=None,
        max_length=50,
        description="specialized (DDS) or generic faculty exporter.",
    )
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
    facultyHint: str | None = None
    semestersOffered: list[int] = Field(default_factory=list)
    prerequisitesText: str | None = None
    corequisitesText: str | None = None
    noAdditionalCreditText: str | None = None
    footnoteMarkers: list[str] = Field(default_factory=list)
    pageNumbers: list[int] = Field(default_factory=list)
    sourceEvidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"
    offeringMetadataNote: str | None = (
        "Semester offering JSON reference only; not the full canonical catalog."
    )


class CatalogRequirementGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groupId: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    requirementType: str = Field(min_length=1, max_length=50)
    minCredits: float | None = Field(default=None, ge=0)
    courseReferences: list[CatalogCourseReference] = Field(default_factory=list)
    ruleExpression: dict[str, Any] = Field(default_factory=dict)
    pageNumbers: list[int] = Field(default_factory=list)
    wikiSourceRefs: list[dict[str, str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    catalogDescription: str | None = None
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
    wikiSourceRefs: list[dict[str, str]] = Field(default_factory=list)
    manualReviewRequired: bool = True
    confidence: ConfidenceLevel = "low"


class CuratedCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: CuratedCatalogSource
    programs: list[NormalizedDegreeProgram] = Field(default_factory=list)
    parserReport: dict[str, Any] = Field(default_factory=dict)


class CurationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curatedBy: str = Field(min_length=1, max_length=100)
    curatedAt: str = Field(min_length=1, max_length=50)
    sourceDraftPath: str = Field(min_length=1, max_length=500)
    sourceMarkdownPath: str = Field(min_length=1, max_length=500)
    courseJsonSources: list[str] = Field(default_factory=list)
    curationStatus: str = Field(min_length=1, max_length=100)
    knownLimitations: list[str] = Field(default_factory=list)
    countsBefore: dict[str, Any] = Field(default_factory=dict)
    countsAfter: dict[str, Any] = Field(default_factory=dict)
    unresolvedIssues: list[str] = Field(default_factory=list)


class SignoffReviewMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewedBy: str = Field(min_length=1, max_length=100)
    reviewedAt: str = Field(min_length=1, max_length=50)
    reviewStatus: str = Field(min_length=1, max_length=100)
    sourceFilesReviewed: list[str] = Field(default_factory=list)
    checksPerformed: list[str] = Field(default_factory=list)
    verifiedItems: list[str] = Field(default_factory=list)
    unresolvedItems: list[str] = Field(default_factory=list)
    phase8Recommendation: str = Field(min_length=1, max_length=200)
    productionPromotionRecommendation: str = Field(min_length=1, max_length=200)


class CatalogFacultyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facultyId: str = Field(min_length=1, max_length=120)
    institutionId: str = Field(min_length=1, max_length=100)
    wikiSlug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    nameHe: str | None = None
    nameEn: str | None = None
    aliases: list[str] = Field(default_factory=list)
    catalogPrefix: str | None = None
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    status: str = "published"


class CatalogPathOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optionKey: str = Field(min_length=1, max_length=200)
    institutionId: str = Field(min_length=1, max_length=100)
    facultyId: str = Field(min_length=1, max_length=120)
    wikiSlug: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=300)
    nameHe: str | None = None
    nameEn: str | None = None
    studyLevels: list[str] = Field(default_factory=list)
    selectableAsPrimary: bool = False
    linkedProgramCode: str | None = None
    description: str | None = None
    duration: str | None = Field(default=None, max_length=200)
    totalCreditsRequired: str | None = Field(default=None, max_length=50)
    catalogYear: int = Field(ge=1990, le=2100)
    catalogVersion: str = Field(min_length=1, max_length=50)
    status: str = "published"


class ReviewedCuratedCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: CuratedCatalogSource
    programs: list[NormalizedDegreeProgram] = Field(default_factory=list)
    faculties: list[CatalogFacultyEntry] = Field(default_factory=list)
    pathOptions: list[CatalogPathOption] = Field(default_factory=list)
    parserReport: dict[str, Any] = Field(default_factory=dict)
    curationMetadata: CurationMetadata
    curationReport: dict[str, Any] = Field(default_factory=dict)
    signoffReview: SignoffReviewMetadata | None = None
