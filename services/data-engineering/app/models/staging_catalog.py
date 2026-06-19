"""Staging document shapes for DDS curated catalog import (Phase 8)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StagingCatalogImportMetadata(BaseModel):
    """Common import envelope preserved on every DDS catalog staging document."""

    model_config = ConfigDict(extra="forbid")

    stagingKey: str = Field(min_length=1, max_length=300)
    sourceName: str = Field(min_length=1, max_length=200)
    sourceType: str = Field(min_length=1, max_length=100)
    sourceVersion: str = Field(min_length=1, max_length=50)
    catalogYear: int = Field(ge=1990, le=2100)
    importedAt: str = Field(min_length=1, max_length=50)
    importRunId: str = Field(min_length=1, max_length=100)
    isStaging: bool = True
    productionEligible: bool = False
    requiresHumanSignoff: bool = True
    curationStatus: str = Field(min_length=1, max_length=100)
    signoffReviewStatus: str | None = None
    sourceFiles: list[str] = Field(default_factory=list)


class Phase8ReadinessCheck(BaseModel):
    """Phase 7.6 readiness gate consumed before staging import."""

    model_config = ConfigDict(extra="allow")

    canImportToStaging: bool
    canPromoteToProduction: bool = False
    blockingIssuesForStaging: list[str] = Field(default_factory=list)
    blockingIssuesForProduction: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reviewStatus: str | None = None
    phase8Recommendation: str | None = None
    productionPromotionRecommendation: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)


class CatalogStagingImportSummary(BaseModel):
    """Result summary returned by the DDS catalog staging importer."""

    model_config = ConfigDict(extra="forbid")

    dryRun: bool = False
    programsUpserted: int = 0
    requirementsUpserted: int = 0
    rulesUpserted: int = 0
    courseReferencesObserved: int = 0
    manualReviewRequiredItems: int = 0
    warningsPreserved: list[str] = Field(default_factory=list)
    stagingCollections: dict[str, str] = Field(default_factory=dict)
    ingestionRunId: str | None = None
    ingestionStatus: str | None = None
