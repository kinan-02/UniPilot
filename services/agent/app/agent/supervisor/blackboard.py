"""Supervisor blackboard (Phase 6).

Compact, run-scoped shared state for the Supervisor Runtime. Stores only
summaries — never raw LLM prompts, raw chain-of-thought, raw compiled
context, raw PDFs/transcript rows, full catalog dumps, or large Mongo
documents. Every value stored is passed through the same deterministic
sanitizer the Phase 4 `ContextCompiler` uses, as defense-in-depth against a
misbehaving subtask handler trying to stuff something large/unsafe in.
"""

from __future__ import annotations

from typing import Any

from app.agent.context_compiler.reducers import sanitize_context_value
from app.agent.supervisor.schemas import SubtaskResult

_MAX_LIST_ITEMS = 50


def _compact_planner_output_summary(planner_output: dict[str, Any]) -> dict[str, Any]:
    """Small summary of the plan — never the raw subtask graph or full plan."""
    return {
        "planId": planner_output.get("plan_id"),
        "executionMode": planner_output.get("execution_mode"),
        "primaryIntent": planner_output.get("primary_intent"),
        "subtaskCount": len(planner_output.get("subtasks") or []),
    }


class SupervisorBlackboard:
    """Run-scoped shared state written to by subtask handlers via the runtime."""

    def __init__(
        self,
        *,
        original_user_message: str,
        task_understanding: dict[str, Any] | None = None,
        planner_output: dict[str, Any] | None = None,
        profile_summary: dict[str, Any] | None = None,
    ) -> None:
        self.original_user_message = original_user_message
        self.task_understanding = sanitize_context_value(task_understanding or {})
        self.planner_output = _compact_planner_output_summary(planner_output or {})
        self.profile_summary = sanitize_context_value(profile_summary or {})
        self.global_context_summary: dict[str, Any] = {}

        self.subtask_results: dict[str, SubtaskResult] = {}
        self.capability_results: dict[str, dict[str, Any]] = {}
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.assumptions: list[str] = []
        self.sources: list[str] = []
        self.proposed_action_summaries: list[dict[str, Any]] = []
        self.validation_notes: list[str] = []

    def add_subtask_result(self, result: SubtaskResult) -> None:
        """Record one subtask's result. Sanitizes `output_summary` before storing it."""
        sanitized_summary = sanitize_context_value(result.output_summary)
        self.subtask_results[result.subtask_id] = result.model_copy(
            update={"output_summary": sanitized_summary}
        )
        self.capability_results[result.capability_name] = sanitized_summary
        for warning in result.warnings:
            self.add_warning(warning)
        if result.error:
            self.add_error(result.error)

    def get_dependency_outputs(self, dependency_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Compact output summaries for already-completed dependency subtasks."""
        return {
            dep_id: dict(self.subtask_results[dep_id].output_summary)
            for dep_id in dependency_ids
            if dep_id in self.subtask_results
        }

    def add_warning(self, warning: str) -> None:
        if warning and warning not in self.warnings:
            self.warnings = (self.warnings + [warning])[-_MAX_LIST_ITEMS:]

    def add_error(self, error: str) -> None:
        if error and error not in self.errors:
            self.errors = (self.errors + [error])[-_MAX_LIST_ITEMS:]

    def add_assumption(self, assumption: str) -> None:
        if assumption and assumption not in self.assumptions:
            self.assumptions = (self.assumptions + [assumption])[-_MAX_LIST_ITEMS:]

    def add_source(self, source: str) -> None:
        if source and source not in self.sources:
            self.sources = (self.sources + [source])[-_MAX_LIST_ITEMS:]

    def to_summary(self) -> dict[str, Any]:
        """Compact, storage-safe summary of the entire blackboard for diagnostics."""
        return {
            "subtaskResultCount": len(self.subtask_results),
            "capabilitiesUsed": sorted(self.capability_results),
            "warnings": list(self.warnings[:_MAX_LIST_ITEMS]),
            "errors": list(self.errors[:_MAX_LIST_ITEMS]),
            "assumptions": list(self.assumptions[:_MAX_LIST_ITEMS]),
            "sources": list(self.sources[:_MAX_LIST_ITEMS]),
            "proposedActionCount": len(self.proposed_action_summaries),
            "validationNotes": list(self.validation_notes[:_MAX_LIST_ITEMS]),
        }
