"""Unit tests for conversation memory assumptions."""

from app.agent.conversation_memory import assumptions_from_entities


def test_assumptions_from_entities_avoid_days():
    assumptions = assumptions_from_entities({"avoidDays": ["Friday"], "maxCredits": 16})
    assert any("Friday" in item for item in assumptions)
    assert any("16" in item for item in assumptions)
