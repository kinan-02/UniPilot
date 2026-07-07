"""Compact `supervisorValidation` metadata shape (Phase 8).

Converts a `SupervisorValidationResult` into the small, storage-safe dict
attached to `agent_runs.retrievalMetadata.supervisorValidation` — never the
raw workflow response, raw supervisor output, raw compiled context, or raw
prompts. Purely deterministic: no LLM calls, no I/O.
"""

from __future__ import annotations

from typing import Any

from app.agent.supervisor.validation_schemas import SupervisorValidationResult

_MAX_ISSUES_LISTED = 20
_MAX_WARNINGS_LISTED = 10


def build_supervisor_validation_metadata(result: SupervisorValidationResult) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.supervisorValidation` — see module docstring."""
    comparison = result.comparison

    return {
        "status": result.status,
        "safeToPromote": result.safe_to_promote,
        "liveWorkflowName": comparison.live_workflow_name if comparison else None,
        "shadowPlanId": comparison.shadow_plan_id if comparison else None,
        "shadowStatus": comparison.shadow_status if comparison else None,
        "safeMatch": comparison.safe_match if comparison else False,
        "issues": [
            {"code": issue.code, "severity": issue.severity} for issue in result.issues[:_MAX_ISSUES_LISTED]
        ],
        "liveBlockTypes": comparison.live_block_types if comparison else [],
        "shadowBlockTypes": comparison.shadow_block_types if comparison else [],
        "liveBlockCount": comparison.live_block_count if comparison else 0,
        "shadowBlockCount": comparison.shadow_block_count if comparison else 0,
        "liveWarningCount": comparison.live_warning_count if comparison else 0,
        "shadowWarningCount": comparison.shadow_warning_count if comparison else 0,
        "liveProposedActionCount": comparison.live_proposed_action_count if comparison else 0,
        "shadowProposedActionCount": comparison.shadow_proposed_action_count if comparison else 0,
        "liveSourceCount": comparison.live_source_count if comparison else 0,
        "shadowSourceCount": comparison.shadow_source_count if comparison else 0,
        "shadowFailedSubtasks": comparison.shadow_failed_subtasks if comparison else [],
        "shadowSkippedSubtasks": comparison.shadow_skipped_subtasks if comparison else [],
        "warnings": list(result.warnings[:_MAX_WARNINGS_LISTED]),
    }
