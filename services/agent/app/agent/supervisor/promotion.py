"""Controlled Supervisor Promotion gate (Phase 9).

`evaluate_promotion_decision` is the single deterministic decision point
that decides whether a supervisor-executed candidate `AgentResponse` may
replace the live deterministic workflow's own response for the current
turn. It is intentionally narrow and conservative:

- Hard-restricted to a small, explicitly reviewed set of read-only
  workflows (`_HARD_ALLOWED_PROMOTION_WORKFLOWS`), regardless of how
  `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` is configured. `general_academic_workflow`
  is deliberately excluded even though it is otherwise read-only: its real
  shadow execution is skipped by default because it is operationally
  expensive (`operationally_expensive_for_shadow_execution`, see
  `capabilities/default_registry.py` and `supervisor/runtime.py::_select_handler`)
  — a shadow run for it is always the dry-run stand-in, never a real
  candidate, so including it here would only ever produce a permanently
  blocked (never promoted) result.
- Requires every Phase 8 validation gate to have already passed cleanly
  (`status == "passed"`, `safe_to_promote is True`) *and* a fresh set of
  Phase 9–specific structural checks on top (matching block types/counts,
  zero proposed actions on both sides, no unsafe/write-scoped capability
  anywhere in the supervisor run, no forbidden raw/chain-of-thought-shaped
  diagnostic key, and a full in-memory candidate `AgentResponse` that itself
  passes `check_candidate_response_safety`).
- Never raises: any unexpected input degrades to `status="failed"`, never to
  an exception escaping this module.
- Never calls an LLM, never touches the database, never performs a write or
  creates an action proposal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.agent.schemas import AgentResponse
from app.agent.supervisor.validation_schemas import SupervisorValidationResult, scan_for_forbidden_keys
from app.agent.supervisor.promotion_schemas import PromotionBlockReason, PromotionDecision, PromotionMode
from app.config import Settings

logger = logging.getLogger(__name__)

# Phase 9 hard ceiling (widened this cycle to cover every read-only workflow
# whose shadow execution is not operationally-expensive-skipped by default —
# see the module docstring for why `general_academic_workflow` stays out).
# No configuration value can ever widen promotion eligibility past this set.
# `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` may only *narrow* it further (e.g.
# an operator disabling promotion entirely by configuring an empty list, or
# limiting it to just one of these three).
_HARD_ALLOWED_PROMOTION_WORKFLOWS: frozenset[str] = frozenset(
    {
        "graduation_progress_workflow",
        "course_question_workflow",
        "requirement_explanation_workflow",
    }
)

# Defense in depth: these must never appear as a capability the supervisor
# run actually touched on a promotion-eligible path, even though a
# graduation-progress plan should never reference them.
_WRITE_OR_PROPOSAL_CAPABILITY_NAMES: frozenset[str] = frozenset(
    {"transcript_import_workflow", "semester_planning_workflow"}
)

_MAX_FORBIDDEN_KEYS_LISTED = 20


def eligible_promotion_workflows(settings: Settings) -> frozenset[str]:
    """The actual, effective promotion-eligible workflow set for `settings`.

    Always a subset of `_HARD_ALLOWED_PROMOTION_WORKFLOWS` — configuring
    `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` with any workflow name outside
    that set has no effect; only removing one of its members can change
    anything (narrowing which of them is actually eligible for promotion).
    """
    return _HARD_ALLOWED_PROMOTION_WORKFLOWS & settings.agent_supervisor_promotion_configured_workflows()


def _reason(code: str, severity: str, message: str, **details: Any) -> PromotionBlockReason:
    return PromotionBlockReason(code=code, severity=severity, message=message, details=details)


def _blocked(workflow_name: str | None, mode: PromotionMode, reasons: list[PromotionBlockReason]) -> PromotionDecision:
    return PromotionDecision(status="blocked", promoted=False, workflow_name=workflow_name, mode=mode, reasons=reasons)


@dataclass(frozen=True)
class _NormalizedValidation:
    status: str | None
    safe_to_promote: bool
    unsafe_capabilities_attempted: list[str]


def _normalize_validation(
    value: SupervisorValidationResult | dict[str, Any] | None,
) -> _NormalizedValidation | None:
    """Accept either a real `SupervisorValidationResult` or its compact dict
    form (`compare_diagnostics.build_supervisor_validation_metadata`'s
    output) — never raises on an unexpected shape, just returns `None`."""
    if value is None:
        return None
    try:
        if isinstance(value, SupervisorValidationResult):
            unsafe = list(value.comparison.unsafe_capabilities_attempted) if value.comparison else []
            return _NormalizedValidation(
                status=value.status, safe_to_promote=bool(value.safe_to_promote), unsafe_capabilities_attempted=unsafe
            )
        if isinstance(value, dict):
            status = value.get("status")
            safe_to_promote = bool(value.get("safeToPromote", value.get("safe_to_promote", False)))
            issues = value.get("issues") or []
            unsafe: list[str] = []
            for issue in issues:
                code = issue.get("code") if isinstance(issue, dict) else getattr(issue, "code", None)
                if code == "unsafe_capability_shadow_execution_detected":
                    unsafe.append("unsafe_capability_detected")
            return _NormalizedValidation(status=status, safe_to_promote=safe_to_promote, unsafe_capabilities_attempted=unsafe)
    except Exception:  # noqa: BLE001 — malformed input must never raise here
        return None
    return None


def _safe_model_dump(obj: Any) -> dict[str, Any] | None:
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:  # noqa: BLE001
            return None
    if isinstance(obj, dict):
        return obj
    return None


def check_candidate_response_safety(
    candidate_response: Any,
    *,
    live_response: Any | None = None,
) -> list[PromotionBlockReason]:
    """Deep, structural safety checks on a candidate response before promotion.

    Duck-typed deliberately (reads attributes via `getattr`, doesn't require
    a strict `isinstance(candidate_response, AgentResponse)`) so a malformed
    stand-in object can be checked and reported on rather than only ever
    producing one generic "wrong type" reason — a real production candidate
    is always a genuine `AgentResponse` (Pydantic already enforces its field
    types at construction), so this flexibility only matters for tests.

    Never raises; never mutates or persists `candidate_response`.
    """
    reasons: list[PromotionBlockReason] = []

    if candidate_response is None:
        reasons.append(_reason("candidate_missing", "error", "No candidate response was provided."))
        return reasons

    proposed_actions = getattr(candidate_response, "proposed_actions", None)
    if not isinstance(proposed_actions, list):
        reasons.append(_reason("candidate_proposed_actions_malformed", "error", "candidate.proposed_actions is not list-like."))
    elif proposed_actions:
        reasons.append(_reason("candidate_has_proposed_actions", "error", "Candidate response has proposed actions."))

    warnings = getattr(candidate_response, "warnings", None)
    if not isinstance(warnings, list):
        reasons.append(_reason("candidate_warnings_malformed", "error", "candidate.warnings is not list-like."))

    used_sources = getattr(candidate_response, "used_sources", None)
    if not isinstance(used_sources, list):
        reasons.append(_reason("candidate_sources_malformed", "error", "candidate.used_sources is not list-like."))

    blocks = getattr(candidate_response, "blocks", None)
    if not isinstance(blocks, list) or not blocks:
        reasons.append(_reason("candidate_blocks_missing_or_malformed", "error", "Candidate response has no valid structured blocks."))
        blocks = []
    else:
        for block in blocks:
            block_type = getattr(block, "type", None)
            if not block_type or not isinstance(block_type, str):
                reasons.append(_reason("candidate_block_structurally_invalid", "error", "Candidate response has a structurally invalid block."))
                break

    dumped = _safe_model_dump(candidate_response)
    if dumped is not None:
        forbidden_hits = scan_for_forbidden_keys(dumped)
        if forbidden_hits:
            reasons.append(
                _reason(
                    "candidate_forbidden_payload_detected",
                    "error",
                    "Candidate response contains a forbidden raw/chain-of-thought-shaped key.",
                    keys=forbidden_hits[:_MAX_FORBIDDEN_KEYS_LISTED],
                )
            )

    if live_response is not None:
        live_blocks = getattr(live_response, "blocks", None) or []
        live_types = sorted({getattr(b, "type", None) for b in live_blocks if getattr(b, "type", None)})
        candidate_types = sorted({getattr(b, "type", None) for b in blocks if getattr(b, "type", None)})
        if live_types != candidate_types:
            reasons.append(
                _reason(
                    "candidate_block_type_mismatch",
                    "error",
                    "Candidate and live block types differ.",
                    liveBlockTypes=live_types,
                    candidateBlockTypes=candidate_types,
                )
            )
        if len(live_blocks) != len(blocks):
            reasons.append(
                _reason(
                    "candidate_block_count_mismatch",
                    "error",
                    "Candidate and live block counts differ.",
                    liveBlockCount=len(live_blocks),
                    candidateBlockCount=len(blocks),
                )
            )

    return reasons


def evaluate_promotion_decision(
    *,
    workflow_name: str,
    live_response_summary: dict[str, Any],
    candidate_response_summary: dict[str, Any] | None,
    supervisor_validation: SupervisorValidationResult | dict[str, Any] | None,
    supervisor_output_summary: dict[str, Any] | None,
    settings: Settings,
    live_response: AgentResponse | Any | None = None,
    candidate_response: AgentResponse | Any | None = None,
) -> PromotionDecision:
    """Decide whether a supervisor candidate may replace the live response.

    `live_response`/`candidate_response` are optional, in-memory-only raw
    `AgentResponse` objects (never serialized anywhere) used solely for the
    final `check_candidate_response_safety` deep structural check; every
    other gate operates on the already-compact `*_summary`/validation
    dicts/models, so nothing raw needs to be passed for most gate checks
    (e.g. the promotion-gate unit tests exercise gates 1–15 with summaries
    alone).

    Never raises: any unexpected input (missing keys, wrong types, `None`
    where a dict was expected, ...) degrades to `status="failed"`.
    """
    try:
        enabled = settings.is_agent_supervisor_promotion_enabled()
        mode = settings.agent_supervisor_promotion_mode()

        if not enabled or mode == "off":
            return PromotionDecision(status="skipped", promoted=False, workflow_name=workflow_name, mode="off")

        if mode == "shadow_only":
            return PromotionDecision(status="skipped", promoted=False, workflow_name=workflow_name, mode="shadow_only")

        # From here on, mode == "promote_validated".
        eligible = eligible_promotion_workflows(settings)
        if workflow_name not in eligible:
            return _blocked(
                workflow_name,
                mode,
                [
                    _reason(
                        "workflow_not_eligible_for_promotion",
                        "error",
                        f"'{workflow_name}' is not eligible for supervisor promotion.",
                    )
                ],
            )

        if settings.is_agent_runtime_readiness_gate_enabled():
            from app.agent.readiness.diagnostics import build_runtime_readiness_diagnostic
            from app.agent.readiness.runtime_gate import (
                evaluate_runtime_gate_for_settings,
                workflow_promotion_candidate_id,
            )

            gate_decision = evaluate_runtime_gate_for_settings(
                candidate_id=workflow_promotion_candidate_id(workflow_name),
                requested_scope=workflow_name,
                settings=settings,
            )
            runtime_diag = build_runtime_readiness_diagnostic(gate_decision, settings=settings)
            if not gate_decision.allowed:
                return PromotionDecision(
                    status="blocked",
                    promoted=False,
                    workflow_name=workflow_name,
                    mode=mode,
                    reasons=[
                        _reason(
                            "runtime_readiness_gate_blocked",
                            "error",
                            "Runtime readiness gate blocked promotion.",
                            reasons=gate_decision.reasons[:5],
                        )
                    ],
                    diagnostics={"runtimeReadiness": runtime_diag},
                )

        reasons: list[PromotionBlockReason] = []

        normalized_validation = _normalize_validation(supervisor_validation)
        if normalized_validation is None:
            reasons.append(_reason("validation_missing", "error", "No supervisor validation result is available."))
        else:
            if normalized_validation.status != "passed":
                severity = "warning" if normalized_validation.status == "passed_with_warnings" else "error"
                reasons.append(
                    _reason(
                        "validation_not_passed",
                        severity,
                        f"Supervisor validation status={normalized_validation.status!r}, not 'passed'.",
                    )
                )
            if not normalized_validation.safe_to_promote:
                reasons.append(
                    _reason(
                        "validation_not_safe_to_promote",
                        "error",
                        "Supervisor validation did not mark this result safe_to_promote.",
                    )
                )
            if normalized_validation.unsafe_capabilities_attempted:
                reasons.append(
                    _reason(
                        "unsafe_capability_attempted",
                        "error",
                        "Supervisor run attempted an unsafe capability.",
                        capabilities=list(normalized_validation.unsafe_capabilities_attempted),
                    )
                )

        live_proposed_count = int(
            (live_response_summary or {}).get("proposedActionCount")
            or (live_response_summary or {}).get("proposed_action_count")
            or 0
        )
        if live_proposed_count:
            reasons.append(_reason("live_response_has_proposed_actions", "error", "Live response has proposed actions."))

        if candidate_response_summary is None:
            reasons.append(_reason("candidate_response_summary_missing", "error", "No candidate response summary is available."))
        else:
            candidate_proposed_count = int(candidate_response_summary.get("proposedActionCount") or 0)
            if candidate_proposed_count:
                reasons.append(
                    _reason("candidate_response_has_proposed_actions", "error", "Candidate response has proposed actions.")
                )

            live_block_types = sorted((live_response_summary or {}).get("blockTypes") or [])
            candidate_block_types = sorted(candidate_response_summary.get("blockTypes") or [])
            if live_block_types != candidate_block_types:
                reasons.append(
                    _reason(
                        "block_types_mismatch",
                        "error",
                        "Live and candidate block types differ.",
                        liveBlockTypes=live_block_types,
                        candidateBlockTypes=candidate_block_types,
                    )
                )

            live_block_count = int((live_response_summary or {}).get("blockCount") or 0)
            candidate_block_count = int(candidate_response_summary.get("blockCount") or 0)
            if live_block_count != candidate_block_count:
                reasons.append(
                    _reason(
                        "block_count_mismatch",
                        "error",
                        "Live and candidate block counts differ.",
                        liveBlockCount=live_block_count,
                        candidateBlockCount=candidate_block_count,
                    )
                )

        if supervisor_output_summary is None:
            reasons.append(_reason("supervisor_output_missing", "error", "No supervisor output summary is available."))
        else:
            capabilities = set(supervisor_output_summary.get("capabilities") or [])
            if workflow_name not in capabilities:
                reasons.append(
                    _reason(
                        "supervisor_output_capability_mismatch",
                        "error",
                        "Supervisor output did not include the expected capability.",
                    )
                )
            if supervisor_output_summary.get("failedSubtasks"):
                reasons.append(_reason("supervisor_subtask_failed", "error", "A supervisor subtask failed."))
            unsafe_capability_names = capabilities & _WRITE_OR_PROPOSAL_CAPABILITY_NAMES
            if unsafe_capability_names:
                reasons.append(
                    _reason(
                        "write_or_proposal_capability_in_path",
                        "error",
                        "A write/proposal capability exists in the candidate execution path.",
                        capabilities=sorted(unsafe_capability_names),
                    )
                )

        forbidden_hits = scan_for_forbidden_keys(
            {
                "live": live_response_summary,
                "candidate": candidate_response_summary,
                "supervisorOutput": supervisor_output_summary,
            }
        )
        if forbidden_hits:
            reasons.append(
                _reason(
                    "forbidden_diagnostic_payload_detected",
                    "error",
                    "Forbidden raw/chain-of-thought-shaped key found in diagnostics.",
                    keys=forbidden_hits[:_MAX_FORBIDDEN_KEYS_LISTED],
                )
            )

        # Gates 16/17: a real in-memory candidate must exist and must itself
        # pass every structural safety check.
        reasons.extend(check_candidate_response_safety(candidate_response, live_response=live_response))

        if reasons:
            return _blocked(workflow_name, mode, reasons)

        return PromotionDecision(status="promoted", promoted=True, workflow_name=workflow_name, mode=mode)
    except Exception:  # noqa: BLE001 — must never raise into a live turn
        logger.exception("supervisor_promotion_evaluation_failed")
        return PromotionDecision(
            status="failed",
            promoted=False,
            workflow_name=workflow_name if isinstance(workflow_name, str) else None,
            mode="promote_validated",
            reasons=[_reason("promotion_evaluation_error", "error", "Promotion evaluation failed unexpectedly.")],
        )
