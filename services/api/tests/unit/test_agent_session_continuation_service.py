"""Unit tests for agent session continuation helpers."""

from __future__ import annotations

from app.services.agent_session_continuation_service import build_second_opinion_constraints


def test_build_second_opinion_constraints() -> None:
    constraints = build_second_opinion_constraints(
        source_session_id="source-1",
        utility_profile="aggressive",
        base_constraints={"maxCredits": 20},
    )
    assert constraints["utilityProfile"] == "aggressive"
    assert constraints["secondOpinionOf"] == "source-1"
    assert constraints["maxCredits"] == 20
