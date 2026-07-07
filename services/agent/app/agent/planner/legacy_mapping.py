"""Map `task_planner.py`'s deterministic workflow names to Phase 4 capability names.

Today the workflow name `task_planner.build_task_plan` picks and the
capability name the Phase 4 `CapabilityRegistry` uses for that same workflow
happen to be identical strings — but this module makes that an explicit,
tested mapping rather than an implicit assumption baked into the planner.
If a workflow is ever renamed or split, only this module (and the registry)
need to change.

This module never talks to an LLM and never touches the database.
"""

from __future__ import annotations

from typing import Any

# Mirrors `app.agent.task_planner._WORKFLOW_BY_INTENT`'s value set and
# `app.agent.capabilities.default_registry`'s workflow capability names.
# Kept as an explicit dict (not `{name: name for name in ...}`) so a future
# divergence between workflow name and capability name is a one-line change
# here, not a silent behavior difference.
_WORKFLOW_TO_CAPABILITY_NAME: dict[str, str] = {
    "graduation_progress_workflow": "graduation_progress_workflow",
    "course_question_workflow": "course_question_workflow",
    "transcript_import_workflow": "transcript_import_workflow",
    "semester_planning_workflow": "semester_planning_workflow",
    "requirement_explanation_workflow": "requirement_explanation_workflow",
    "general_academic_workflow": "general_academic_workflow",
}

_DEFAULT_CAPABILITY_NAME = "general_academic_workflow"


def legacy_workflow_to_capability_name(workflow_name: str | None) -> str:
    """Map a `TaskPlan.workflow` name to its Phase 4 capability name.

    Falls back to `general_academic_workflow` for an unrecognized workflow
    name rather than raising — this is a diagnostic-only lookup, never a
    routing decision.
    """
    if not workflow_name:
        return _DEFAULT_CAPABILITY_NAME
    return _WORKFLOW_TO_CAPABILITY_NAME.get(workflow_name, _DEFAULT_CAPABILITY_NAME)


def build_legacy_workflow_plan_summary(
    *,
    workflow_name: str,
    read_only: bool,
    requires_confirmation: bool,
    primary_intent: str,
) -> dict[str, Any]:
    """Compact summary of the current deterministic `TaskPlan`.

    Fed to the LLM planner (so it can prefer the existing deterministic
    workflow when it already solves the task) and used to build the
    deterministic fallback plan when the LLM planner is disabled/unavailable.
    """
    return {
        "workflow": workflow_name,
        "capability_name": legacy_workflow_to_capability_name(workflow_name),
        "read_only": read_only,
        "requires_confirmation": requires_confirmation,
        "primary_intent": primary_intent,
    }
