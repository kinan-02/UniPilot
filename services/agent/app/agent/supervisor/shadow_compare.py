"""Deterministic shadow-vs-live result comparison (Phase 7/8).

Purely structural, deterministic comparison between a live workflow's
`AgentResponse` and a shadow-executed run. No LLM calls, no semantic text
comparison, and no raw full text/blocks are ever stored — only counts and
type lists.

`compare_live_and_shadow_result` (Phase 7) compares a live response against
one shadow capability's compact output summary — a standalone utility, not
wired into the live orchestrator.

`build_comparison_summary` (Phase 8) is the run-level equivalent used by
`supervisor.post_context_runner`: it compares a live response against an
entire `SupervisorRunOutput` (potentially multiple subtasks), producing a
typed `ShadowComparisonSummary` for `supervisor.validation` to reason over.
"""

from __future__ import annotations

from typing import Any

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.schemas import AgentResponse
from app.agent.supervisor.schemas import SupervisorRunOutput
from app.agent.supervisor.validation_schemas import ShadowComparisonSummary

_MAX_ISSUES_LISTED = 20


def compare_live_and_shadow_result(
    *,
    live_workflow_name: str,
    live_response: AgentResponse,
    shadow_capability_name: str,
    shadow_output_summary: dict[str, Any],
) -> dict[str, Any]:
    """Compare a live `AgentResponse` against a shadow handler's compact summary.

    Returns a compact, storage-safe comparison dict — never the raw live
    response text/blocks, and never anything from the shadow side beyond
    what `output_summarizer` already reduced it to.
    """
    live_block_types = sorted({block.type for block in live_response.blocks})
    shadow_block_types = sorted(set(shadow_output_summary.get("blockTypes") or []))

    live_warning_count = len(live_response.warnings)
    shadow_warning_count = int(shadow_output_summary.get("warningCount") or 0)

    live_proposed_action_count = len(live_response.proposed_actions)
    shadow_proposed_action_count = int(shadow_output_summary.get("proposedActionCount") or 0)

    issues: list[str] = []
    if live_workflow_name != shadow_capability_name:
        issues.append("workflow_capability_name_mismatch")
    if live_block_types != shadow_block_types:
        issues.append("block_types_mismatch")
    if live_proposed_action_count != shadow_proposed_action_count:
        issues.append("proposed_action_count_mismatch")
    if shadow_proposed_action_count > 0:
        # A shadow-executed capability must never have produced a proposed
        # action at all -- this is a hard safety signal, not just a diff.
        issues.append("shadow_produced_proposed_actions")

    return {
        "liveWorkflowName": live_workflow_name,
        "shadowCapabilityName": shadow_capability_name,
        "liveBlockTypes": live_block_types,
        "shadowBlockTypes": shadow_block_types,
        "liveWarningCount": live_warning_count,
        "shadowWarningCount": shadow_warning_count,
        "liveProposedActionCount": live_proposed_action_count,
        "shadowProposedActionCount": shadow_proposed_action_count,
        "safeMatch": not issues,
        "issues": issues[:_MAX_ISSUES_LISTED],
    }


def _aggregate_shadow_output_summaries(
    run_output: SupervisorRunOutput,
    *,
    capability_registry: CapabilityRegistry | None,
) -> tuple[set[str], int, int, int, int, list[str]]:
    """Aggregate every subtask's `result_summary` into run-level counters.

    Returns `(block_types, block_count, warning_count, proposed_action_count,
    source_count, unsafe_capabilities_attempted)`. Only ever reads the
    compact `result_summary` dicts already produced by
    `output_summarizer`/the Phase 6 dry-run handlers — never the underlying
    `AgentResponse` or compiled context.
    """
    block_types: set[str] = set()
    block_count = 0
    warning_count = 0
    proposed_action_count = 0
    source_count = 0
    unsafe_attempted: list[str] = []

    for record in run_output.subtask_records:
        summary = record.result_summary or {}
        block_types.update(summary.get("blockTypes") or [])
        block_count += int(summary.get("blockCount") or 0)
        warning_count += int(summary.get("warningCount") or 0)
        proposed_action_count += int(summary.get("proposedActionCount") or 0)
        source_count += int(summary.get("sourceCount") or 0)

        if not summary.get("shadowExecuted"):
            continue

        # Defense in depth: a subtask that genuinely ran for real
        # (`shadowExecuted=True`) is flagged as an unsafe attempt either
        # when it visibly produced/attempted proposed actions, or — when a
        # `capability_registry` is supplied — when the capability's own
        # declared `side_effect_level` isn't `"none"` (the ground truth the
        # runtime's `safety.can_shadow_execute_capability` gate is built
        # from). Both checks are independent so this never depends on a
        # registry being passed in.
        side_effect_level = "none"
        if capability_registry is not None:
            descriptor = capability_registry.get(record.capability_name)
            if descriptor is not None:
                side_effect_level = descriptor.execution.side_effect_level
        looks_unsafe = bool(summary.get("hasProposedActions")) or side_effect_level != "none"
        if looks_unsafe:
            unsafe_attempted.append(record.capability_name)

    return block_types, block_count, warning_count, proposed_action_count, source_count, unsafe_attempted


