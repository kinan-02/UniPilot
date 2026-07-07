"""Condense retrieved wiki snippets for advanced explanation blocks."""

from __future__ import annotations

from app.agent.schemas import WikiContextSnippet


def build_wiki_explanation_context(
    snippets: list[WikiContextSnippet],
    *,
    max_sections: int = 4,
    max_chars_per_section: int = 600,
) -> str:
    if not snippets:
        return ""

    lines: list[str] = []
    for snippet in snippets[:max_sections]:
        title = snippet.page_title or snippet.source_file or "Catalog"
        section = snippet.section_title or title
        content = (snippet.content or "").strip()
        if len(content) > max_chars_per_section:
            content = content[: max_chars_per_section - 3].rstrip() + "..."
        if not content:
            continue
        lines.append(f"[{title} › {section}]\n{content}")

    return "\n\n".join(lines)
