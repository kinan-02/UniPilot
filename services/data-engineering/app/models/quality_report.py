"""Models for Phase 10 staging data quality reports."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FindingSeverity = Literal[
    "info",
    "warning",
    "staging-blocker",
    "production-blocker",
    "api-migration-blocker",
]

QualityStatus = Literal["pass", "pass-with-warnings", "needs-fixes"]
QualityRecommendation = Literal[
    "ready-for-staging-review",
    "needs-staging-fixes",
    "ready-for-production-promotion-design",
    "not-ready",
]


class QualityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    severity: FindingSeverity
    category: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class QualityCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkId: str = Field(min_length=1, max_length=100)
    passed: bool
    severity: FindingSeverity = "info"
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class DdsStagingQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reportId: str = Field(min_length=1, max_length=100)
    sourceName: str = Field(default="technion-dds-staging", min_length=1, max_length=200)
    sourceType: str = Field(default="staging_quality_review", min_length=1, max_length=100)
    generatedAt: str = Field(min_length=1, max_length=50)
    status: QualityStatus
    recommendation: QualityRecommendation
    summary: str = Field(min_length=1, max_length=1000)
    counts: dict[str, Any] = Field(default_factory=dict)
    checks: list[QualityCheckResult] = Field(default_factory=list)
    findings: list[QualityFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockersForProduction: list[str] = Field(default_factory=list)
    blockersForApiMigration: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    manualReviewSummary: dict[str, Any] = Field(default_factory=dict)
    courseReferenceCoverage: dict[str, Any] = Field(default_factory=dict)
    creditMismatchSummary: dict[str, Any] = Field(default_factory=dict)
    nonExecutableRuleSummary: dict[str, Any] = Field(default_factory=dict)
    missingTitleHintSummary: dict[str, Any] = Field(default_factory=dict)
    productionSafetySummary: dict[str, Any] = Field(default_factory=dict)
