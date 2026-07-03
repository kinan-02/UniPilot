"""Refine wiki retrieval between agentic attempts (Agent_RAG_tuning.md §16)."""

from __future__ import annotations

from typing import Any, Literal

from app.agent.query_decomposer import DecomposedQuery, decompose_retrieval_query
from app.agent.schemas import AgentIntent

RetrievalAttemptMode = Literal["strict", "relaxed", "fallback"]


def attempt_mode_for_index(attempt_index: int) -> RetrievalAttemptMode:
    if attempt_index <= 0:
        return "strict"
    if attempt_index == 1:
        return "relaxed"
    return "fallback"


def wiki_profile_for_attempt(
    *,
    attempt_index: int,
    default_profile_name: str,
) -> str:
    if attempt_index >= 2:
        return "fallback_academic_search"
    return default_profile_name


def refine_decomposed_queries(
    *,
    user_message: str,
    intent: AgentIntent,
    entities: dict[str, Any],
    base_wiki_query: str,
    gaps: list[str],
    attempt_index: int,
) -> list[DecomposedQuery]:
    queries = decompose_retrieval_query(
        user_message=user_message,
        intent=intent,
        entities=entities,
        base_wiki_query=base_wiki_query,
    )
    if attempt_index <= 0 or not gaps:
        return queries

    refined: list[DecomposedQuery] = list(queries)
    seen = {query.text.lower() for query in refined}

    def add(text: str, facet: str) -> None:
        normalized = text.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        refined.append(DecomposedQuery(text=text.strip(), facet=facet, source="refined"))

    if "missing_wiki" in gaps or "thin_wiki_context" in gaps:
        add(base_wiki_query, "retry_base")
        if entities.get("track"):
            add(f"{entities['track']} requirements explanation", "track_retry")

    if "low_wiki_confidence" in gaps:
        add(user_message, "user_message_retry")

    if "missing_offering" in gaps and entities.get("courseNumber"):
        semester = entities.get("targetSemesterCode") or "next semester"
        add(f"{entities['courseNumber']} {semester} offering", "offering_retry")

    if "missing_structured_course" in gaps and entities.get("courseNumber"):
        add(f"{entities['courseNumber']} catalog course page", "course_retry")

    if attempt_index >= 2:
        add(f"{user_message} academic catalog requirements", "broad_fallback")

    return refined[:5]
