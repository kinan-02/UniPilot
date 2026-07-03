"""Unified hard constraint evaluation for catalog + workload safety."""

from __future__ import annotations

from typing import Any

from app.orchestrator.artifacts import (
    FeasibilityReport,
    HardConstraintResult,
    RiskReport,
    Violation,
    ViolationType,
)
from app.orchestrator.violations import violation_from_message, violation_messages
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_academic_risk import (
    merge_academic_risk_evidence,
    violations_from_academic_risk_preview,
)
from app.services.plan_risk import (
    evaluate_credit_overload,
    evaluate_probation_pressure,
    resolve_max_credits,
)
from app.validator.pre_commit import validate_plan_proposal_typed


def evaluate_hard_constraints(
    *,
    course_ids: list[str],
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any],
    academic_risk_analysis: dict[str, Any] | None = None,
) -> HardConstraintResult:
    """
    Single source of truth for hard vetoes (catalog scout + risk sentinel).

    Used by negotiation veto loop, per-variant filtering, and arbitration.
    """
    references: list[str] = []
    violations: list[Violation] = []

    if not course_ids:
        empty_violation = violation_from_message("Plan must include at least one course.")
        feasibility = FeasibilityReport(
            ok=False,
            violations=[empty_violation],
            references=[],
        )
        risk = RiskReport(
            ok=False,
            violations=[
                Violation(
                    type=ViolationType.MISSING_PLAN,
                    message="No candidate plan to evaluate for workload risk.",
                )
            ],
            references=[],
        )
        return HardConstraintResult(
            ok=False,
            feasibility=feasibility,
            risk=risk,
            violations=[empty_violation],
            references=[],
            veto_agent="catalog_scout",
        )

    feas_ok, feas_typed, feas_refs = validate_plan_proposal_typed(
        course_ids=course_ids,
        engine=engine,
        completed_courses=completed_courses,
        user_context=user_context,
    )
    references.extend(feas_refs)
    feasibility = FeasibilityReport(
        ok=feas_ok,
        violations=feas_typed,
        references=feas_refs,
    )
    if not feas_ok:
        violations.extend(feas_typed)

    max_credits = resolve_max_credits(user_context)
    is_safe, evidence, risk_refs = evaluate_credit_overload(
        engine=engine,
        course_ids=course_ids,
        max_credits=max_credits,
        user_context=user_context,
    )
    pressured, probation_evidence, probation_refs = evaluate_probation_pressure(user_context)
    evidence = {**evidence, "probation": probation_evidence}
    merged_risk_refs = list(dict.fromkeys([*risk_refs, *probation_refs]))
    references = list(dict.fromkeys([*references, *merged_risk_refs]))

    risk_violations: list[Violation] = []
    if not is_safe:
        risk_violations.append(
            Violation(
                type=ViolationType.CREDIT_OVERLOAD,
                message=(
                    f"Credit overload: {evidence['totalCredits']} credits exceeds "
                    f"limit of {evidence['maxCredits']}."
                ),
                course_ids=list(course_ids),
            )
        )
        violations.extend(risk_violations)

    risk = RiskReport(
        ok=is_safe,
        evidence=evidence,
        violations=risk_violations,
        references=merged_risk_refs,
    )
    if pressured:
        evidence["probationPressured"] = True

    academic_violations, academic_refs, academic_evidence = violations_from_academic_risk_preview(
        academic_risk_analysis
    )
    if academic_violations:
        risk_violations = list(risk_violations) + academic_violations
        violations = list(violations) + academic_violations
        is_safe = False
        risk = RiskReport(
            ok=False,
            evidence=merge_academic_risk_evidence(evidence, academic_evidence),
            violations=risk_violations,
            references=list(dict.fromkeys([*merged_risk_refs, *academic_refs])),
        )
        references = list(dict.fromkeys([*references, *academic_refs]))
    elif academic_evidence:
        evidence = merge_academic_risk_evidence(evidence, academic_evidence)
        risk = RiskReport(
            ok=is_safe,
            evidence=evidence,
            violations=risk_violations,
            references=list(dict.fromkeys([*merged_risk_refs, *academic_refs])),
        )
        references = list(dict.fromkeys([*references, *academic_refs]))

    veto_agent: str | None = None
    if not feas_ok:
        veto_agent = "catalog_scout"
    elif not is_safe:
        veto_agent = "risk_sentinel"

    return HardConstraintResult(
        ok=feas_ok and is_safe,
        feasibility=feasibility,
        risk=risk,
        violations=violations,
        references=references,
        veto_agent=veto_agent,
    )


def hard_violation_messages(result: HardConstraintResult) -> list[str]:
    return violation_messages(result.violations)
