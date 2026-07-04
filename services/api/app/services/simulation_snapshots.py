"""Compact snapshots and deltas for simulation results."""

from __future__ import annotations

from typing import Any


def compact_graduation_progress(progress: dict[str, Any]) -> dict[str, Any]:
    missing = progress.get("missingRequirements") or []
    return {
        "completedCredits": progress.get("completedCredits"),
        "totalRequiredCredits": progress.get("totalRequiredCredits"),
        "creditsRemaining": progress.get("creditsRemaining"),
        "completionPercentage": progress.get("completionPercentage"),
        "statusSummary": progress.get("statusSummary"),
        "missingRequirementCount": len(missing),
    }


def compact_risk_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    summary = analysis.get("summary") or {}
    risks = analysis.get("risks") or []
    return {
        "highestSeverity": summary.get("highestSeverity"),
        "totalRisks": summary.get("totalRisks"),
        "topRisks": [
            {
                "severity": item.get("severity"),
                "title": item.get("title"),
                "riskType": item.get("riskType"),
            }
            for item in risks[:3]
            if isinstance(item, dict)
        ],
    }


def build_progress_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_completed = float(before.get("completedCredits") or 0)
    after_completed = float(after.get("completedCredits") or 0)
    before_remaining = float(before.get("creditsRemaining") or 0)
    after_remaining = float(after.get("creditsRemaining") or 0)
    return {
        "completedCreditsDelta": round(after_completed - before_completed, 2),
        "creditsRemainingDelta": round(after_remaining - before_remaining, 2),
        "completionPercentageDelta": round(
            float(after.get("completionPercentage") or 0)
            - float(before.get("completionPercentage") or 0),
            2,
        ),
        "missingRequirementCountDelta": int(after.get("missingRequirementCount") or 0)
        - int(before.get("missingRequirementCount") or 0),
    }


def build_risk_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if before is None and after is None:
        return None
    before_total = int((before or {}).get("totalRisks") or 0)
    after_total = int((after or {}).get("totalRisks") or 0)
    return {
        "totalRisksDelta": after_total - before_total,
        "highestSeverityBefore": (before or {}).get("highestSeverity"),
        "highestSeverityAfter": (after or {}).get("highestSeverity"),
    }


def build_template_summary(
    scenario_name: str,
    *,
    progress_delta: dict[str, Any],
    risk_delta: dict[str, Any] | None,
) -> str:
    parts = [f'Scenario "{scenario_name}" impact:']
    completed_delta = progress_delta.get("completedCreditsDelta", 0)
    remaining_delta = progress_delta.get("creditsRemainingDelta", 0)
    if completed_delta:
        parts.append(
            f"Completed credits change by {completed_delta:+.1f} "
            f"(remaining credits {remaining_delta:+.1f})."
        )
    else:
        parts.append("No change to completed credits.")

    if risk_delta is not None:
        risk_count_delta = risk_delta.get("totalRisksDelta", 0)
        if risk_count_delta:
            parts.append(f"Academic risk count changes by {risk_count_delta:+d}.")
        else:
            parts.append("Academic risk count is unchanged.")
    return " ".join(parts)
