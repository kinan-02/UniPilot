"""Typed models for Specialist Output Validation + Compare (Phase 11).

Diagnostic-only, exactly like every other Phase 6–10 supervisor/specialist
model: none of these fields are read anywhere to select a workflow, shape
the final `AgentResponse`, or otherwise change live behavior — they exist
purely to be attached (compactly) to
`agent_runs.retrievalMetadata.specialistValidation`.

As with `SpecialistAgentOutput`/`SupervisorValidationResult`, no field here
may carry raw chain-of-thought or private model reasoning, and
`validation.py`/`compare.py` actively scan for the forbidden key names below
before a result is ever built.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.supervisor.validation_schemas import FORBIDDEN_DIAGNOSTIC_KEYS, scan_for_forbidden_keys

# Re-exported so `specialists.validation`/`specialists.compare` (and their
# tests) can import a single, Phase-11-specific name without every caller
# needing to know this list is actually shared with the Phase 8 supervisor
# validation layer.
FORBIDDEN_SPECIALIST_KEYS = FORBIDDEN_DIAGNOSTIC_KEYS

SpecialistValidationSeverity = Literal["info", "warning", "error"]
SpecialistValidationStatus = Literal[
    "passed",
    "passed_with_warnings",
    "failed",
    "skipped",
]

# Diagnostic-only mapping from a live, comparable, read-only deterministic
# workflow to its Phase 10 specialist-agent counterpart. Never used to route
# production traffic — see `specialists.compare.specialist_agent_for_workflow`.
# `general_academic_workflow`, `transcript_import_workflow`, and
# `semester_planning_workflow` are deliberately absent (never comparable in
# Phase 11 — the first is operationally expensive/LLM-heavy, the other two
# are write/proposal workflows).
WORKFLOW_TO_SPECIALIST_AGENT: dict[str, str] = {
    "graduation_progress_workflow": "graduation_progress_agent",
    "course_question_workflow": "course_catalog_agent",
    "requirement_explanation_workflow": "requirement_explanation_agent",
}


class SpecialistValidationIssue(BaseModel):
    """One deterministic validator/comparison finding."""

    code: str
    severity: SpecialistValidationSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SpecialistOutputValidationResult(BaseModel):
    """Result of running Phase 11's deterministic validators over one specialist output.

    `safe_to_consider` is diagnostic-only — nothing reads it to change
    routing, execution, or the response. It defaults to `False` and is only
    ever `True` when `status == "passed"` (zero issues, not even warnings).
    """

    status: SpecialistValidationStatus
    safe_to_consider: bool = False
    agent_name: str
    subtask_id: str | None = None
    issues: list[SpecialistValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class WorkflowSpecialistComparison(BaseModel):
    """Compact, structural-only comparison of a live workflow result vs a
    comparable specialist-agent output summary — see
    `specialists.compare.compare_workflow_and_specialist`.

    Never carries raw text, raw blocks, raw sources, or proposed-action
    payloads — only counts, type lists, and status strings.
    """

    workflow_name: str | None = None
    specialist_agent_name: str | None = None
    comparable: bool = False
    safe_match: bool = False
    live_block_types: list[str] = Field(default_factory=list)
    specialist_result_keys: list[str] = Field(default_factory=list)
    live_warning_count: int = 0
    specialist_warning_count: int = 0
    live_source_count: int = 0
    specialist_source_count: int = 0
    issues: list[SpecialistValidationIssue] = Field(default_factory=list)


class SpecialistCompareDiagnostics(BaseModel):
    """Aggregate result of validating (and, when enabled, comparing) every
    specialist-agent subtask output found in one supervisor shadow run.

    `safe_to_consider` is diagnostic-only in Phase 11 — never used to
    promote a specialist output or otherwise change behavior. Only ever
    `True` when at least one specialist output was actually validated,
    every validation passed cleanly, and every comparable comparison
    reported `safe_match=True`.
    """

    status: SpecialistValidationStatus
    safe_to_consider: bool = False
    comparisons: list[WorkflowSpecialistComparison] = Field(default_factory=list)
    validation_results: list[SpecialistOutputValidationResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "FORBIDDEN_SPECIALIST_KEYS",
    "SpecialistValidationSeverity",
    "SpecialistValidationStatus",
    "WORKFLOW_TO_SPECIALIST_AGENT",
    "SpecialistValidationIssue",
    "SpecialistOutputValidationResult",
    "WorkflowSpecialistComparison",
    "SpecialistCompareDiagnostics",
    "scan_for_forbidden_keys",
]
