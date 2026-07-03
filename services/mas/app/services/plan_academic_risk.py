"""Map API academic-risk preview results into MAS risk signals."""

from __future__ import annotations

from typing import Any

from app.orchestrator.artifacts import Violation, ViolationType

HARD_VETO_RISK_TYPES = frozenset(
    {
        "credit_overload",
        "unmet_prerequisites",
        "course_already_completed",
        "empty_plan",
        "unknown_planned_course",
        "out_of_scope_course",
    }
)

_VIOLATION_TYPE_BY_RISK = {
    "credit_overload": ViolationType.CREDIT_OVERLOAD,
    "unmet_prerequisites": ViolationType.PREREQ_MISSING,
    "course_already_completed": ViolationType.OTHER,
    "empty_plan": ViolationType.EMPTY_PLAN,
    "unknown_planned_course": ViolationType.COURSE_NOT_IN_CATALOG,
    "out_of_scope_course": ViolationType.COURSE_NOT_IN_CATALOG,
}


def violations_from_academic_risk_preview(
    analysis: dict[str, Any] | None,
) -> tuple[list[Violation], list[str], dict[str, Any]]:
    """Return hard violations, references, and evidence from a risk preview."""
    if not analysis:
        return [], [], {}

    violations: list[Violation] = []
    references: list[str] = []
    risks = analysis.get("risks") or []
    summary = analysis.get("summary") or {}

    for risk in risks:
        if not isinstance(risk, dict):
            continue
        risk_type = str(risk.get("riskType") or "")
        severity = str(risk.get("severity") or "")
        references.append(f"academic_risk:{risk_type}:{severity}")
        if severity != "high" or risk_type not in HARD_VETO_RISK_TYPES:
            continue

        related_ids = [
            str(course_id)
            for course_id in (risk.get("relatedCourseIds") or [])
            if course_id
        ]
        violations.append(
            Violation(
                type=_VIOLATION_TYPE_BY_RISK.get(risk_type, ViolationType.OTHER),
                message=str(risk.get("explanation") or risk.get("title") or risk_type),
                course_ids=related_ids,
            )
        )

    evidence = {
        "academicRiskSummary": summary,
        "academicRiskCount": len(risks),
        "highSeverityCount": summary.get("highSeverityCount"),
    }
    if violations:
        references.append(f"academic_risk:hard_vetoes={len(violations)}")
    else:
        references.append("academic_risk:no_hard_vetoes")

    return violations, references, evidence


def merge_academic_risk_evidence(
    evidence: dict[str, Any],
    academic_evidence: dict[str, Any],
) -> dict[str, Any]:
    if not academic_evidence:
        return evidence
    return {**evidence, "academicRisk": academic_evidence}
