"""Build text-only promoted AgentResponse from synthesis candidate (Phase 22)."""

from __future__ import annotations

import logging

from app.agent.schemas import AgentResponse

logger = logging.getLogger(__name__)


def build_synthesis_text_promoted_response(
    *,
    live_response: AgentResponse,
    candidate_text: str,
) -> AgentResponse:
    """Copy `live_response`, replacing only `text`. Never mutates `live_response`."""
    try:
        if not isinstance(live_response, AgentResponse):
            return live_response
        return live_response.model_copy(update={"text": str(candidate_text)})
    except Exception:  # noqa: BLE001
        logger.exception("synthesis_text_promoted_response_build_failed")
        return live_response