def build_comparison_summary(
    *,
    live_workflow_name: str | None,
    live_response: AgentResponse | None,
    shadow_run_output: SupervisorRunOutput | None,
    capability_registry: CapabilityRegistry | None = None,
) -> ShadowComparisonSummary:
    """Build a typed, run-level `ShadowComparisonSummary`.

    Safe with any combination of missing inputs: a `None` `live_response` or
    `shadow_run_output` simply yields zeroed-out counts for that side rather
    than raising — callers (e.g. `post_context_runner`) may call this even
    when the shadow run itself failed early.

    Never stores raw text, raw blocks, raw sources, or proposed-action
    payloads — only counts, type lists, and status strings, exactly like
    `compare_live_and_shadow_result` above.
    """
    live_block_types: list[str] = sorted({block.type for block in live_response.blocks}) if live_response else []
    live_block_count = len(live_response.blocks) if live_response else 0
    live_warning_count = len(live_response.warnings) if live_response else 0
    live_proposed_action_count = len(live_response.proposed_actions) if live_response else 0
    live_source_count = len(live_response.used_sources) if live_response else 0

    shadow_block_types: set[str] = set()
    shadow_block_count = shadow_warning_count = shadow_proposed_action_count = shadow_source_count = 0
    unsafe_attempted: list[str] = []
    shadow_status: str | None = None
    shadow_plan_id: str | None = None
    shadow_failed_subtasks: list[str] = []
    shadow_skipped_subtasks: list[str] = []

    if shadow_run_output is not None:
        shadow_status = shadow_run_output.status
        shadow_plan_id = shadow_run_output.plan_id
        shadow_failed_subtasks = list(shadow_run_output.failed_subtasks)
        shadow_skipped_subtasks = list(shadow_run_output.skipped_subtasks)
        (
            shadow_block_types,
            shadow_block_count,
            shadow_warning_count,
            shadow_proposed_action_count,
            shadow_source_count,
            unsafe_attempted,
        ) = _aggregate_shadow_output_summaries(shadow_run_output, capability_registry=capability_registry)

    # A conservative, purely structural "do these look like the same kind of
    # result" signal — `validation.py` is the actual source of truth for
    # pass/fail/severity; this is only a quick hint for consumers that only
    # look at the comparison object directly.
    safe_match = (
        not unsafe_attempted
        and shadow_proposed_action_count == 0
        and live_proposed_action_count == shadow_proposed_action_count
    )

    return ShadowComparisonSummary(
        live_workflow_name=live_workflow_name,
        shadow_plan_id=shadow_plan_id,
        shadow_status=shadow_status,
        live_block_types=live_block_types,
        shadow_block_types=sorted(shadow_block_types),
        live_block_count=live_block_count,
        shadow_block_count=shadow_block_count,
        live_warning_count=live_warning_count,
        shadow_warning_count=shadow_warning_count,
        live_proposed_action_count=live_proposed_action_count,
        shadow_proposed_action_count=shadow_proposed_action_count,
        live_source_count=live_source_count,
        shadow_source_count=shadow_source_count,
        shadow_failed_subtasks=shadow_failed_subtasks,
        shadow_skipped_subtasks=shadow_skipped_subtasks,
        unsafe_capabilities_attempted=unsafe_attempted,
        safe_match=safe_match,
    )
