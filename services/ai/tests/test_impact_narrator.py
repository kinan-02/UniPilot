"""Unit tests for impact narrator."""

from __future__ import annotations

from app.services.impact_narrator import narrate_simulation_impact


def test_template_narrative_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    narrative = narrate_simulation_impact(
        scenario_name="Drop course",
        operations=[{"type": "drop_course", "courseNumber": "00940219"}],
        before_snapshot={"graduation": {"completedCredits": 10}},
        after_snapshot={"graduation": {"completedCredits": 6.5}},
        deltas={"progress": {"completedCreditsDelta": -3.5, "creditsRemainingDelta": 3.5}},
    )
    assert "10" in narrative
    assert "6.5" in narrative
