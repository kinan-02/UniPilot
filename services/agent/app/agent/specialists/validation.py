"""Deterministic Phase 11 validators over one specialist-agent output.

Every validator here is pure, synchronous, and deterministic — no LLM calls,
no I/O, no database access. `validate_specialist_output` never raises: a bug
in a single validator, or a malformed/unexpected input, degrades to a safe
`status="failed"` result instead of an exception escaping this module.

Accepts either a real `SpecialistAgentOutput` (in-memory only — used
directly by unit tests and any future caller with the raw object) or its
already-compact summary dict (`specialists.output_summarizer.summarize_specialist_output`'s
shape — what `SupervisorRunOutput.subtask_records[].result_summary` actually
holds, since the raw output itself is never stored there).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.specialists.schemas import SpecialistAgentOutput
from app.agent.specialists.validation_schemas import (
    SpecialistOutputValidationResult,
    SpecialistValidationIssue,
    SpecialistValidationSeverity,
    SpecialistValidationStatus,
    scan_for_forbidden_keys,
)

logger = logging.getLogger(__name__)

_VALID_SPECIALIST_STATUSES = ("completed", "needs_more_context", "unsupported", "failed", "skipped")
_LOW_CONFIDENCE_THRESHOLD = 0.6
_MAX_FORBIDDEN_KEYS_LISTED = 20
_UNKNOWN_AGENT_NAME = "unknown_specialist"

# Conservative, substring-based (case/underscore-insensitive) scope-violation
# signals per agent — see the Phase 11 spec's own examples. Deliberately
# small and specific to avoid false positives on legitimate result shapes.
_SUSPICIOUS_RESULT_KEY_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "graduation_progress_agent": ("transcriptrow", "transcript"),
    "course_catalog_agent": ("savedplan", "actionid", "proposedaction"),
    "requirement_explanation_agent": ("proposedaction", "actionid", "savedplan"),
}


@dataclass(frozen=True)
class _NormalizedSpecialistOutput:
    agent_name: str | None
    subtask_id: str | None
    status: str | None
    confidence: float | None
    has_proposed_actions: bool
    missing_context_count: int
    result_keys: list[str]
    scan_payload: dict[str, Any]


def _normalize(
    output: SpecialistAgentOutput | dict[str, Any] | None, *, subtask_id_override: str | None
) -> _NormalizedSpecialistOutput | None:
    if output is None:
        return None
    if isinstance(output, SpecialistAgentOutput):
        return _NormalizedSpecialistOutput(
            agent_name=output.agent_name,
            subtask_id=subtask_id_override or output.subtask_id,
            status=output.status,
            confidence=output.confidence,
            has_proposed_actions=bool(output.proposed_actions),
            missing_context_count=len(output.missing_context),
            result_keys=sorted(output.result.keys()),
            scan_payload=output.model_dump(),
        )
    if isinstance(output, dict):
        confidence_raw = output.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        result_keys = output.get("resultKeys", output.get("result_keys"))
        return _NormalizedSpecialistOutput(
            agent_name=output.get("agentName") or output.get("agent_name"),
            subtask_id=subtask_id_override,
            status=output.get("status"),
            confidence=confidence,
            has_proposed_actions=bool(output.get("hasProposedActions") or output.get("has_proposed_actions")),
            missing_context_count=int(
                output.get("missingContextCount") or output.get("missing_context_count") or 0
            ),
            result_keys=list(result_keys) if isinstance(result_keys, list) else [],
            scan_payload=output,
        )
    return None


def _issue(code: str, severity: SpecialistValidationSeverity, message: str, **details: Any) -> SpecialistValidationIssue:
    return SpecialistValidationIssue(code=code, severity=severity, message=message, details=details)


def _validate_no_proposed_actions(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 1: a specialist output must never carry a proposed action."""
    if n.has_proposed_actions:
        return _issue(
            "specialist_proposed_actions_detected",
            "error",
            "Specialist output has (or reported) proposed actions.",
        )
    return None


