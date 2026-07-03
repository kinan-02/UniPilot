"""Deterministic plan risk checks for the Risk Sentinel agent."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import sum_plan_credits

DEFAULT_MAX_CREDITS = 18.0


def resolve_max_credits(user_context: dict[str, Any]) -> float:
    preferences = user_context.get("preferences") or {}
    raw = preferences.get("maxCreditsPerSemester")
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    constraints = user_context.get("constraints") or {}
    constraint_max = constraints.get("maxCredits")
    if isinstance(constraint_max, (int, float)) and constraint_max > 0:
        return float(constraint_max)
    return DEFAULT_MAX_CREDITS


def evaluate_credit_overload(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    max_credits: float,
    user_context: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Return (is_safe, evidence, references).

    A credit overload is a hard veto for the Risk Sentinel.
    """
    total_credits = sum_plan_credits(engine, course_ids, user_context=user_context)
    references = [f"credits:total={total_credits}", f"credits:max={max_credits}"]
    evidence = {
        "totalCredits": total_credits,
        "maxCredits": max_credits,
        "courseCount": len(course_ids),
    }

    if total_credits > max_credits:
        evidence["excessCredits"] = round(total_credits - max_credits, 2)
        return False, evidence, references

    return True, evidence, references


def evaluate_probation_pressure(
    user_context: dict[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Soft probation signal from profile preferences.

    Returns (is_pressured, evidence, references). Never hard-vetoes by itself.
    """
    preferences = user_context.get("preferences") or {}
    gpa = preferences.get("currentGpa")
    threshold = preferences.get("probationGpaThreshold", 2.0)
    references: list[str] = []
    evidence: dict[str, Any] = {"currentGpa": gpa, "probationGpaThreshold": threshold}

    if not isinstance(gpa, (int, float)):
        references.append("probation:gpa_unknown")
        return False, evidence, references

    evidence["currentGpa"] = float(gpa)
    references.append(f"probation:gpa={gpa}")
    pressured = float(gpa) < float(threshold)
    evidence["pressured"] = pressured
    return pressured, evidence, references
