"""Shared negotiation state for MAS agent rounds."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.orchestrator.artifacts import (
    ArbitrationResult,
    FeasibilityReport,
    GoalSpec,
    PreferenceReport,
    ProgressReport,
    RiskReport,
    StudentSummary,
    VariantEvaluation,
    Violation,
)
from app.orchestrator.types import AgentTurn, PlanProposal


class Blackboard(BaseModel):
    """Mutable session state agents read and update during negotiation."""

    model_config = {"arbitrary_types_allowed": True}

    goal: str
    user_context: dict[str, Any] = Field(default_factory=dict)
    settings: Any = None
    engine: Any = None

    session_id: str | None = None

    goal_spec: GoalSpec | None = None
    candidate_plan: PlanProposal | None = None
    candidate_plans: list[PlanProposal] = Field(default_factory=list)
    best_seen_plan: PlanProposal | None = None
    best_seen_score: float = 0.0
    utility_breakdown: dict[str, Any] | None = None
    arbitration: ArbitrationResult | None = None
    student_summary: StudentSummary | None = None

    feasibility_report: FeasibilityReport | None = None
    risk_report: RiskReport | None = None
    progress_report: ProgressReport | None = None
    preference_report: PreferenceReport | None = None
    variant_evaluations: list[VariantEvaluation] = Field(default_factory=list)
    academic_risk_cache: dict[str, Any] = Field(default_factory=dict)

    typed_violations: list[Violation] = Field(default_factory=list)
    last_veto_agent: str | None = None

    open_vetoes: list[dict[str, Any]] = Field(default_factory=list)
    open_critiques: list[dict[str, Any]] = Field(default_factory=list)
    validation_references: list[str] = Field(default_factory=list)
    validation_violations: list[str] = Field(default_factory=list)
    relaxed_constraints: list[str] = Field(default_factory=list)

    transcript: list[dict[str, Any]] = Field(default_factory=list)
    round: int = 0
    max_rounds: int = 3

    @property
    def completed_courses(self) -> list[str]:
        return list(self.user_context.get("completed_courses") or [])

    def record_turn(self, turn: AgentTurn) -> None:
        self.transcript.append(turn.model_dump())

    def set_candidate(self, proposal: PlanProposal) -> None:
        self.candidate_plan = proposal
        if not self.candidate_plans:
            self.candidate_plans = [proposal]

    def set_candidates(self, proposals: list[PlanProposal]) -> None:
        self.candidate_plans = list(proposals)
        self.candidate_plan = proposals[0] if proposals else None

    def clear_vetoes(self) -> None:
        self.open_vetoes = []
        self.validation_violations = []
        self.typed_violations = []

    def apply_veto(
        self,
        *,
        agent_role: str,
        violations: list[str],
        references: list[str],
        typed_violations: list[Violation] | None = None,
    ) -> None:
        self.last_veto_agent = agent_role
        resolved_typed = typed_violations or []
        self.typed_violations = resolved_typed
        self.open_vetoes.append(
            {
                "agent": agent_role,
                "violations": violations,
                "references": references,
                "typedViolations": [item.model_dump() for item in resolved_typed],
            }
        )
        self.validation_violations = violations
        self.validation_references = references

    def apply_approval(self, *, references: list[str]) -> None:
        self.open_vetoes = []
        self.validation_violations = []
        self.validation_references = references
        self.typed_violations = []
        self.last_veto_agent = None

    def record_relaxation(self, note: str) -> None:
        if note and note not in self.relaxed_constraints:
            self.relaxed_constraints.append(note)

    def unique_agent_roles(self) -> int:
        return len({turn["agent_role"] for turn in self.transcript})
