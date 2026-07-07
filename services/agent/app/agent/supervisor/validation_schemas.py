"""Typed models for the Supervisor Shadow Compare + Validation Layer (Phase 8).

Diagnostic-only, exactly like every other Phase 6/7 supervisor model: none of
these fields are read anywhere to select a workflow, shape the final
`AgentResponse`, or otherwise change live behavior — they exist purely to be
attached (compactly) to `agent_runs.retrievalMetadata.supervisorValidation`.

As with `PlannerOutput`/`SupervisorRunOutput`, no field here may carry raw
chain-of-thought or private model reasoning, and `validation.py` actively
scans arbitrary diagnostic payloads for the forbidden key names below before
they are ever attached to a result.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ValidationSeverity = Literal["info", "warning", "error"]
ValidationStatus = Literal["passed", "passed_with_warnings", "failed", "skipped"]

# Never allowed as a key anywhere in a diagnostics payload passed to
# `validation.validate_shadow_run` — see that module's
# `_validate_no_forbidden_diagnostic_payload`.
FORBIDDEN_DIAGNOSTIC_KEYS: tuple[str, ...] = (
    "context",
    "compiled_context",
    "raw_context",
    "raw_blocks",
    "raw_response",
    "raw_text",
    "full_text",
    "proposed_action_payload",
    "transcript_rows",
    "full_catalog",
    "raw_pdf_bytes",
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
    # Phase 11 additions — specialist-agent validation/compare scans for
    # these too (`app.agent.specialists.validation_schemas` re-exports this
    # same tuple rather than keeping a second, divergent list).
    "raw_prompt",
    "system_prompt",
    "user_prompt",
    "full_blocks",
)


def scan_for_forbidden_keys(value: Any, *, path: str = "") -> list[str]:
    """Recursively find `FORBIDDEN_DIAGNOSTIC_KEYS` key names in a dict/list.

    Shared by `validation.py` (Phase 8) and `promotion.py` (Phase 9) so both
    layers scan for exactly the same forbidden shapes. Never raises — a
    malformed/unexpected `value` degrades to "no hits found", never to an
    exception escaping this function.
    """
    found: list[str] = []
    try:
        if isinstance(value, dict):
            for key, sub_value in value.items():
                key_str = str(key)
                current_path = f"{path}.{key_str}" if path else key_str
                if key_str in FORBIDDEN_DIAGNOSTIC_KEYS:
                    found.append(current_path)
                found.extend(scan_for_forbidden_keys(sub_value, path=current_path))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                found.extend(scan_for_forbidden_keys(item, path=f"{path}[{index}]"))
    except Exception:  # noqa: BLE001 — a scan bug must never break a caller
        return found
    return found


class ValidationIssue(BaseModel):
    """One deterministic validator finding."""

    code: str
    severity: ValidationSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ShadowComparisonSummary(BaseModel):
    """Compact, structural-only comparison of a live workflow result vs a
    supervisor shadow run — see `shadow_compare.build_comparison_summary`.

    Never carries raw text, raw blocks, raw sources, or proposed-action
    payloads — only counts, type lists, and status strings.
    """

    live_workflow_name: str | None = None
    shadow_plan_id: str | None = None
    shadow_status: str | None = None

    live_block_types: list[str] = Field(default_factory=list)
    shadow_block_types: list[str] = Field(default_factory=list)

    live_block_count: int = 0
    shadow_block_count: int = 0

    live_warning_count: int = 0
    shadow_warning_count: int = 0

    live_proposed_action_count: int = 0
    shadow_proposed_action_count: int = 0

    live_source_count: int = 0
    shadow_source_count: int = 0

    # Structural, run-level signals `validation.py` reasons over — never the
    # underlying subtask output itself.
    shadow_failed_subtasks: list[str] = Field(default_factory=list)
    shadow_skipped_subtasks: list[str] = Field(default_factory=list)
    unsafe_capabilities_attempted: list[str] = Field(default_factory=list)

    safe_match: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)


class SupervisorValidationResult(BaseModel):
    """Result of running Phase 8's deterministic validators over one comparison.

    `safe_to_promote` is diagnostic-only in Phase 8 — nothing reads it to
    change routing or behavior. It defaults to `False` and is only ever set
    `True` when every validator passed cleanly (no warnings, no errors) and
    the shadow run itself completed.
    """

    status: ValidationStatus
    safe_to_promote: bool = False
    comparison: ShadowComparisonSummary | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
