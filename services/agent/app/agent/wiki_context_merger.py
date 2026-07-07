"""Merge and rank wiki snippets from multi-step retrieval."""

from __future__ import annotations

from app.agent.schemas import WikiContextSnippet


def _snippet_key(snippet: WikiContextSnippet) -> tuple[str, str]:
    return (
        str(snippet.source_file or ""),
        str(snippet.section_title or ""),
    )


def merge_wiki_snippets(
    existing: list[WikiContextSnippet],
    new_items: list[WikiContextSnippet],
    *,
    max_snippets: int,
) -> list[WikiContextSnippet]:
    if max_snippets <= 0:
        return []

    by_key: dict[tuple[str, str], WikiContextSnippet] = {}
    for snippet in [*existing, *new_items]:
        key = _snippet_key(snippet)
        current = by_key.get(key)
        if current is None:
            by_key[key] = snippet
            continue
        current_score = float(current.score or 0.0)
        new_score = float(snippet.score or 0.0)
        if new_score > current_score:
            by_key[key] = snippet

    merged = sorted(
        by_key.values(),
        key=lambda item: float(item.score or 0.0),
        reverse=True,
    )
    return merged[:max_snippets]
