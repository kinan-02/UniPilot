"""Unit tests for centralized agent LLM prompts."""

from app.agent.llm_prompts import (
    build_explanation_human,
    build_explanation_system,
    build_intent_classifier_system,
    build_preference_extractor_system,
    detect_message_language,
    language_instruction,
)
from app.agent.schemas import AgentContextPack, AgentResponse


def test_detect_message_language_hebrew():
    assert detect_message_language("מה חסר לי לסיים את התואר?") == "he"


def test_detect_message_language_english():
    assert detect_message_language("What am I missing to graduate?") == "en"


def test_language_instruction_matches_hebrew():
    assert "Hebrew" in language_instruction("מה חסר?")


def test_intent_classifier_system_includes_all_intents():
    system = build_intent_classifier_system(
        valid_intents=["graduation_progress_check", "course_question"]
    )
    assert "graduation_progress_check" in system
    assert "course_question" in system
    assert "JSON" in system


def test_preference_extractor_system_includes_schema():
    system = build_preference_extractor_system()
    assert "maxCredits" in system
    assert "avoidDays" in system
    assert "never invent" in system.lower() or "Never invent" in system


def test_explanation_system_intent_specific():
    system = build_explanation_system(
        intent="graduation_progress_check",
        user_message="What am I missing?",
    )
    assert "graduation" in system.lower()
    assert "NEVER invent" in system or "never invent" in system.lower()


def test_explanation_human_includes_baseline():
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "234218"},
    )
    response = AgentResponse(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="You may take this course next semester.",
        warnings=["offering_unconfirmed"],
    )
    human = build_explanation_human(
        user_message="Can I take 234218?",
        response=response,
        context=context,
        wiki_context="Catalog note about the course.",
    )
    assert "234218" in human
    assert "You may take this course" in human
    assert "offering_unconfirmed" in human
