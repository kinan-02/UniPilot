"""Build retrieval plan from intent, profiles, and task needs (spec §11)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentIntent, IntentClassification, TaskPlan
from app.retrieval.profiles import (
    intent_omits_student_profile,
    primary_profile_for_intent,
    profile_allows_structured_catalog,
    profile_allows_structured_offerings,
    profile_allows_wiki,
    select_profiles_for_intent,
)


def build_retrieval_plan(
    *,
    classification: IntentClassification,
    task_plan: TaskPlan,
    entities: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return ordered retrieval steps with explicit profile names."""
    profiles = select_profiles_for_intent(classification.intent, entities=entities)
    primary = primary_profile_for_intent(classification.intent, entities=entities)
    steps: list[dict[str, Any]] = []

    mongo_queries = _mongo_queries_for_intent(classification.intent)
    if mongo_queries:
        steps.append(
            {
                "source": "mongodb",
                "queries": mongo_queries,
                "profile": primary.profileName,
            }
        )

    if any(profile_allows_structured_catalog(profile) for profile in profiles):
        catalog_queries = _catalog_queries_for_intent(classification.intent)
        if catalog_queries:
            catalog_profile = next(
                (
                    profile.profileName
                    for profile in profiles
                    if profile_allows_structured_catalog(profile)
                ),
                primary.profileName,
            )
            steps.append(
                {
                    "source": "structured_catalog",
                    "queries": catalog_queries,
                    "profile": catalog_profile,
                }
            )

    if any(profile_allows_structured_offerings(profile) for profile in profiles):
        offering_queries = _offering_queries_for_intent(classification.intent, entities)
        if offering_queries:
            offering_profile = next(
                (
                    profile.profileName
                    for profile in profiles
                    if profile_allows_structured_offerings(profile)
                ),
                "semester_offering_lookup",
            )
            steps.append(
                {
                    "source": "structured_offerings",
                    "queries": offering_queries,
                    "profile": offering_profile,
                }
            )

    wiki_profile = next((profile for profile in profiles if profile_allows_wiki(profile)), None)
    if wiki_profile and _needs_wiki(classification.intent):
        steps.append(
            {
                "source": "academic_graph",
                "mode": "wiki_graph_plus_semester_json",
                "query": _wiki_query(classification.intent, entities),
                "profile": wiki_profile.profileName,
            }
        )

    if not steps:
        steps.append(
            {
                "source": "mongodb",
                "queries": ["student_profile"],
                "profile": primary.profileName,
            }
        )

    return steps


def _mongo_queries_for_intent(intent: AgentIntent) -> list[str]:
    if intent_omits_student_profile(intent):
        return []
    mapping: dict[AgentIntent, list[str]] = {
        "graduation_progress_check": [
            "student_profile",
            "completed_courses",
            "degree_program",
            "catalog_year",
        ],
        "course_question": ["student_profile", "completed_courses"],
        "prerequisite_check": ["student_profile", "completed_courses"],
        "semester_plan_generation": [
            "student_profile",
            "completed_courses",
            "user_preferences",
            "saved_semester_plans",
        ],
        "semester_plan_modification": [
            "student_profile",
            "completed_courses",
            "saved_semester_plans",
        ],
        "requirement_explanation": ["student_profile", "degree_program"],
        "transcript_import": ["completed_courses", "student_profile"],
        "general_academic_question": ["student_profile"],
    }
    return list(mapping.get(intent, ["student_profile"]))


def _catalog_queries_for_intent(intent: AgentIntent) -> list[str]:
    if intent_omits_student_profile(intent):
        return []
    mapping: dict[AgentIntent, list[str]] = {
        "graduation_progress_check": ["degree_requirements"],
        "course_question": ["course_record", "prerequisiteResult", "requirement_contribution"],
        "prerequisite_check": ["course_record", "prerequisiteResult", "requirement_contribution"],
        "semester_plan_generation": ["degree_requirements"],
        "requirement_explanation": ["degree_requirements"],
        "catalog_search": ["course_record"],
        "transcript_import": ["course_record"],
    }
    return list(mapping.get(intent, []))


def _offering_queries_for_intent(
    intent: AgentIntent,
    entities: dict[str, Any],
) -> list[dict[str, Any] | str]:
    if intent not in {
        "course_question",
        "semester_plan_generation",
        "prerequisite_check",
        "semester_plan_modification",
    }:
        return []

    course_number = entities.get("courseNumber")
    semester = entities.get("targetSemesterCode") or entities.get("targetSemester")
    if course_number and semester:
        return [{"semester": str(semester), "courseNumber": str(course_number)}]
    if course_number:
        return [{"courseNumber": str(course_number)}]
    if intent in {"semester_plan_generation", "semester_plan_modification"} and semester:
        return [str(semester)]
    return []


def _needs_wiki(intent: AgentIntent) -> bool:
    return intent in {
        "graduation_progress_check",
        "course_question",
        "requirement_explanation",
        "general_academic_question",
        "catalog_search",
        "semester_plan_generation",
        "semester_plan_modification",
        "transcript_import",
        "program_minor_lookup",
        "track_structure_lookup",
        "regulation_lookup",
    }


def _wiki_query(intent: AgentIntent, entities: dict[str, Any]) -> str:
    if entities.get("courseNumber"):
        return f"{entities['courseNumber']} prerequisites requirements"
    if entities.get("courseName"):
        return str(entities["courseName"])
    prompts: dict[AgentIntent, str] = {
        "graduation_progress_check": "graduation requirements degree completion",
        "requirement_explanation": "requirement bucket elective explanation",
        "semester_plan_generation": "semester planning requirements",
        "semester_plan_modification": "semester plan modification",
        "catalog_search": "catalog course requirements",
        "transcript_import": "transcript course catalog match",
    }
    return prompts.get(intent, "academic requirements")
