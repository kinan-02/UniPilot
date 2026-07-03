"""Regulations RAG helpers for MAS policy Q&A vertical."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine


def _excerpt(text: str, *, limit: int = 480) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def search_regulation_citations(
    engine: AcademicGraphEngine,
    *,
    query: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return wiki-backed citations for a student policy question."""
    if not engine._built:
        engine.build_graph()

    hits = engine.search_wiki(query, limit=limit)
    citations: list[dict[str, Any]] = []
    for hit in hits:
        slug = str(hit.get("slug") or "")
        page = engine.wiki_pages.get(slug)
        if not page:
            continue
        title = str(hit.get("title_he") or hit.get("title") or slug)
        body = str(page.get("content") or "")
        citations.append(
            {
                "slug": slug,
                "title": title,
                "excerpt": _excerpt(body),
                "reference": f"wiki:{slug}",
            }
        )
    return citations


def build_policy_answer(
    engine: AcademicGraphEngine,
    *,
    question: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Build a grounded policy answer from wiki regulations search."""
    citations = search_regulation_citations(engine, query=question)
    if not citations:
        return (
            "I could not find matching regulation pages in the academic wiki for this question. "
            "Try rephrasing with specific terms (e.g. retake, appeal, student rights).",
            [],
        )

    answer_parts = [
        "Based on the institutional regulations corpus, these wiki sources are most relevant:"
    ]
    for index, citation in enumerate(citations, start=1):
        answer_parts.append(
            f"{index}. {citation['title']} ({citation['slug']}): {citation['excerpt']}"
        )

    answer_parts.append(
        "This is advisory information from the regulations knowledge base — "
        "confirm final decisions with the relevant academic office."
    )
    return "\n\n".join(answer_parts), citations
