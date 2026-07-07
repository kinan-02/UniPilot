"""Deterministic safety checks for synthesis candidate text (Phase 22)."""

from __future__ import annotations

import re
from typing import Any

from app.agent.synthesis.promotion_schemas import SynthesisTextPromotionReason

_DEFAULT_MAX_CHARS = 5000

_FORBIDDEN_PAYLOAD_MARKERS: tuple[str, ...] = (
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
    "raw_context",
    "compiled_context",
    "raw_prompt",
    "system_prompt",
    "retrievalmetadata",
    "agentcontextpack",
    "raw_blocks",
    "proposed_action_payload",
    '"proposed_actions"',
    '"proposedactions"',
    '"blocks":',
    "```json",
    "transcript_rows",
    "transcript_row:",
    "full_catalog",
    "catalog_dump",
)

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
    "i modified your transcript",
    "i updated your plan",
    "i created an action",
    "i created a proposal",
    "i created an action proposal",
    "i proposed an action",
    "your profile has been updated",
    "your plan has been saved",
    "the transcript has been imported",
    "has been saved to your account",
)

_CERTAINTY_PHRASES: tuple[str, ...] = (
    "definitely ",
    "certainly ",
    "guaranteed ",
    "without a doubt",
    "100% sure",
)

_INTERNAL_ID_RE = re.compile(r"\b(?:ObjectId|[0-9a-f]{24})\b", re.IGNORECASE)


def _reason(code: str, severity: str = "error", **details: Any) -> SynthesisTextPromotionReason:
    return SynthesisTextPromotionReason(code=code, severity=severity, details=details)


def check_synthesis_candidate_safety(
    candidate_text: str | None,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    uncertainty_notes: list[str] | None = None,
) -> list[SynthesisTextPromotionReason]:
    """Return empty list when candidate text is safe to promote. Never raises."""
    try:
        if candidate_text is None or not str(candidate_text).strip():
            return [_reason("candidate_empty")]

        text = str(candidate_text)
        reasons: list[SynthesisTextPromotionReason] = []

        limit = max(1, int(max_chars or _DEFAULT_MAX_CHARS))
        if len(text) > limit:
            reasons.append(_reason("candidate_too_long", length=len(text), maxChars=limit))

        lowered = text.lower()
        if any(marker in lowered for marker in _FORBIDDEN_PAYLOAD_MARKERS):
            reasons.append(_reason("candidate_raw_payload_marker"))

        if any(phrase in lowered for phrase in _WRITE_CLAIM_PHRASES):
            reasons.append(_reason("candidate_write_claim"))

        if any(marker in lowered for marker in ("chain_of_thought", "scratchpad", "hidden_reasoning")):
            reasons.append(_reason("candidate_chain_of_thought_marker"))

        if any(
            phrase in lowered
            for phrase in ("created an action proposal", "proposed action was created", "action proposal created")
        ):
            reasons.append(_reason("candidate_action_proposal_claim"))

        notes = [note for note in (uncertainty_notes or []) if isinstance(note, str) and note.strip()]
        if notes and any(phrase in lowered for phrase in _CERTAINTY_PHRASES):
            reasons.append(_reason("candidate_unsupported_certainty", uncertaintyNoteCount=len(notes)))

        if _INTERNAL_ID_RE.search(text):
            reasons.append(_reason("candidate_internal_id_leak"))

        return reasons
    except Exception:  # noqa: BLE001
        return [_reason("candidate_raw_payload_marker")]
