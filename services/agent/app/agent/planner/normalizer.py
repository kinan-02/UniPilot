"""Reconcile/validate LLM-produced `PlannerOutput` candidates (Phase 5).

This module never talks to an LLM and never touches the database. It only
validates a `PlannerOutput` that already passed `ReasoningBlock`'s
JSON-schema validation against rules the schema can't express: capability
names must exist in (and be enabled in) the live `CapabilityRegistry`,
subtask ids must be unique, dependencies must reference existing subtasks
and form an acyclic graph, and write-risk/confirmation fields must be
internally consistent. It never lets a hallucinated capability, a broken
dependency graph, or an under-confirmed write survive into the returned
plan.

Returns `None` when the plan is unusable after normalization (e.g. every
subtask referenced an invalid capability, or a dependency cycle survives
edge-stripping) — the caller (`planner.agent.build_execution_plan`) falls
back to the deterministic legacy plan in that case.
"""

from __future__ import annotations

import re
from typing import get_args

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.context_compiler.context_sections import ALL_CONTEXT_SECTIONS
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.schemas import AgentIntent

_SUPPORTED_INTENTS: frozenset[str] = frozenset(get_args(AgentIntent))
_UNKNOWN_INTENT_VALUE = "unknown_or_unsupported"

_VALID_EXECUTION_MODES: frozenset[str] = frozenset(
    {
        "deterministic_workflow",
        "single_capability",
        "multi_capability_graph",
        "clarification",
        "unsupported",
    }
)
_VALID_AUTONOMY_LEVELS: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5})
_WRITE_RISK_RANK: dict[str, int] = {"none": 0, "possible": 1, "explicit": 2}

