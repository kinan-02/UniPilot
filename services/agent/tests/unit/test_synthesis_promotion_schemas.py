"""Unit tests for synthesis text promotion schemas (Phase 22)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.synthesis.promotion_schemas import (
    SynthesisTextPromotionDecision,
    SynthesisTextPromotionReason,
)


def test_synthesis_text_promotion_decision_parses() -> None:
    decision = SynthesisTextPromotionDecision(status="blocked", mode="shadow_only")
    assert decision.promoted is False


def test_reasons_parse() -> None:
    reason = SynthesisTextPromotionReason(code="shadow_only", severity="info")
    assert reason.details == {}


def test_defaults_are_safe() -> None:
    decision = SynthesisTextPromotionDecision(status="skipped")
    assert decision.promoted is False
    assert decision.live_blocks_preserved is True


def test_forbidden_chain_of_thought_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        SynthesisTextPromotionDecision.model_validate(
            {"status": "blocked", "chain_of_thought": "secret"}
        )
