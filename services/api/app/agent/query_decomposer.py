"""Rules-first query decomposition for agentic multi-step wiki retrieval (spec §38 Phase 7)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agent.schemas import AgentIntent

_COURSE_NUMBER = re.compile(r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)")
_SPLIT_CLAUSES = re.compile(
    r"\s+(?:and|also|plus|as well as|בנוסף|וגם)\s+",
    re.IGNORECASE,
)
_OFFERING_TERMS = frozenset(
    {
        "offered",
        "offering",
        "semester",
        "next",
        "schedule",
        "מוצע",
        "סמסטר",
        "האם מוצע",
    }
)
_PREREQ_TERMS = frozenset(
    {
        "prerequisite",
        "prerequisites",
        "prereq",
        "קדם",
        "דרישות קדם",
        "דרישת קדם",
    }
)
_REQUIREMENT_TERMS = frozenset(
    {
        "requirement",
        "requirements",
        "graduate",
        "graduation",
        "credits",
        "elective",
        "bucket",
        "דרישות",
        "נקודות",
        "בחירה",
        "תואר",
    }
)


@dataclass(frozen=True)
class DecomposedQuery:
    text: str
    facet: str
    source: str = "derived"


def _tokenize_lower(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w\u0590-\u05FF]+", text or "")}


def _has_any(tokens: set[str], terms: frozenset[str]) -> bool:
    return any(term in tokens or term in " ".join(tokens) for term in terms)


def _course_query(course_number: str, facet: str) -> DecomposedQuery:
    prompts = {
        "prerequisites": f"{course_number} prerequisites requirements",
        "offering": f"{course_number} semester offering schedule",
        "contribution": f"{course_number} degree requirement contribution track",
    }
    return DecomposedQuery(
        text=prompts.get(facet, f"{course_number} course catalog"),
        facet=facet,
    )


def decompose_retrieval_query(
    *,
    user_message: str,
    intent: AgentIntent,
    entities: dict[str, Any],
    base_wiki_query: str,
) -> list[DecomposedQuery]:
    """Return ordered sub-queries for wiki retrieval (deduped, capped)."""
    message = (user_message or "").strip()
    if not message:
        return [DecomposedQuery(text=base_wiki_query, facet="general", source="base")]

    queries: list[DecomposedQuery] = []
    seen_text: set[str] = set()

    def add(text: str, facet: str, *, source: str = "derived") -> None:
        normalized = " ".join(text.split()).strip().lower()
        if not normalized or normalized in seen_text:
            return
        seen_text.add(normalized)
        queries.append(DecomposedQuery(text=text.strip(), facet=facet, source=source))

    add(base_wiki_query, "general", source="base")

    course_number = str(entities.get("courseNumber") or "").strip()
    numbers = list(dict.fromkeys(_COURSE_NUMBER.findall(message)))
    if course_number and course_number not in numbers:
        numbers.insert(0, course_number)
    elif not course_number and numbers:
        course_number = numbers[0]

    tokens = _tokenize_lower(message)
    if course_number:
        if _has_any(tokens, _PREREQ_TERMS) or intent in {"prerequisite_check", "course_question"}:
            add(_course_query(course_number, "prerequisites").text, "prerequisites")
        if _has_any(tokens, _OFFERING_TERMS) or entities.get("targetSemesterCode"):
            add(_course_query(course_number, "offering").text, "offering")
        if intent in {"course_question", "graduation_progress_check"}:
            add(_course_query(course_number, "contribution").text, "contribution")

    if intent in {"graduation_progress_check", "requirement_explanation"}:
        add("degree requirements graduation credits elective buckets", "requirements")
        if entities.get("track"):
            add(f"{entities['track']} track requirements electives", "track")

    if intent in {"semester_plan_generation", "semester_plan_modification"}:
        add("semester planning degree requirements eligible courses", "planning")

    clauses = [part.strip() for part in _SPLIT_CLAUSES.split(message) if part.strip()]
    if len(clauses) > 1:
        for clause in clauses:
            if len(clause) >= 12:
                add(clause, "clause", source="split")

    if _has_any(tokens, _REQUIREMENT_TERMS) and intent == "general_academic_question":
        add("academic requirements catalog explanation", "requirements")

    return queries[:4]
