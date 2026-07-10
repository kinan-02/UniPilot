"""Regression tests for retrieval profiles.

Intent-coupled cases (`select_profiles_for_intent`/`primary_profile_for_intent`)
were removed along with those functions -- profile selection is no longer
keyed by the old `AgentIntent` enum (see docs/agent/TOOL_PRIMITIVES_PROGRESS.md).
"""

from app.retrieval.profiles import get_profile, load_profile_config, reset_profile_config_cache


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


def test_profile_has_latency_budget():
    profile = get_profile("course_exact_lookup")
    assert profile.latencyBudgetMs > 0
    assert profile.wikiChunksFinal >= 0
