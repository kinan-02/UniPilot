"""Deterministic Phase 8 validators over a live-vs-shadow comparison.

Every validator here is pure, synchronous, and deterministic — no LLM calls,
no I/O, no database access. `validate_shadow_run` never raises: a bug in a
single validator degrades to that validator being skipped, not to the whole
call failing (mirrors every other Phase 6/7 supervisor diagnostic call site).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent.supervisor.schemas import SupervisorRunOutput
from app.agent.supervisor.validation_schemas import (
    ShadowComparisonSummary,
    SupervisorValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatus,
    scan_for_forbidden_keys,
)

# If neither side has zero blocks but one has this many times more blocks
# than the other, treat it as a "drastic" count difference (still only a
# warning, never a failure — see module docstring rules).
_DRASTIC_BLOCK_COUNT_RATIO = 3
_MAX_FORBIDDEN_KEYS_LISTED = 20
_FAILED_SHADOW_STATUSES = {"failed", "budget_exceeded"}


def _issue(code: str, severity: ValidationSeverity, message: str, **details: Any) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message=message, details=details)


def _validate_no_shadow_proposed_actions(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 1: a shadow-executed capability must never produce a proposed action."""
    if comparison.shadow_proposed_action_count > 0:
        return _issue(
            "shadow_proposed_actions_detected",
            "error",
            "Shadow-executed capability produced one or more proposed actions.",
            shadowProposedActionCount=comparison.shadow_proposed_action_count,
        )
    return None


