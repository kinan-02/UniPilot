"""Human-readable explanations for rejected planner variants."""

from __future__ import annotations

from typing import Any


def _evaluation_map(variant_evaluations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for evaluation in variant_evaluations:
        if not isinstance(evaluation, dict):
            continue
        variant = str(evaluation.get("variant") or "")
        if variant:
            mapped[variant] = evaluation
    return mapped


def _hard_failure_reason(evaluation: dict[str, Any]) -> str | None:
    if evaluation.get("hard_ok") is not False:
        return None
    progress = evaluation.get("progress_report") or {}
    preference = evaluation.get("preference_report") or {}
    critiques = list(progress.get("critiques") or []) + list(preference.get("critiques") or [])
    if critiques:
        first = critiques[0]
        if isinstance(first, dict) and first.get("message"):
            return str(first["message"])
    return "Failed hard feasibility or workload constraints."


def build_counterfactual_explanations(
    *,
    chosen_variant: str,
    chosen_utility: float | None,
    arbitration: dict[str, Any] | None,
    variant_evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Explain why non-chosen variants were not committed."""
    explanations: list[dict[str, Any]] = []
    by_variant = _evaluation_map(variant_evaluations)
    rejected = list((arbitration or {}).get("rejected_alternatives") or [])

    for entry in rejected:
        if not isinstance(entry, dict):
            continue
        variant = str(entry.get("variant") or "")
        if not variant or variant == chosen_variant:
            continue
        utility = entry.get("utility")
        evaluation = by_variant.get(variant, {})
        hard_reason = _hard_failure_reason(evaluation)
        if hard_reason:
            reason = hard_reason
        elif chosen_utility is not None and isinstance(utility, (int, float)):
            reason = (
                f"Lower arbitration utility ({utility} vs committed {chosen_utility:.4f})."
            )
        else:
            reason = "Did not win utility arbitration against the committed variant."

        explanations.append(
            {
                "variant": variant,
                "courseIds": list(entry.get("course_ids") or []),
                "utility": utility,
                "hardOk": evaluation.get("hard_ok", True),
                "reason": reason,
            }
        )

    for variant, evaluation in by_variant.items():
        if variant == chosen_variant:
            continue
        if any(item["variant"] == variant for item in explanations):
            continue
        hard_reason = _hard_failure_reason(evaluation)
        if hard_reason:
            explanations.append(
                {
                    "variant": variant,
                    "courseIds": list(evaluation.get("course_ids") or []),
                    "utility": None,
                    "hardOk": False,
                    "reason": hard_reason,
                }
            )

    return explanations
