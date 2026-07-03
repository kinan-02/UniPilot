"""Typed negotiation artifacts exchanged between MAS agents."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class GoalIntent(str, Enum):
    EXPLICIT_COURSES = "explicit_courses"
    BALANCED_LOAD = "balanced_load"
    TRACK_ALIGNED = "track_aligned"
    OPEN_EXPLORATION = "open_exploration"
    WHAT_IF = "what_if"
    WHAT_IF_FAIL = "what_if_fail"
    POLICY_QA = "policy_qa"
    UNCLEAR = "unclear"


class GoalSpec(BaseModel):
    """Structured interpretation of the student's natural-language goal."""

    intent: GoalIntent = GoalIntent.OPEN_EXPLORATION
    explicit_course_ids: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ambiguity_note: str | None = None
    clarification_question: str | None = None
    what_if_scenario: str | None = None
    raw_goal: str = ""
    analysis_source: Literal["deterministic", "llm"] = "deterministic"


class ViolationType(str, Enum):
    MISSING_PLAN = "missing_plan"
    COURSE_NOT_IN_CATALOG = "course_not_in_catalog"
    PREREQ_MISSING = "prereq_missing"
    SCHEDULE_CONFLICT = "schedule_conflict"
    CREDIT_OVERLOAD = "credit_overload"
    EMPTY_PLAN = "empty_plan"
    PROBATION_RISK = "probation_risk"
    OTHER = "other"


class Violation(BaseModel):
    type: ViolationType
    message: str
    course_ids: list[str] = Field(default_factory=list)
    hard: bool = True


class FeasibilityReport(BaseModel):
    agent_role: str = "catalog_scout"
    ok: bool = False
    violations: list[Violation] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class RiskReport(BaseModel):
    agent_role: str = "risk_sentinel"
    ok: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)
    violations: list[Violation] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class ProgressReport(BaseModel):
    agent_role: str = "progress_scout"
    progress_score: float = 0.0
    unlock_count: int = 0
    critiques: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class PreferenceReport(BaseModel):
    agent_role: str = "student_advocate"
    critiques: list[dict[str, Any]] = Field(default_factory=list)
    trade_offs: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class ArbitrationResult(BaseModel):
    chosen_variant: str = "primary"
    utility: float = 0.0
    breakdown: dict[str, Any] = Field(default_factory=dict)
    considered_variants: list[str] = Field(default_factory=list)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)


class StudentSummary(BaseModel):
    headline: str = ""
    rationale: str = ""
    trade_offs: list[str] = Field(default_factory=list)
    source: Literal["deterministic", "llm"] = "deterministic"


class HardConstraintResult(BaseModel):
    """Unified catalog + workload hard gate for a single plan."""

    ok: bool = False
    feasibility: FeasibilityReport = Field(default_factory=FeasibilityReport)
    risk: RiskReport = Field(default_factory=RiskReport)
    violations: list[Violation] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    veto_agent: str | None = None


class VariantEvaluation(BaseModel):
    """Per-variant soft critic outputs used during arbitration."""

    model_config = {"arbitrary_types_allowed": True}

    variant: str = "primary"
    course_ids: list[str] = Field(default_factory=list)
    progress_report: ProgressReport = Field(default_factory=ProgressReport)
    preference_report: PreferenceReport = Field(default_factory=PreferenceReport)
    hard_ok: bool = True