# Same heuristic family as `task_understanding.normalizer._EXPLICIT_WRITE_VERBS`
# (kept local rather than imported — a small, stable, intentionally duplicated
# heuristic, same precedent as `task_understanding.agent._SUPPORTED_WORKFLOWS`).
_EXPLICIT_WRITE_VERBS = re.compile(
    r"\b(save|commit|apply|confirm|persist|store|import|update)\b", re.IGNORECASE
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _looks_like_explicit_write_request(text: str) -> bool:
    return bool(_EXPLICIT_WRITE_VERBS.search(text or ""))


def _reconcile_primary_intent(
    intent: str, *, deterministic_intent: str | None, warnings: list[str]
) -> str:
    if intent in _SUPPORTED_INTENTS:
        return intent
    warnings.append(f"unsupported_primary_intent_replaced: '{intent}' is not a supported intent")
    if deterministic_intent and deterministic_intent in _SUPPORTED_INTENTS:
        return deterministic_intent
    return _UNKNOWN_INTENT_VALUE


def _reconcile_execution_mode(mode: str, warnings: list[str]) -> str:
    if mode in _VALID_EXECUTION_MODES:
        return mode
    warnings.append(f"invalid_execution_mode_defaulted: {mode!r} -> unsupported")
    return "unsupported"


def _reconcile_autonomy_level(level: int, warnings: list[str]) -> int:
    if level in _VALID_AUTONOMY_LEVELS:
        return level
    warnings.append(f"invalid_autonomy_level_clamped: {level!r} -> 2")
    return 2


def _valid_context_sections(sections: list[str], *, warnings: list[str], subtask_id: str) -> list[str]:
    valid = [section for section in sections if section in ALL_CONTEXT_SECTIONS]
    dropped = [section for section in sections if section not in ALL_CONTEXT_SECTIONS]
    for section in dropped:
        warnings.append(f"unknown_context_section_dropped: subtask={subtask_id} section={section}")
    return valid


def _is_explicit_write_subtask(subtask: PlannerSubtask) -> bool:
    if subtask.kind == "propose_action":
        return True
    return _looks_like_explicit_write_request(f"{subtask.title} {subtask.objective}")


def _drop_invalid_capabilities(
    subtasks: list[PlannerSubtask], *, registry: CapabilityRegistry, warnings: list[str]
) -> list[PlannerSubtask]:
    survivors: list[PlannerSubtask] = []
    for subtask in subtasks:
        capability = registry.get(subtask.capability_name)
        if capability is None:
            warnings.append(
                f"unknown_capability_dropped: subtask={subtask.id} capability={subtask.capability_name}"
            )
            continue
        if not capability.enabled:
            warnings.append(
                f"disabled_capability_dropped: subtask={subtask.id} capability={subtask.capability_name}"
            )
            continue
        survivors.append(subtask)
    return survivors


def _dedupe_subtask_ids(subtasks: list[PlannerSubtask], *, warnings: list[str]) -> list[PlannerSubtask]:
    seen_ids: set[str] = set()
    deduplicated: list[PlannerSubtask] = []
    for subtask in subtasks:
        if not subtask.id or subtask.id in seen_ids:
            warnings.append(f"duplicate_or_missing_subtask_id_dropped: {subtask.id!r}")
            continue
        seen_ids.add(subtask.id)
        deduplicated.append(subtask)
    return deduplicated


def _clean_dependencies_and_context(
    subtasks: list[PlannerSubtask], *, warnings: list[str]
) -> list[PlannerSubtask]:
    valid_ids = {subtask.id for subtask in subtasks}
    cleaned: list[PlannerSubtask] = []
    for subtask in subtasks:
        depends_on = [dep for dep in subtask.depends_on if dep in valid_ids and dep != subtask.id]
        for dep in subtask.depends_on:
            if dep not in depends_on:
                warnings.append(f"invalid_dependency_dropped: subtask={subtask.id} depends_on={dep}")

        required_context_sections = _valid_context_sections(
            subtask.required_context_sections, warnings=warnings, subtask_id=subtask.id
        )

        requires_confirmation = subtask.requires_user_confirmation or _is_explicit_write_subtask(subtask)
        risk_level = subtask.risk_level
        if requires_confirmation and risk_level == "low":
            risk_level = "medium"

        cleaned.append(
            subtask.model_copy(
                update={
                    "depends_on": depends_on,
                    "required_context_sections": required_context_sections,
                    "requires_user_confirmation": requires_confirmation,
                    "risk_level": risk_level,
                }
            )
        )
    return cleaned


def _has_dependency_cycle(subtasks: list[PlannerSubtask]) -> bool:
    """DFS-based cycle detection over the `id -> depends_on` adjacency."""
    graph = {subtask.id: subtask.depends_on for subtask in subtasks}
    unvisited, in_progress, done = 0, 1, 2
    state = dict.fromkeys(graph, unvisited)

    def visit(node: str) -> bool:
        state[node] = in_progress
        for neighbor in graph.get(node, []):
            if neighbor not in state:
                continue
            if state[neighbor] == in_progress:
                return True
            if state[neighbor] == unvisited and visit(neighbor):
                return True
        state[node] = done
        return False

    return any(state[node] == unvisited and visit(node) for node in graph)


def normalize_planner_output(
    candidate: PlannerOutput,
    *,
    registry: CapabilityRegistry,
    user_message: str,
    deterministic_intent: str | None,
) -> PlannerOutput | None:
    """Validate/repair `candidate` in place; return `None` if it's unusable.

    Never raises — always returns either a fully valid `PlannerOutput` or
    `None` (signaling the caller should fall back to the deterministic plan).
    """
    warnings = list(candidate.warnings)

    primary_intent = _reconcile_primary_intent(
        candidate.primary_intent, deterministic_intent=deterministic_intent, warnings=warnings
    )
    execution_mode = _reconcile_execution_mode(candidate.execution_mode, warnings)
    autonomy_level = _reconcile_autonomy_level(candidate.recommended_autonomy_level, warnings)
    confidence = _clamp01(candidate.confidence)

    subtasks = _dedupe_subtask_ids(candidate.subtasks, warnings=warnings)
    subtasks = _drop_invalid_capabilities(subtasks, registry=registry, warnings=warnings)
    subtasks = _clean_dependencies_and_context(subtasks, warnings=warnings)

    if candidate.subtasks and not subtasks:
        # Every proposed subtask was invalid — the plan carries no usable work.
        warnings.append("all_subtasks_invalid_after_normalization")
        return None

    if _has_dependency_cycle(subtasks):
        warnings.append("dependency_cycle_detected")
        return None

    plan_requires_confirmation = candidate.requires_user_confirmation or any(
        subtask.requires_user_confirmation for subtask in subtasks
    )
    explicit_write_request = _looks_like_explicit_write_request(user_message)
    if explicit_write_request:
        plan_requires_confirmation = True

    write_risk = candidate.write_risk if candidate.write_risk in _WRITE_RISK_RANK else "none"
    if plan_requires_confirmation and _WRITE_RISK_RANK[write_risk] < _WRITE_RISK_RANK["possible"]:
        write_risk = "possible"
    if explicit_write_request:
        write_risk = "explicit"

    return candidate.model_copy(
        update={
            "primary_intent": primary_intent,
            "execution_mode": execution_mode,
            "recommended_autonomy_level": autonomy_level,
            "confidence": confidence,
            "subtasks": subtasks,
            "requires_user_confirmation": plan_requires_confirmation,
            "write_risk": write_risk,
            "warnings": warnings,
        }
    )
