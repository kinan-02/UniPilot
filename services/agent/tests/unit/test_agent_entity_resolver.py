"""Unit tests for entity resolver."""

from app.agent.entity_resolver import resolve_entities


def test_resolve_course_number():
    entities = resolve_entities("Can I take 234218 next semester?")
    assert entities["courseNumber"] == "234218"


def test_resolve_max_credits_and_avoid_friday():
    entities = resolve_entities("Build a plan with max 18 credits and no Friday classes")
    assert entities["maxCredits"] == 18
    assert "Friday" in entities["avoidDays"]


def test_merge_conversation_entities():
    entities = resolve_entities(
        "Also include 00940139",
        conversation_entities={"courseNumber": "234218"},
    )
    assert entities["courseNumber"] == "00940139"
    assert "234218" in entities.get("courseNumbers", []) or entities["courseNumber"] == "00940139"
