"""Compact specialist output validation + workflow-vs-specialist compare
diagnostics (Phase 11).

`build_specialist_compare_diagnostics` is the entry point
`supervisor.post_context_runner` calls: it scans an already-computed
`SupervisorRunOutput` for specialist-agent subtask results, validates each
one (`specialists.validation.validate_specialist_output`), optionally
compares each against the live workflow's `AgentResponse`
(`specialists.compare.compare_workflow_and_specialist`), and returns a
`SpecialistCompareDiagnostics` aggregate — or `None` when no specialist
output exists to look at. `build_specialist_validation_metadata` then
converts that aggregate into the compact dict attached to
`agent_runs.retrievalMetadata.specialistValidation`.

Diagnostic only: nothing here executes anything, selects a workflow, or
changes the final response. Never calls an LLM.
"""

from __future__ import annotations

from typing import Any, get_args

from app.agent.schemas import AgentResponse
from app.agent.specialists.compare import compare_workflow_and_specialist
from app.agent.specialists.schemas import SpecialistAgentKind
from app.agent.specialists.validation import validate_specialist_output
from app.agent.specialists.validation_schemas import SpecialistCompareDiagnostics

_KNOWN_SPECIALIST_AGENT_NAMES: frozenset[str] = frozenset(get_args(SpecialistAgentKind))
_MAX_ISSUES_LISTED = 20


def _is_specialist_result_summary(result_summary: dict[str, Any] | None) -> bool:
    """`True` only for the compact shape `output_summarizer.summarize_specialist_output`
    produces — distinguishes a specialist's own summary from a generic
    dry-run/workflow-adapter summary that happens to share a capability name
    coincidence (defense in depth; capability-name filtering already does
    most of the work)."""
    return isinstance(result_summary, dict) and "agentName" in result_summary


def build_specialist_compare_diagnostics(
    *,
    shadow_run_output: Any | None,
    live_workflow_name: str | None = None,
    live_response: AgentResponse | None = None,
    validation_enabled: bool = True,
    compare_enabled: bool = True,
) -> SpecialistCompareDiagnostics | None:
    """Validate (and, when enabled, compare) every specialist subtask output
    found in `shadow_run_output`. Returns `None` when there is nothing to
    look at (no `shadow_run_output`, or it contains no specialist-agent
    subtask results) — never raises.
    """
    if shadow_run_output is None:
        return None

    try:
        specialist_records = [
            record
            for record in shadow_run_output.subtask_records
            if record.capability_name in _KNOWN_SPECIALIST_AGENT_NAMES
            and _is_specialist_result_summary(record.result_summary)
        ]
    except Exception:  # noqa: BLE001 — malformed shadow_run_output must never raise here
        return None

    if not specialist_records:
        return None

    validation_results = [
        validate_specialist_output(
            record.result_summary, subtask_id=record.subtask_id, validation_enabled=validation_enabled
        )
        for record in specialist_records
    ]

    comparisons = []
    if compare_enabled:
        comparisons = [
            compare_workflow_and_specialist(
                workflow_name=live_workflow_name,
                live_response=live_response,
                specialist_output_summary=record.result_summary,
            )
            for record in specialist_records
        ]

    issues = [issue for result in validation_results for issue in result.issues]
    issues += [issue for comparison in comparisons for issue in comparison.issues]

    if validation_results and all(result.status == "skipped" for result in validation_results) and not comparisons:
        status = "skipped"
    elif any(issue.severity == "error" for issue in issues):
        status = "failed"
    elif any(issue.severity == "warning" for issue in issues):
        status = "passed_with_warnings"
    else:
        status = "passed"

    safe_to_consider = (
        status == "passed"
        and bool(validation_results)
        and all(result.status == "passed" for result in validation_results)
        and all(comparison.safe_match for comparison in comparisons if comparison.comparable)
    )

    return SpecialistCompareDiagnostics(
        status=status,
        safe_to_consider=safe_to_consider,
        comparisons=comparisons,
        validation_results=validation_results,
    )


def build_specialist_validation_metadata(diagnostics: SpecialistCompareDiagnostics) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.specialistValidation` — see module docstring."""
    issues = [issue for result in diagnostics.validation_results for issue in result.issues]
    issues += [issue for comparison in diagnostics.comparisons for issue in comparison.issues]

    return {
        "status": diagnostics.status,
        "safeToConsider": diagnostics.safe_to_consider,
        "validationCount": len(diagnostics.validation_results),
        "comparisonCount": len(diagnostics.comparisons),
        "issues": [
            {"code": issue.code, "severity": issue.severity} for issue in issues[:_MAX_ISSUES_LISTED]
        ],
        "agents": sorted({result.agent_name for result in diagnostics.validation_results}),
        "comparisons": [
            {
                "workflowName": comparison.workflow_name,
                "specialistAgentName": comparison.specialist_agent_name,
                "comparable": comparison.comparable,
                "safeMatch": comparison.safe_match,
                "liveBlockTypes": comparison.live_block_types,
                "specialistResultKeys": comparison.specialist_result_keys,
                "liveWarningCount": comparison.live_warning_count,
                "specialistWarningCount": comparison.specialist_warning_count,
            }
            for comparison in diagnostics.comparisons
        ],
    }
