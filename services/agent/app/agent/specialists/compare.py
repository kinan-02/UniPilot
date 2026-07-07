"""Deterministic workflow-vs-specialist result comparison (Phase 11).

Purely structural, deterministic comparison between a live deterministic
workflow's `AgentResponse` and a comparable specialist agent's compact
output summary (`specialists.output_summarizer.summarize_specialist_output`'s
shape). No LLM calls, no semantic text comparison, and no raw full
text/blocks/result are ever stored — only counts and type/key lists.

Diagnostic only: `WORKFLOW_TO_SPECIALIST_AGENT` is never used to route
production traffic, select a workflow, or influence the final response.
"""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentResponse
from app.agent.specialists.validation_schemas import (
    WORKFLOW_TO_SPECIALIST_AGENT,
    SpecialistValidationIssue,
    SpecialistValidationSeverity,
    WorkflowSpecialistComparison,
)

_LOW_CONFIDENCE_THRESHOLD = 0.6


def specialist_agent_for_workflow(workflow_name: str | None) -> str | None:
    """The Phase 11 comparable specialist agent name for `workflow_name`, or `None`.

    Deliberately excludes `general_academic_workflow` (operationally
    expensive/LLM-heavy — see Phase 8) and `transcript_import_workflow`/
    `semester_planning_workflow` (write/proposal workflows) — none of these
    are ever comparable in Phase 11.
    """
    if not workflow_name:
        return None
    return WORKFLOW_TO_SPECIALIST_AGENT.get(workflow_name)


def _issue(code: str, severity: SpecialistValidationSeverity, message: str, **details: Any) -> SpecialistValidationIssue:
    return SpecialistValidationIssue(code=code, severity=severity, message=message, details=details)


def _not_comparable(
    *, workflow_name: str | None, specialist_agent_name: str | None, code: str, message: str
) -> WorkflowSpecialistComparison:
    return WorkflowSpecialistComparison(
        workflow_name=workflow_name,
        specialist_agent_name=specialist_agent_name,
        comparable=False,
        safe_match=False,
        issues=[_issue(code, "info", message)],
    )


def compare_workflow_and_specialist(
    *,
    workflow_name: str | None,
    live_response: AgentResponse | None,
    specialist_output_summary: dict[str, Any] | None,
) -> WorkflowSpecialistComparison:
    """Compare a live `AgentResponse` against a comparable specialist's compact summary.

    Returns a compact, storage-safe comparison — never raw text/blocks or
    the specialist's raw `result` payload. `comparable=False` (with an
    informational issue explaining why) whenever: `workflow_name` has no
    Phase 11 comparable specialist, no specialist output/live response is
    available, or the summary is for a different specialist than expected.

    Never raises: any unexpected input degrades to a `comparable=False`,
    `safe_match=False` result with an error-severity issue instead of an
    exception escaping this function.
    """
    try:
        expected_agent_name = specialist_agent_for_workflow(workflow_name)
        actual_agent_name = (specialist_output_summary or {}).get("agentName")

        if expected_agent_name is None:
            return _not_comparable(
                workflow_name=workflow_name,
                specialist_agent_name=actual_agent_name,
                code="workflow_not_comparable",
                message=f"{workflow_name!r} has no comparable specialist agent in Phase 11.",
            )

        if specialist_output_summary is None or live_response is None:
            return _not_comparable(
                workflow_name=workflow_name,
                specialist_agent_name=expected_agent_name,
                code="no_comparable_specialist_result",
                message="No specialist output summary or live response is available to compare.",
            )

        if actual_agent_name != expected_agent_name:
            return _not_comparable(
                workflow_name=workflow_name,
                specialist_agent_name=actual_agent_name,
                code="specialist_agent_mismatch",
                message=f"Expected specialist {expected_agent_name!r}, got {actual_agent_name!r}.",
            )

        live_block_types = sorted({block.type for block in live_response.blocks})
        specialist_result_keys = sorted(specialist_output_summary.get("resultKeys") or [])
        live_warning_count = len(live_response.warnings)
        specialist_warning_count = int(specialist_output_summary.get("warningCount") or 0)
        live_source_count = len(live_response.used_sources)
        specialist_source_count = int(specialist_output_summary.get("sourceCount") or 0)
        has_proposed_actions = bool(specialist_output_summary.get("hasProposedActions"))
        missing_context_count = int(specialist_output_summary.get("missingContextCount") or 0)
        confidence = specialist_output_summary.get("confidence")

        issues: list[SpecialistValidationIssue] = []
        if has_proposed_actions:
            issues.append(
                _issue(
                    "specialist_proposed_actions_detected",
                    "error",
                    "Specialist output has (or reported) proposed actions.",
                )
            )
        if missing_context_count > 0:
            issues.append(
                _issue(
                    "specialist_missing_context",
                    "warning",
                    "Specialist reported missing context.",
                    missingContextCount=missing_context_count,
                )
            )
        if confidence is None or float(confidence) < _LOW_CONFIDENCE_THRESHOLD:
            issues.append(
                _issue(
                    "low_specialist_confidence",
                    "warning",
                    "Specialist confidence is low or missing.",
                    confidence=confidence,
                )
            )
        if not specialist_result_keys:
            issues.append(
                _issue("specialist_empty_result", "warning", "Specialist returned an empty result.")
            )

        safe_match = not issues

        return WorkflowSpecialistComparison(
            workflow_name=workflow_name,
            specialist_agent_name=actual_agent_name,
            comparable=True,
            safe_match=safe_match,
            live_block_types=live_block_types,
            specialist_result_keys=specialist_result_keys,
            live_warning_count=live_warning_count,
            specialist_warning_count=specialist_warning_count,
            live_source_count=live_source_count,
            specialist_source_count=specialist_source_count,
            issues=issues,
        )
    except Exception:  # noqa: BLE001 — must never raise into a live turn
        return WorkflowSpecialistComparison(
            workflow_name=workflow_name,
            specialist_agent_name=None,
            comparable=False,
            safe_match=False,
            issues=[_issue("specialist_comparison_error", "error", "Comparison failed unexpectedly.")],
        )