def _validate_confidence(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 3: confidence must be present and in [0, 1]; low confidence is only a warning."""
    if n.confidence is None or not (0.0 <= n.confidence <= 1.0):
        return _issue(
            "invalid_specialist_confidence",
            "error",
            "Specialist confidence is missing or out of the [0, 1] range.",
            confidence=n.confidence,
        )
    if n.confidence < _LOW_CONFIDENCE_THRESHOLD:
        return _issue(
            "low_specialist_confidence",
            "warning",
            f"Specialist confidence ({n.confidence}) is below the {_LOW_CONFIDENCE_THRESHOLD} threshold.",
            confidence=n.confidence,
        )
    return None


def _validate_status(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 4: status must be one of the allowed values; a reported `"failed"` is a warning, not a crash."""
    if n.status not in _VALID_SPECIALIST_STATUSES:
        return _issue("invalid_specialist_status", "error", f"Unrecognized specialist status: {n.status!r}.")
    if n.status == "failed":
        return _issue(
            "specialist_status_reported_failed",
            "warning",
            "The specialist itself reported status=failed.",
        )
    return None


def _validate_missing_context(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 5: any missing context is a warning (never safe_to_consider on its own)."""
    if n.missing_context_count > 0:
        return _issue(
            "specialist_missing_context",
            "warning",
            "Specialist reported missing context.",
            missingContextCount=n.missing_context_count,
        )
    return None


def _validate_empty_result(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 6: a `"completed"` status with an empty result is suspicious but not fatal."""
    if n.status == "completed" and not n.result_keys:
        return _issue(
            "specialist_empty_result",
            "warning",
            "Specialist reported status=completed but returned an empty result.",
        )
    return None


def _validate_scope(n: _NormalizedSpecialistOutput) -> SpecialistValidationIssue | None:
    """Rule 7: conservative, substring-based scope-violation signal — see module docstring."""
    suspicious = _SUSPICIOUS_RESULT_KEY_SUBSTRINGS.get(n.agent_name or "", ())
    if not suspicious:
        return None
    for key in n.result_keys:
        normalized_key = key.lower().replace("_", "")
        if any(substring in normalized_key for substring in suspicious):
            return _issue(
                "specialist_scope_violation_suspected",
                "warning",
                f"Result key {key!r} looks unrelated to {n.agent_name}'s assigned scope.",
                key=key,
            )
    return None


def _validate_no_forbidden_payload(
    n: _NormalizedSpecialistOutput, diagnostics: dict[str, Any] | None
) -> SpecialistValidationIssue | None:
    """Rule 2: no forbidden raw/chain-of-thought-shaped key anywhere in the scanned payload."""
    combined = {"output": n.scan_payload, "diagnostics": diagnostics or {}}
    hits = scan_for_forbidden_keys(combined)
    if hits:
        return _issue(
            "forbidden_specialist_payload_detected",
            "error",
            "Specialist output/diagnostics contains a forbidden raw/chain-of-thought-shaped key.",
            keys=hits[:_MAX_FORBIDDEN_KEYS_LISTED],
        )
    return None


_VALIDATORS: tuple[Callable[[_NormalizedSpecialistOutput], SpecialistValidationIssue | None], ...] = (
    _validate_no_proposed_actions,
    _validate_confidence,
    _validate_status,
    _validate_missing_context,
    _validate_empty_result,
    _validate_scope,
)


def validate_specialist_output(
    output: SpecialistAgentOutput | dict[str, Any] | None,
    *,
    subtask_id: str | None = None,
    diagnostics: dict[str, Any] | None = None,
    validation_enabled: bool = True,
) -> SpecialistOutputValidationResult:
    """Run every deterministic Phase 11 validator over `output`.

    Never raises: a malformed/unexpected `output` (wrong type, missing
    fields) degrades to a `status="failed"` result with a
    `specialist_output_malformed` issue; a bug in a single validator
    degrades to that validator being skipped, not to the whole call failing.

    When `validation_enabled` is `False`, returns a minimal, deterministic
    `status="skipped"` result instead of running any validator.
    """
    try:
        normalized = _normalize(output, subtask_id_override=subtask_id)
    except Exception:  # noqa: BLE001 — malformed input must never raise here
        logger.exception("specialist_output_normalization_failed")
        normalized = None

    agent_name = (normalized.agent_name if normalized else None) or _UNKNOWN_AGENT_NAME
    resolved_subtask_id = (normalized.subtask_id if normalized else None) or subtask_id

    if normalized is None:
        return SpecialistOutputValidationResult(
            status="failed",
            safe_to_consider=False,
            agent_name=agent_name,
            subtask_id=resolved_subtask_id,
            issues=[
                SpecialistValidationIssue(
                    code="specialist_output_malformed",
                    severity="error",
                    message="Specialist output could not be parsed into a validatable shape.",
                )
            ],
        )

    if not validation_enabled:
        return SpecialistOutputValidationResult(
            status="skipped",
            safe_to_consider=False,
            agent_name=agent_name,
            subtask_id=resolved_subtask_id,
            warnings=["specialist_validation_disabled"],
        )

    issues: list[SpecialistValidationIssue] = []
    for validator in _VALIDATORS:
        try:
            issue = validator(normalized)
        except Exception:  # noqa: BLE001 — one bad validator must never break the run
            continue
        if issue is not None:
            issues.append(issue)

    try:
        forbidden_issue = _validate_no_forbidden_payload(normalized, diagnostics)
    except Exception:  # noqa: BLE001
        forbidden_issue = None
    if forbidden_issue is not None:
        issues.append(forbidden_issue)

    has_error = any(issue.severity == "error" for issue in issues)
    has_warning = any(issue.severity == "warning" for issue in issues)

    status: SpecialistValidationStatus
    if has_error:
        status = "failed"
    elif has_warning:
        status = "passed_with_warnings"
    else:
        status = "passed"

    return SpecialistOutputValidationResult(
        status=status,
        safe_to_consider=status == "passed",
        agent_name=agent_name,
        subtask_id=resolved_subtask_id,
        issues=issues,
    )
