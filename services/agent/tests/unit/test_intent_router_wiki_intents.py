"""Intent routing for wiki-only lookup intents."""

from app.agent.intent_router import classify_intent


def test_robotics_minor_routes_to_program_minor_lookup() -> None:
    result = classify_intent(
        "I'm a DDS student interested in the Inter-Faculty Robotics Minor. "
        "What are the admission requirements?"
    )
    assert result.intent == "program_minor_lookup"


def test_bme_track_routes_to_track_structure_lookup() -> None:
    result = classify_intent(
        "What is the total credit requirement for the Biomedical Engineering BSc track, "
        "and how are the credits broken down by category?"
    )
    assert result.intent == "track_structure_lookup"


def test_max_credits_routes_to_regulation_lookup() -> None:
    result = classify_intent(
        "What is the maximum number of credits I can take in a single semester "
        "at Technion without special approval?"
    )
    assert result.intent == "regulation_lookup"


def test_dual_degree_routes_to_regulation_lookup() -> None:
    result = classify_intent(
        "I'm enrolled in a 4-year CS track (155 credits required) and want to add "
        "a second degree in Industrial Engineering & Management (155 credits required). "
        "How many total credits will I need to complete both degrees?"
    )
    assert result.intent == "regulation_lookup"
