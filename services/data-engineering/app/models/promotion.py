"""Models for Phase 11 staging → production promotion gate (dry-run plan)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GateStatus = Literal["pass", "fail", "pass-with-warnings"]
PromotionAction = Literal["upsert", "skip", "advisory-only"]


class PromotionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nonExecutableRulesPolicy: str = Field(min_length=1, max_length=100)
    enforceNonExecutableRulesInProduction: bool = False
    productionExcludedCoursePolicy: str = Field(min_length=1, max_length=100)
    productionExcludedCourseNumbers: list[str] = Field(default_factory=list)
    signedOffBy: str | None = None
    signedOffAt: str | None = None


class PromotionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkId: str = Field(min_length=1, max_length=100)
    passed: bool
    severity: Literal["info", "warning", "blocker"] = "info"
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class PromotionPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemType: str = Field(min_length=1, max_length=80)
    stagingKey: str = Field(min_length=1, max_length=300)
    productionCollection: str = Field(min_length=1, max_length=100)
    action: PromotionAction = "upsert"
    identifier: str = Field(min_length=1, max_length=200)
    enforceInGraduationProgress: bool = False
    notes: str | None = None


class SkippedPromotionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemType: str = Field(min_length=1, max_length=80)
    identifier: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)
    details: dict[str, Any] = Field(default_factory=dict)


class PromotionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degreePrograms: list[PromotionPlanItem] = Field(default_factory=list)
    catalogPathOptions: list[PromotionPlanItem] = Field(default_factory=list)
    catalogFaculties: list[PromotionPlanItem] = Field(default_factory=list)
    hardDegreeRequirements: list[PromotionPlanItem] = Field(default_factory=list)
    advisoryCatalogRules: list[PromotionPlanItem] = Field(default_factory=list)
    courses: list[PromotionPlanItem] = Field(default_factory=list)
    courseOfferings: list[PromotionPlanItem] = Field(default_factory=list)
    skippedItems: list[SkippedPromotionItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class PromotionGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generatedAt: str = Field(min_length=1, max_length=50)
    sourceName: str = Field(default="technion-dds-catalog", min_length=1, max_length=200)
    catalogYear: int | None = None
    catalogVersion: str | None = None
    gateStatus: GateStatus
    canPromote: bool
    dryRun: bool = True
    checks: list[PromotionCheck] = Field(default_factory=list)
    policiesApplied: PromotionPolicy | None = None
    plannedWrites: PromotionPlan = Field(default_factory=PromotionPlan)
    advisoryRules: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    productionSafetySummary: dict[str, Any] = Field(default_factory=dict)
    rollbackNotes: list[str] = Field(default_factory=list)
    recommendedNextAction: str = Field(min_length=1, max_length=500)


class PromotionReport(BaseModel):
    """Full Phase 11 report envelope."""

    model_config = ConfigDict(extra="forbid")

    gate: PromotionGateResult
    qualityReportSummary: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(
        default="Phase 11 dry-run only — no production collections were written.",
        min_length=1,
        max_length=500,
    )


PromotionRunStatus = Literal["planned", "completed", "failed", "rolled_back"]


class ProductionPromotionRun(BaseModel):
    """Audit record for a guarded staging → production promotion."""

    model_config = ConfigDict(extra="forbid")

    promotionRunId: str = Field(min_length=1, max_length=100)
    sourceName: str = Field(min_length=1, max_length=200)
    catalogYear: int | None = None
    catalogVersion: str | None = None
    startedAt: str = Field(min_length=1, max_length=50)
    finishedAt: str | None = None
    status: PromotionRunStatus
    gateStatus: GateStatus
    dryRun: bool = False
    confirmationFlagProvided: bool = False
    triggeredBy: str = Field(default="data-engineering-cli", min_length=1, max_length=100)
    countsPlanned: dict[str, int] = Field(default_factory=dict)
    countsWritten: dict[str, int] = Field(default_factory=dict)
    skippedItems: list[SkippedPromotionItem] = Field(default_factory=list)
    policiesApplied: PromotionPolicy | None = None
    productionCollectionsTouched: list[str] = Field(default_factory=list)
    productionCollectionCountsBefore: dict[str, int] = Field(default_factory=dict)
    productionCollectionCountsAfter: dict[str, int] = Field(default_factory=dict)
    plannedProductionKeys: dict[str, list[str]] = Field(default_factory=dict)
    rollbackNotes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ProductionPromotionResult(BaseModel):
    """Outcome of promote-dds-to-production."""

    model_config = ConfigDict(extra="forbid")

    promotionRun: ProductionPromotionRun
    gate: PromotionGateResult
    productionWritesPerformed: bool
    reportPaths: dict[str, str] = Field(default_factory=dict)
