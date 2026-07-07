"""Deterministic plan assumption extraction (Phase 16).

Never calls an LLM and never invents new facts — only structures information
already present in planner output, task understanding, or conversation memory.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.monitoring.schemas import PlanAssumption

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("_", value.strip().lower()).strip("_") or "item"


def assumptions_from_conversation_assumptions(items: list[str] | None) -> list[PlanAssumption]:
    assumptions: list[PlanAssumption] = []
    for index, raw in enumerate(items or []):
        statement = str(raw or "").strip()
        if not statement:
            continue
        assumptions.append(
            PlanAssumption(
                id=f"conv_assumption_{index}_{_slug(statement)[:24]}",
                kind="user_preference",
                statement=statement,
                provenance="assumed",
                confidence=0.45,
                invalidation_signals=["user_correction", "contradicting_evidence"],
                consequence_if_wrong="medium",
            )
        )
    return assumptions


def assumptions_from_task_understanding(task_understanding: dict[str, Any] | None) -> list[PlanAssumption]:
    if not isinstance(task_understanding, dict):
        return []

    assumptions: list[PlanAssumption] = []

    user_goal = str(task_understanding.get("user_goal") or task_understanding.get("normalized_request") or "").strip()
    if user_goal:
        assumptions.append(
            PlanAssumption(
                id="tu_user_goal",
                kind="workflow_precondition",
                statement=f"User goal is: {user_goal}",
                provenance="llm_interpreted" if task_understanding.get("source") == "llm_reasoning_block" else "inferred",
                confidence=float(task_understanding.get("overall_confidence") or 0.6),
                invalidation_signals=["goal_drift", "user_correction"],
                consequence_if_wrong="high",
            )
        )

    primary_intent = str(task_understanding.get("primary_intent") or "").strip()
    if primary_intent:
        assumptions.append(
            PlanAssumption(
                id="tu_primary_intent",
                kind="workflow_precondition",
                statement=f"Primary intent is {primary_intent}",
                provenance="deterministic" if task_understanding.get("source") == "deterministic_fallback" else "inferred",
                confidence=float(task_understanding.get("intent_confidence") or 0.55),
                invalidation_signals=["intent_mismatch", "goal_drift"],
                consequence_if_wrong="high",
            )
        )

    for index, missing in enumerate(task_understanding.get("missing_context") or []):
        text = str(missing or "").strip()
        if not text:
            continue
        assumptions.append(
            PlanAssumption(
                id=f"tu_missing_context_{index}",
                kind="context_availability",
                statement=f"Required context may be missing: {text}",
                provenance="inferred",
                confidence=0.5,
                invalidation_signals=["context_recovered", "context_still_missing"],
                consequence_if_wrong="medium",
            )
        )

    write_risk = str(task_understanding.get("write_risk") or "none").strip().lower()
    if write_risk in {"possible", "explicit"}:
        assumptions.append(
            PlanAssumption(
                id="tu_write_risk",
                kind="safety_constraint",
                statement=f"Write risk is {write_risk}",
                provenance="inferred",
                confidence=0.7,
                invalidation_signals=["unsafe_output", "proposed_action_detected"],
                consequence_if_wrong="high",
            )
        )

    for index, assumption_text in enumerate(task_understanding.get("assumptions") or []):
        text = str(assumption_text or "").strip()
        if not text:
            continue
        assumptions.append(
            PlanAssumption(
                id=f"tu_assumption_{index}",
                kind="academic_fact",
                statement=text,
                provenance="assumed",
                confidence=0.45,
                invalidation_signals=["contradicting_evidence"],
                consequence_if_wrong="medium",
            )
        )

    return assumptions


def assumptions_from_planner_output(planner_output: dict[str, Any] | None) -> list[PlanAssumption]:
    if not isinstance(planner_output, dict):
        return []

    assumptions: list[PlanAssumption] = []

    user_goal = str(planner_output.get("user_goal") or "").strip()
    if user_goal:
        assumptions.append(
            PlanAssumption(
                id="planner_user_goal",
                kind="workflow_precondition",
                statement=f"Plan user goal is: {user_goal}",
                provenance="deterministic",
                confidence=0.85,
                invalidation_signals=["goal_drift"],
                consequence_if_wrong="high",
            )
        )

    execution_mode = str(planner_output.get("execution_mode") or "").strip()
    if execution_mode:
        assumptions.append(
            PlanAssumption(
                id="planner_execution_mode",
                kind="workflow_precondition",
                statement=f"Execution mode is {execution_mode}",
                provenance="deterministic",
                confidence=0.8,
                invalidation_signals=["execution_mode_unsupported", "goal_drift"],
                consequence_if_wrong="medium",
            )
        )

    for index, text in enumerate(planner_output.get("assumptions") or []):
        statement = str(text or "").strip()
        if not statement:
            continue
        assumptions.append(
            PlanAssumption(
                id=f"planner_assumption_{index}",
                kind="academic_fact",
                statement=statement,
                provenance="assumed",
                confidence=0.5,
                invalidation_signals=["contradicting_evidence"],
                consequence_if_wrong="medium",
            )
        )

    for index, missing in enumerate(planner_output.get("missing_context") or []):
        text = str(missing or "").strip()
        if not text:
            continue
        assumptions.append(
            PlanAssumption(
                id=f"planner_missing_context_{index}",
                kind="context_availability",
                statement=f"Plan expects missing context: {text}",
                provenance="deterministic",
                confidence=0.75,
                invalidation_signals=["context_still_missing"],
                consequence_if_wrong="medium",
            )
        )

    write_risk = str(planner_output.get("write_risk") or "none").strip().lower()
    if write_risk != "none":
        assumptions.append(
            PlanAssumption(
                id="planner_write_risk",
                kind="safety_constraint",
                statement=f"Planner write risk is {write_risk}",
                provenance="deterministic",
                confidence=0.8,
                invalidation_signals=["unsafe_output"],
                consequence_if_wrong="high",
            )
        )

    if planner_output.get("requires_user_confirmation"):
        assumptions.append(
            PlanAssumption(
                id="planner_requires_confirmation",
                kind="safety_constraint",
                statement="Plan requires user confirmation before any write/proposal path",
                provenance="deterministic",
                confidence=0.9,
                invalidation_signals=["proposed_action_detected"],
                consequence_if_wrong="high",
            )
        )

    fallback = str(planner_output.get("fallback_workflow_name") or "").strip()
    if fallback:
        assumptions.append(
            PlanAssumption(
                id="planner_fallback_workflow",
                kind="tool_availability",
                statement=f"Fallback workflow available: {fallback}",
                provenance="deterministic",
                confidence=0.7,
                invalidation_signals=["fallback_unavailable"],
                consequence_if_wrong="low",
            )
        )

    return assumptions


def build_assumptions_for_monitor(
    *,
    planner_output: dict[str, Any] | None = None,
    task_understanding: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    preset: list[PlanAssumption] | None = None,
) -> list[PlanAssumption]:
    """Merge deterministic assumption sources, preserving caller-supplied preset first."""
    merged: list[PlanAssumption] = list(preset or [])
    seen_ids = {item.id for item in merged}
    for source in (
        assumptions_from_planner_output(planner_output),
        assumptions_from_task_understanding(task_understanding),
        assumptions_from_conversation_assumptions(conversation_assumptions),
    ):
        for assumption in source:
            if assumption.id in seen_ids:
                continue
            merged.append(assumption)
            seen_ids.add(assumption.id)
    return merged
