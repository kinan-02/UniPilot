"""Deterministic subtask expectation extraction (Phase 16)."""

from __future__ import annotations

from typing import Any

from app.agent.monitoring.schemas import SubtaskExpectation


def _default_expectations_for_subtask(subtask: dict[str, Any]) -> list[SubtaskExpectation]:
    subtask_id = str(subtask.get("id") or subtask.get("subtask_id") or "unknown")
    expectations: list[SubtaskExpectation] = [
        SubtaskExpectation(
            id=f"{subtask_id}_status_safe",
            subtask_id=subtask_id,
            kind="status",
            description="Subtask should complete or skip safely",
            expected_value={"allowed": ["completed", "skipped"]},
            severity_if_failed="warning",
        ),
        SubtaskExpectation(
            id=f"{subtask_id}_no_proposed_actions",
            subtask_id=subtask_id,
            kind="no_proposed_actions",
            description="Subtask must not produce proposed actions",
            expected_value=True,
            severity_if_failed="error",
        ),
        SubtaskExpectation(
            id=f"{subtask_id}_no_writes",
            subtask_id=subtask_id,
            kind="no_writes",
            description="Subtask must not perform writes",
            expected_value=True,
            severity_if_failed="error",
        ),
    ]

    if not subtask.get("requires_user_confirmation", False):
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_confirmation_not_required",
                subtask_id=subtask_id,
                kind="no_proposed_actions",
                description="Subtask marked requires_user_confirmation=false must stay action-free",
                expected_value=True,
                severity_if_failed="error",
            )
        )

    risk_level = str(subtask.get("risk_level") or "medium").strip().lower()
    if risk_level == "high":
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_confidence_threshold",
                subtask_id=subtask_id,
                kind="confidence_threshold",
                description="High-risk subtask should report non-zero confidence when completed",
                expected_value=0.1,
                severity_if_failed="warning",
            )
        )

    for index, criterion in enumerate(subtask.get("success_criteria") or []):
        text = str(criterion or "").strip()
        if not text:
            continue
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_success_{index}",
                subtask_id=subtask_id,
                kind="custom",
                description=f"Success criterion: {text}",
                expected_value=text,
                severity_if_failed="warning",
            )
        )

    for index, requirement in enumerate(subtask.get("validation_requirements") or []):
        text = str(requirement or "").strip()
        if not text:
            continue
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_validation_{index}",
                subtask_id=subtask_id,
                kind="custom",
                description=f"Validation requirement: {text}",
                expected_value=text,
                severity_if_failed="warning",
            )
        )

    return expectations


def _dynamic_agent_subtask_expectations(subtask: dict[str, Any]) -> list[SubtaskExpectation]:
    subtask_id = str(subtask.get("id") or "unknown")
    spec = subtask.get("dynamic_agent_spec") or {}
    policy = spec.get("validation_policy") if isinstance(spec, dict) else {}
    allow_missing = bool((policy or {}).get("allow_missing_context", True))
    risk_level = str((spec.get("risk_level") if isinstance(spec, dict) else None) or "medium")

    expectations = [
        SubtaskExpectation(
            id=f"{subtask_id}_dynamic_agent_status_safe",
            subtask_id=subtask_id,
            kind="status",
            description="Dynamic agent subtask should complete or skip safely in shadow mode",
            expected_value={"allowed": ["completed", "skipped", "needs_more_context"]},
            severity_if_failed="warning",
        ),
        SubtaskExpectation(
            id=f"{subtask_id}_dynamic_agent_no_proposed_actions",
            subtask_id=subtask_id,
            kind="no_proposed_actions",
            description="Dynamic agent must not produce proposed actions",
            expected_value=True,
            severity_if_failed="error",
        ),
        SubtaskExpectation(
            id=f"{subtask_id}_dynamic_agent_no_writes",
            subtask_id=subtask_id,
            kind="no_writes",
            description="Dynamic agent must not perform writes",
            expected_value=True,
            severity_if_failed="error",
        ),
    ]

    if not allow_missing:
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_dynamic_agent_missing_context_absent",
                subtask_id=subtask_id,
                kind="missing_context_absent",
                description="Dynamic agent should not report missing context when disallowed",
                expected_value=True,
                severity_if_failed="warning",
            )
        )

    if risk_level in {"medium", "high"}:
        expectations.append(
            SubtaskExpectation(
                id=f"{subtask_id}_dynamic_agent_confidence_threshold",
                subtask_id=subtask_id,
                kind="confidence_threshold",
                description="Dynamic agent should report confidence when risk is medium/high",
                expected_value=0.1,
                severity_if_failed="warning",
            )
        )

    return expectations


def expectations_from_planner_output(planner_output: dict[str, Any] | None) -> list[SubtaskExpectation]:
    return expectations_from_supervisor_plan(planner_output)


def expectations_from_supervisor_plan(planner_output: dict[str, Any] | None) -> list[SubtaskExpectation]:
    if not isinstance(planner_output, dict):
        return []

    expectations: list[SubtaskExpectation] = []
    subtasks = planner_output.get("subtasks")
    if not isinstance(subtasks, list):
        return expectations

    for raw in subtasks:
        if not isinstance(raw, dict):
            continue
        expectations.extend(_default_expectations_for_subtask(raw))
        if isinstance(raw.get("dynamic_agent_spec"), dict):
            expectations.extend(_dynamic_agent_subtask_expectations(raw))

    expectations.append(
        SubtaskExpectation(
            id="plan_no_writes",
            subtask_id="*",
            kind="no_writes",
            description="Entire plan must remain read-only in shadow diagnostics",
            expected_value=True,
            severity_if_failed="error",
        )
    )
    expectations.append(
        SubtaskExpectation(
            id="plan_no_proposed_actions",
            subtask_id="*",
            kind="no_proposed_actions",
            description="Plan execution must not create proposed actions",
            expected_value=True,
            severity_if_failed="error",
        )
    )
    return expectations


def build_expectations_for_monitor(
    *,
    planner_output: dict[str, Any] | None = None,
    preset: list[SubtaskExpectation] | None = None,
) -> list[SubtaskExpectation]:
    if preset:
        return list(preset)
    return expectations_from_supervisor_plan(planner_output)
