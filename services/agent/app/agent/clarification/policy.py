"""Deterministic clarification decision policy (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.schemas import ClarificationAction, ClarificationDecision, ClarificationNeed


def decide_clarification_action(need: ClarificationNeed) -> ClarificationDecision:
    """Decide whether to ask, assume, resolve epistemically, or skip."""
    try:
        return _decide(need)
    except Exception:  # noqa: BLE001 — policy must never raise
        return ClarificationDecision(
            need_id=need.id if isinstance(need, ClarificationNeed) else "unknown",
            action="skip",
            reason="policy_error_fallback_skip",
            confidence=0.2,
        )


def _decide(need: ClarificationNeed) -> ClarificationDecision:
    strong_default = _has_strong_default(need)
    retrievable = bool(need.evidence.get("retrievableEpistemic"))

    if need.ambiguity_type == "preference":
        return _decide_preference(need, strong_default=strong_default)
    if need.ambiguity_type == "epistemic":
        return _decide_epistemic(need, retrievable=retrievable, strong_default=strong_default)
    if need.ambiguity_type == "mixed":
        if need.consequence == "high":
            return ClarificationDecision(
                need_id=need.id,
                action="ask_user",
                reason="mixed_high_consequence_preference_component",
                confidence=0.75,
            )
        if retrievable:
            return ClarificationDecision(
                need_id=need.id,
                action="resolve_epistemically",
                reason="mixed_epistemic_component_retrievable",
                confidence=0.65,
            )
        if need.default_assumption:
            return ClarificationDecision(
                need_id=need.id,
                action="assume_default",
                reason="mixed_assume_default",
                confidence=0.5,
                selected_default=need.default_assumption,
            )
        return ClarificationDecision(
            need_id=need.id,
            action="skip",
            reason="mixed_no_safe_action",
            confidence=0.4,
        )

    if need.default_assumption:
        return ClarificationDecision(
            need_id=need.id,
            action="assume_default",
            reason="unknown_assume_default_conservatively",
            confidence=0.35,
            selected_default=need.default_assumption,
        )
    return ClarificationDecision(
        need_id=need.id,
        action="skip",
        reason="unknown_skip_conservatively",
        confidence=0.3,
    )


def _decide_preference(need: ClarificationNeed, *, strong_default: bool) -> ClarificationDecision:
    if need.consequence == "high":
        return ClarificationDecision(
            need_id=need.id,
            action="ask_user",
            reason="preference_high_consequence",
            confidence=0.85,
        )
    if need.consequence == "medium":
        if strong_default:
            return ClarificationDecision(
                need_id=need.id,
                action="assume_default",
                reason="preference_medium_strong_default",
                confidence=0.6,
                selected_default=need.default_assumption,
            )
        return ClarificationDecision(
            need_id=need.id,
            action="ask_user",
            reason="preference_medium_no_strong_default",
            confidence=0.7,
        )
    if need.default_assumption:
        return ClarificationDecision(
            need_id=need.id,
            action="assume_default",
            reason="preference_low_assume_default",
            confidence=0.55,
            selected_default=need.default_assumption,
        )
    return ClarificationDecision(
        need_id=need.id,
        action="skip",
        reason="preference_low_no_default",
        confidence=0.45,
    )


def _decide_epistemic(need: ClarificationNeed, *, retrievable: bool, strong_default: bool) -> ClarificationDecision:
    if retrievable:
        return ClarificationDecision(
            need_id=need.id,
            action="resolve_epistemically",
            reason="epistemic_retrievable",
            confidence=0.7,
        )
    if need.default_assumption:
        return ClarificationDecision(
            need_id=need.id,
            action="assume_default",
            reason="epistemic_assume_default",
            confidence=0.45 if not strong_default else 0.55,
            selected_default=need.default_assumption,
        )
    return ClarificationDecision(
        need_id=need.id,
        action="skip",
        reason="epistemic_skip",
        confidence=0.4,
    )


def _has_strong_default(need: ClarificationNeed) -> bool:
    default = (need.default_assumption or "").strip()
    if len(default) < 12:
        return False
    if need.evidence.get("strongDefault") is True:
        return True
    return len(default.split()) >= 3