def _validate_no_unsafe_capability_execution(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 2: no capability with a non-`"none"` side-effect level may actually execute."""
    if comparison.unsafe_capabilities_attempted:
        return _issue(
            "unsafe_capability_shadow_execution_detected",
            "error",
            "Shadow run executed (or attempted to execute) a capability that is not "
            "side-effect free.",
            capabilities=list(comparison.unsafe_capabilities_attempted),
        )
    return None


def _validate_block_type_mismatch(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 3: conservative, warning-only structural block comparison.

    - Both sides empty -> pass (no issue).
    - Block type sets differ -> warning.
    - Type sets match but counts differ drastically -> warning.
    - Never fails here — a block mismatch alone is never "dangerous or
      impossible", just worth a human glancing at it.
    """
    live_types = set(comparison.live_block_types)
    shadow_types = set(comparison.shadow_block_types)
    if not live_types and not shadow_types:
        return None

    if live_types != shadow_types:
        return _issue(
            "shadow_block_type_mismatch",
            "warning",
            "Live and shadow structured block type sets differ.",
            liveBlockTypes=sorted(live_types),
            shadowBlockTypes=sorted(shadow_types),
        )

    live_count, shadow_count = comparison.live_block_count, comparison.shadow_block_count
    if live_count and shadow_count:
        bigger, smaller = max(live_count, shadow_count), min(live_count, shadow_count)
        if bigger >= smaller * _DRASTIC_BLOCK_COUNT_RATIO:
            return _issue(
                "shadow_block_type_mismatch",
                "warning",
                "Live and shadow block counts differ drastically despite matching types.",
                liveBlockCount=live_count,
                shadowBlockCount=shadow_count,
            )
    return None


def _validate_proposed_action_count_mismatch(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 4a: any proposed-action count difference is a hard failure."""
    if comparison.live_proposed_action_count != comparison.shadow_proposed_action_count:
        return _issue(
            "proposed_action_count_mismatch",
            "error",
            "Live and shadow proposed-action counts differ.",
            liveProposedActionCount=comparison.live_proposed_action_count,
            shadowProposedActionCount=comparison.shadow_proposed_action_count,
        )
    return None


def _validate_warning_count_mismatch(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 4b: a warning-count difference is only a warning."""
    if comparison.live_warning_count != comparison.shadow_warning_count:
        return _issue(
            "warning_count_mismatch",
            "warning",
            "Live and shadow warning counts differ.",
            liveWarningCount=comparison.live_warning_count,
            shadowWarningCount=comparison.shadow_warning_count,
        )
    return None


def _validate_shadow_execution_failed(comparison: ShadowComparisonSummary) -> ValidationIssue | None:
    """Rule 5: a failed/budget-exceeded shadow run is at least a warning."""
    status = comparison.shadow_status
    if status in _FAILED_SHADOW_STATUSES:
        severity: ValidationSeverity = "error" if status == "failed" else "warning"
        return _issue(
            "shadow_execution_failed",
            severity,
            f"Supervisor shadow run ended with status={status}.",
            shadowStatus=status,
            failedSubtasks=list(comparison.shadow_failed_subtasks),
        )
    return None


def _validate_no_forbidden_diagnostic_payload(diagnostics: dict[str, Any] | None) -> ValidationIssue | None:
    """Rule 6: diagnostics must never carry a raw-context/chain-of-thought-shaped key."""
    if not diagnostics:
        return None
    hits = scan_for_forbidden_keys(diagnostics)
    if hits:
        return _issue(
            "forbidden_diagnostic_payload_detected",
            "error",
            "Diagnostics payload contains a forbidden raw-context or "
            "chain-of-thought-shaped key.",
            keys=hits[:_MAX_FORBIDDEN_KEYS_LISTED],
        )
    return None


_COMPARISON_VALIDATORS: tuple[Callable[[ShadowComparisonSummary], ValidationIssue | None], ...] = (
    _validate_no_shadow_proposed_actions,
    _validate_no_unsafe_capability_execution,
    _validate_block_type_mismatch,
    _validate_proposed_action_count_mismatch,
    _validate_warning_count_mismatch,
    _validate_shadow_execution_failed,
)


def _is_read_only_result(comparison: ShadowComparisonSummary) -> bool:
    return comparison.live_proposed_action_count == 0 and comparison.shadow_proposed_action_count == 0


def validate_shadow_run(
    *,
    comparison: ShadowComparisonSummary,
    shadow_run_output: SupervisorRunOutput | None = None,
    diagnostics: dict[str, Any] | None = None,
    validation_enabled: bool = True,
) -> SupervisorValidationResult:
    """Run every deterministic Phase 8 validator over `comparison`.

    When `validation_enabled` is `False`, a comparison may still have been
    generated by the caller — this simply returns a minimal, deterministic
    `status="skipped"` result instead of running any validator, per the
    `AGENT_SUPERVISOR_VALIDATION_ENABLED=false` behavior in the spec.

    `safe_to_promote` is always diagnostic-only and defaults conservatively:
    it is only ever `True` when `status == "passed"` (zero issues, not even
    warnings), the shadow run itself reported `completed`/
    `completed_with_warnings`, and the compared result was read-only on both
    sides (no proposed actions at all). Nothing reads this flag to change
    behavior in Phase 8.

    Never raises: unexpected input (e.g. a malformed `diagnostics` dict)
    degrades to that specific check being skipped, never to an exception
    escaping this function.
    """
    if not validation_enabled:
        return SupervisorValidationResult(
            status="skipped",
            safe_to_promote=False,
            comparison=comparison,
            warnings=["supervisor_validation_disabled"],
        )

    issues: list[ValidationIssue] = []
    for validator in _COMPARISON_VALIDATORS:
        try:
            issue = validator(comparison)
        except Exception:  # noqa: BLE001 — one bad validator must never break the run
            continue
        if issue is not None:
            issues.append(issue)

    forbidden_issue = _validate_no_forbidden_diagnostic_payload(diagnostics)
    if forbidden_issue is not None:
        issues.append(forbidden_issue)

    has_error = any(issue.severity == "error" for issue in issues)
    has_warning = any(issue.severity == "warning" for issue in issues)

    status: ValidationStatus
    if has_error:
        status = "failed"
    elif has_warning:
        status = "passed_with_warnings"
    else:
        status = "passed"

    shadow_completed = comparison.shadow_status in ("completed", "completed_with_warnings")
    safe_to_promote = status == "passed" and shadow_completed and _is_read_only_result(comparison)

    annotated_comparison = comparison.model_copy(update={"issues": list(issues), "safe_match": not has_error})

    return SupervisorValidationResult(
        status=status,
        safe_to_promote=safe_to_promote,
        comparison=annotated_comparison,
        issues=issues,
    )
