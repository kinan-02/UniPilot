"""Regression tests for retrieval profiles."""

from app.agent.schemas import AgentIntent
from app.retrieval.profiles import (
    get_profile,
    load_profile_config,
    primary_profile_for_intent,
    reset_profile_config_cache,
    select_profiles_for_intent,
)


def setup_function() -> None:
    reset_profile_config_cache()


def test_profile_config_loads_all_required_profiles():
    config = load_profile_config()
    required = {
        "course_exact_lookup",
        "course_semantic_search",
        "catalog_requirement_lookup",
        "requirement_explanation",
        "semester_offering_lookup",
        "semester_planning_retrieval",
        "general_catalog_question",
        "transcript_course_matching",
        "fallback_academic_search",
    }
    assert required.issubset(set(config.profiles.keys()))


def test_intent_maps_to_expected_primary_profile():
    profile = primary_profile_for_intent("course_question", entities={"courseNumber": "00940139"})
    assert profile.profileName == "course_exact_lookup"

    planning = primary_profile_for_intent("semester_plan_generation", entities={})
    assert planning.profileName == "semester_planning_retrieval"


def test_course_question_selects_multiple_profiles():
    profiles = select_profiles_for_intent(
        "course_question",
        entities={"courseNumber": "00940139"},
    )
    names = [profile.profileName for profile in profiles]
    assert "course_exact_lookup" in names
    assert "semester_offering_lookup" in names


def test_profile_has_latency_budget():
    profile = get_profile("course_exact_lookup")
    assert profile.latencyBudgetMs > 0
    assert profile.wikiChunksFinal >= 0
