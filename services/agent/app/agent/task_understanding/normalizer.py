"""Reconcile/validate LLM-produced `TaskUnderstandingOutput` candidates.

This module never talks to an LLM. It only checks a `TaskUnderstandingOutput`
that already passed `ReasoningBlock`'s JSON-schema validation against
project-specific rules the schema can't express (mainly: supported intent
values), and applies a couple of conservative, deterministic safety nets
(explicit-write detection, confidence clamping). It never lets the LLM's
classification silently override the deterministic intent in Phase 3 — it
only annotates disagreement with a warning for future phases to consume.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.agent.task_understanding.schemas import (
    AutonomyLevel,
    SuggestedNextLayer,
    TaskUnderstandingOutput,
)

# Presence of any of these verbs is treated as a strong signal that the user
# is explicitly asking for a write/mutation (save/import/apply/etc.), on top
# of whatever the LLM itself reported. This is a diagnostic heuristic only —
# the actual write gate remains `task_planner.py`'s deterministic mapping.
_EXPLICIT_WRITE_VERBS = re.compile(
    r"\b(save|commit|apply|confirm|persist|store)\b", re.IGNORECASE
)

# "Strongly conflicts" threshold: only warn when the deterministic classifier
# was itself confident, matching the bar `llm_intent_classifier` already uses
# to trust an LLM override (`_LLM_FALLBACK_THRESHOLD`).
_STRONG_CONFLICT_CONFIDENCE_THRESHOLD = 0.78

_VALID_AUTONOMY_LEVELS: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5})
_VALID_NEXT_LAYERS: frozenset[str] = frozenset(
    {"deterministic_workflow", "planner", "clarification", "unsupported"}
)


def _looks_like_explicit_write_request(message: str) -> bool:
    return bool(_EXPLICIT_WRITE_VERBS.search(message or ""))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _reconcile_intent(
    intent: str,
    *,
    supported_intents: frozenset[str],
    deterministic_intent: str | None,
    unknown_intent_value: str,
    warnings: list[str],
    field_label: str,
) -> str | None:
    if intent in supported_intents:
        return intent
    warnings.append(f"unsupported_{field_label}_replaced: '{intent}' is not a supported intent")
    if deterministic_intent and deterministic_intent in supported_intents:
        return deterministic_intent
    return unknown_intent_value


def _reconcile_secondary_intents(
    intents: Iterable[str],
    *,
    supported_intents: frozenset[str],
    primary_intent: str,
    warnings: list[str],
) -> list[str]:
    reconciled: list[str] = []
    for intent in intents:
        if intent == primary_intent:
            continue
        if intent in supported_intents:
            if intent not in reconciled:
                reconciled.append(intent)
        else:
            warnings.append(f"unsupported_secondary_intent_dropped: '{intent}'")
    return reconciled


def reconcile_task_understanding_output(
    candidate: TaskUnderstandingOutput,
    *,
    user_message: str,
    supported_intents: frozenset[str],
    deterministic_intent: str | None,
    deterministic_intent_confidence: float | None = None,
    unknown_intent_value: str,
) -> TaskUnderstandingOutput:
    """Validate `candidate` against supported enums and apply safety nets.

    Does not call the LLM. Never raises — always returns a fully valid
    `TaskUnderstandingOutput`.
    """
    warnings = list(candidate.warnings)

    primary_intent = _reconcile_intent(
        candidate.primary_intent,
        supported_intents=supported_intents,
        deterministic_intent=deterministic_intent,
        unknown_intent_value=unknown_intent_value,
        warnings=warnings,
        field_label="primary_intent",
    )
    secondary_intents = _reconcile_secondary_intents(
        candidate.secondary_intents,
        supported_intents=supported_intents,
        primary_intent=primary_intent,
        warnings=warnings,
    )

    strongly_conflicts = (
        deterministic_intent is not None
        and deterministic_intent in supported_intents
        and deterministic_intent != primary_intent
        and (deterministic_intent_confidence or 0.0) >= _STRONG_CONFLICT_CONFIDENCE_THRESHOLD
    )
    if strongly_conflicts:
        warnings.append(
            "llm_intent_conflicts_with_deterministic_intent: "
            f"llm='{primary_intent}' deterministic='{deterministic_intent}' "
            f"(deterministic_confidence={deterministic_intent_confidence:.2f})"
        )

    requires_confirmation = candidate.requires_user_confirmation
    write_risk = candidate.write_risk
    if _looks_like_explicit_write_request(user_message):
        requires_confirmation = True
        write_risk = "explicit"

    autonomy_level: AutonomyLevel = candidate.recommended_autonomy_level
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        warnings.append(f"invalid_autonomy_level_clamped: {autonomy_level!r} -> 2")
        autonomy_level = 2

    next_layer: SuggestedNextLayer = candidate.suggested_next_layer
    if next_layer not in _VALID_NEXT_LAYERS:
        warnings.append(f"invalid_suggested_next_layer_defaulted: {next_layer!r} -> deterministic_workflow")
        next_layer = "deterministic_workflow"

    return candidate.model_copy(
        update={
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "requires_user_confirmation": requires_confirmation,
            "write_risk": write_risk,
            "recommended_autonomy_level": autonomy_level,
            "suggested_next_layer": next_layer,
            "intent_confidence": _clamp01(candidate.intent_confidence),
            "overall_confidence": _clamp01(candidate.overall_confidence),
            "warnings": warnings,
        }
    )
