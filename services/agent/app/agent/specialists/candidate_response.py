"""Layer 3 — maps a specialist agent's real output to a live-turn candidate.

`build_specialist_candidate_response` is the sole bridge between
`SpecialistAgentOutput` (Phase 10) and `AgentResponse` for
`planner_first_live.run_planner_first_live_turn`'s `candidate_sink`. It is
deliberately **narrower** than Phase 14's own specialist-text-promotion gate
(`specialists.text_promotion.evaluate_specialist_text_promotion`), which
also requires Phase 11 validation/comparison metadata computed elsewhere in
the turn -- this function only ever sees one `SpecialistAgentOutput` in
isolation, so it applies the subset of Phase 14's checks that are
self-contained: status, confidence floor, no missing context, and
`answer_text` safety via the exact same `answer_text_safety.check_answer_text_safety`
scanner Phase 14 uses.

Text-only, by deliberate design (mirrors Phase 14's own permanent scope,
not just a stepping stone): `output.sources` (`list[dict]`) and
`output.warnings` (free-form specialist-authored strings) are never passed
through -- neither is scanned by anything, and `sources`'s shape doesn't
even match `AgentResponse.used_sources`'s (`list[str]`). No new UI block
type is introduced either; specialists producing genuinely typed structured
blocks is explicit future work requiring its own frontend changes.
"""

from __future__ import annotations

import logging

from app.agent.response_composer import compose_response
from app.agent.schemas import AgentResponse
from app.agent.specialists.answer_text_safety import check_answer_text_safety
from app.agent.specialists.schemas import SpecialistAgentOutput
from app.config import Settings

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE = 0.85


def build_specialist_candidate_response(
    output: SpecialistAgentOutput,
    *,
    conversation_id: str,
    run_id: str,
    settings: Settings,
) -> AgentResponse | None:
    """`None` unless every gate holds; never raises.

    Mirrors Phase 14's own self-contained gates (status, confidence floor,
    no missing context, safe non-empty `answer_text`) -- see module
    docstring for why this is narrower than the full Phase 14 gate.
    """
    try:
        if output.status != "completed":
            return None
        if output.confidence < _MIN_CONFIDENCE:
            return None
        if output.missing_context:
            return None

        answer_text = output.result.get("answer_text") if isinstance(output.result, dict) else None
        if not answer_text or not str(answer_text).strip():
            return None

        reasons = check_answer_text_safety(
            answer_text, max_chars=settings.resolved_agent_specialist_text_promotion_max_chars()
        )
        if reasons:
            return None

        return compose_response(
            conversation_id=conversation_id,
            message_id="",
            run_id=run_id,
            text=str(answer_text),
        )
    except Exception:  # noqa: BLE001 -- must never break a live turn
        logger.exception("specialist_candidate_response_build_failed", extra={"agentName": output.agent_name})
        return None


__all__ = ["build_specialist_candidate_response"]
