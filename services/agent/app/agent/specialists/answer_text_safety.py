"""Deterministic safety checks for specialist-generated `answer_text` (Phase 14).

Pure functions only — no I/O, no LLM calls, no database access. Applied to
`SpecialistAgentOutput.result["answer_text"]` before it is ever allowed to
replace `AgentResponse.text` (see `text_promotion.evaluate_specialist_text_promotion`).

Deliberately a simple, deterministic keyword/marker scan — not an NLP
classifier — matching the rest of the codebase's forbidden-key/forbidden-
token scanning style (`supervisor.validation_schemas.scan_for_forbidden_keys`,
`specialists.tools.safety.sanitize_observation_payload`).
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.text_promotion_schemas import SpecialistTextPromotionReason

DEFAULT_ANSWER_TEXT_MAX_CHARS = 4000

# Markers indicating the specialist leaked something it never should have --
# raw diagnostic/internal-reasoning key names, raw JSON-shaped block/action
# payloads, raw transcript rows, or a raw catalog dump. All fold into the
# single `specialist_answer_text_forbidden_payload` reason code.
_FORBIDDEN_PAYLOAD_MARKERS: tuple[str, ...] = (
    # Chain-of-thought / private-reasoning markers.
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
    # Raw context/prompt markers.
    "raw_context",
    "compiled_context",
    "raw_prompt",
    "system_prompt",
    "user_prompt",
    "raw_response",
    "raw_text",
    "full_text",
    # Raw block/action-payload markers.
    "raw_blocks",
    "full_blocks",
    "proposed_action_payload",
    '"actiontype"',
    '"proposedactions"',
    '"proposed_actions"',
    '"blocks":',
    "```json",
    # Raw transcript-row / raw-catalog-dump markers.
    "transcript_rows",
    "transcript_row:",
    "full_catalog",
    "raw_pdf_bytes",
    "catalog_dump",
)

# Phrases claiming a write/save/import/update/action-proposal happened.
# Case-insensitive substring match against the lowered answer text.
_WRITE_CLAIM_PHRASES: tuple[str, ...] = (
    "i updated",
    "i've updated",
    "i have updated",
    "i saved",
    "i've saved",
    "i have saved",
    "i imported",
    "i've imported",
    "i have imported",
    "i changed your profile",
    "i modified your profile",
    "i deleted",
    "i submitted",
    "i created an action",
    "i created a proposal",
    "i created an action proposal",
    "i proposed an action",
    "your profile has been updated",
    "your plan has been saved",
    "the transcript has been imported",
    "has been saved to your account",
    "i added this to your plan",
    "i've added this to your plan",
)


def _reason(code: str, severity: str = "error", **details: Any) -> SpecialistTextPromotionReason:
    return SpecialistTextPromotionReason(code=code, severity=severity, details=details)


def check_answer_text_safety(
    answer_text: str | None, *, max_chars: int = DEFAULT_ANSWER_TEXT_MAX_CHARS
) -> list[SpecialistTextPromotionReason]:
    """Deterministic safety scan over `answer_text`.

    Returns an empty list only when `answer_text` is safe to promote.
    Never raises: any unexpected input (non-string, huge, malformed)
    degrades to a `specialist_answer_text_forbidden_payload` reason rather
    than an exception escaping this function.
    """
    try:
        if answer_text is None:
            return [_reason("specialist_answer_text_empty")]
        text = str(answer_text)
        if not text.strip():
            return [_reason("specialist_answer_text_empty")]

        reasons: list[SpecialistTextPromotionReason] = []

        limit = max(1, int(max_chars or DEFAULT_ANSWER_TEXT_MAX_CHARS))
        if len(text) > limit:
            reasons.append(_reason("specialist_answer_text_too_long", length=len(text), maxChars=limit))

        lowered = text.lower()
        if any(marker in lowered for marker in _FORBIDDEN_PAYLOAD_MARKERS):
            reasons.append(_reason("specialist_answer_text_forbidden_payload"))

        if any(phrase in lowered for phrase in _WRITE_CLAIM_PHRASES):
            reasons.append(_reason("specialist_answer_text_write_claim"))

        return reasons
    except Exception:  # noqa: BLE001 — a safety scan must never raise into a caller
        return [_reason("specialist_answer_text_forbidden_payload")]


__all__ = ["DEFAULT_ANSWER_TEXT_MAX_CHARS", "check_answer_text_safety"]
