"""Deterministic plan snapshot builders (Phase 19)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent.planner.repair_schemas import PlanSnapshot

_RAW_CONTEXT_KEYS = frozenset(
    {
        "compiled_context",
        "raw_context",
        "context_pack",
        "prompt",
        "system_prompt",
        "user_prompt",
        "reasoning_passes",
        "chain_of_thought",
    }
)


def _compact_subtask(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id") or raw.get("subtask_id") or ""),
        "title": str(raw.get("title") or ""),
        "kind": str(raw.get("kind") or ""),
        "capability_name": str(raw.get("capability_name") or raw.get("capabilityName") or ""),
        "objective": str(raw.get("objective") or "")[:240],
    }


def _compact_assumptions(raw_assumptions: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_assumptions, list):
        return []
    compact: list[dict[str, Any]] = []
    for index, item in enumerate(raw_assumptions):
        if isinstance(item, str):
            compact.append(
                {
                    "id": f"assumption_{index}",
                    "statement": item[:240],
                    "kind": "unknown",
                    "provenance": "unknown",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "id": str(item.get("id") or f"assumption_{index}"),
                "statement": str(item.get("statement") or item.get("text") or "")[:240],
                "kind": str(item.get("kind") or "unknown"),
                "provenance": str(item.get("provenance") or "unknown"),
            }
        )
    return compact


def _success_criteria_from_subtasks(subtasks: list[dict[str, Any]]) -> list[str]:
    criteria: list[str] = []
    for subtask in subtasks:
        if not isinstance(subtask, dict):
            continue
        raw = subtask.get("success_criteria") or subtask.get("successCriteria") or []
        if isinstance(raw, list):
            criteria.extend(str(item)[:240] for item in raw if str(item).strip())
    return criteria[:12]


def build_plan_snapshot_from_planner_output(planner_output: dict[str, Any]) -> PlanSnapshot | None:
    """Build a compact snapshot from planner output. Never raises."""
    try:
        if not isinstance(planner_output, dict) or not planner_output:
            return None

        plan_id = str(planner_output.get("plan_id") or planner_output.get("planId") or "").strip()
        if not plan_id:
            return None

        user_goal = str(planner_output.get("user_goal") or planner_output.get("userGoal") or "").strip()
        if not user_goal:
            return None

        raw_subtasks = planner_output.get("subtasks") or []
        subtasks: list[dict[str, Any]] = []
        if isinstance(raw_subtasks, list):
            for item in raw_subtasks:
                if isinstance(item, dict):
                    subtasks.append(_compact_subtask(item))

        assumptions = _compact_assumptions(planner_output.get("assumptions") or [])
        success_criteria = _success_criteria_from_subtasks(raw_subtasks if isinstance(raw_subtasks, list) else [])
        validation_strategy = planner_output.get("validation_strategy") or planner_output.get("validationStrategy")
        replan_triggers: list[str] = []
        if isinstance(validation_strategy, list):
            replan_triggers = [str(item)[:120] for item in validation_strategy[:8]]

        source = str(planner_output.get("source") or "planner_output")
        if source not in {"planner_output", "fallback", "manual", "unknown"}:
            source = "planner_output"

        return PlanSnapshot(
            plan_id=plan_id,
            user_goal=user_goal[:500],
            normalized_request=user_goal[:500],
            planner_mode="cold",
            subtasks=subtasks,
            assumptions=assumptions,
            success_criteria=success_criteria,
            replan_triggers=replan_triggers,
            created_at=datetime.now(tz=UTC),
            source=source,  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001
        return None


def build_fallback_plan_snapshot(
    *,
    user_goal: str,
    workflow_name: str | None,
    intent: str | None,
) -> PlanSnapshot:
    """Deterministic fallback snapshot when no planner output exists."""
    goal = (user_goal or "").strip() or "unknown goal"
    workflow = (workflow_name or "general_academic_workflow").strip()
    primary_intent = (intent or "unknown_or_unsupported").strip()
    subtask_id = "run_legacy_workflow"
    return PlanSnapshot(
        plan_id=f"fallback-{uuid.uuid4().hex[:12]}",
        user_goal=goal[:500],
        normalized_request=goal[:500],
        planner_mode="cold",
        subtasks=[
            {
                "id": subtask_id,
                "title": "Run existing deterministic workflow",
                "kind": "execute",
                "capability_name": workflow,
                "objective": f"Serve intent {primary_intent} via {workflow}.",
            }
        ],
        assumptions=[
            {
                "id": "legacy_workflow_assumption",
                "statement": f"Deterministic workflow {workflow} satisfies the request.",
                "kind": "workflow_precondition",
                "provenance": "deterministic",
            }
        ],
        success_criteria=["Deterministic workflow completes without unsafe output."],
        replan_triggers=["workflow_failure", "unsafe_output"],
        created_at=datetime.now(tz=UTC),
        source="fallback",
    )


def snapshot_omits_raw_payloads(snapshot: PlanSnapshot) -> bool:
    """Helper for tests — ensure no raw context keys leaked into subtasks."""
    for subtask in snapshot.subtasks:
        for key in subtask:
            if key in _RAW_CONTEXT_KEYS:
                return False
    return True
