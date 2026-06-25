"""Build course title lookups from the catalog wiki vault."""

from __future__ import annotations

import re
from typing import Any

from app.utils.course_numbers import (
    normalize_course_number,
    resolve_course_number_token,
    strip_wikilinks_for_inline_scan,
)
from app.vault.loader import WikiPage
from app.vault.markdown_tables import parse_markdown_tables

INLINE_TITLE_PATTERN = re.compile(
    r"(?<!\d)(0\d{6,8}|\d{7,8})\s*[\(\[]\s*([^\)\]]+?)\s*[\)\]]",
)


def _column_index(headers: list[str], *candidates: str) -> int | None:
    lowered = [header.lower() for header in headers]
    for candidate in candidates:
        for index, header in enumerate(lowered):
            if candidate.lower() in header:
                return index
    return None


def _titles_from_tables(text: str, index: dict[str, str]) -> None:
    for table in parse_markdown_tables(text):
        code_idx = _column_index(table.headers, "code", "קוד")
        if code_idx is None:
            continue
        name_idx = _column_index(table.headers, "name", "שם")
        if name_idx is None:
            continue
        for row in table.rows:
            if code_idx >= len(row) or name_idx >= len(row):
                continue
            number = resolve_course_number_token(row[code_idx].strip())
            name = row[name_idx].strip()
            if number and name and not name.startswith("**"):
                index.setdefault(number, name)


def _titles_from_inline(text: str, index: dict[str, str]) -> None:
    for match in INLINE_TITLE_PATTERN.finditer(text):
        number = normalize_course_number(match.group(1))
        title = match.group(2).strip()
        if number and title:
            index.setdefault(number, title)


def build_wiki_title_index(pages: dict[str, WikiPage]) -> dict[str, str]:
    """Resolve titles from course pages, wiki tables, and inline annotations."""
    index: dict[str, str] = {}

    for page in pages.values():
        if page.page_type == "course":
            raw_code = page.frontmatter.get("course_code")
            if raw_code:
                number = normalize_course_number(str(raw_code))
                if number:
                    title = page.title_he or page.title
                    if title:
                        index.setdefault(number, str(title))

        for body in (page.english_body, page.body):
            _titles_from_tables(body, index)
            _titles_from_inline(strip_wikilinks_for_inline_scan(body), index)

    return index


def enrich_titles_from_index(
    document: dict[str, Any],
    title_index: dict[str, str],
    *,
    source_label: str,
) -> int:
    filled = 0
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                if ref.get("titleHint"):
                    continue
                number = ref.get("courseNumber")
                if not number:
                    continue
                title = title_index.get(number)
                if not title:
                    continue
                ref["titleHint"] = title
                evidence = list(ref.get("sourceEvidence") or [])
                evidence.append(f"titleHint:{source_label}:{number}")
                ref["sourceEvidence"] = evidence
                ref["confidence"] = "medium"
                filled += 1
    return filled


def align_credits_with_semester_json(
    document: dict[str, Any],
    course_index: dict[str, Any],
) -> int:
    """Prefer semester JSON credits when a course appears in offerings staging."""
    aligned = 0
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber")
                if not number:
                    continue
                record = course_index.get(number)
                if record is None or record.credits is None:
                    continue
                hint = ref.get("creditsHint")
                json_credits = float(record.credits)
                if hint is not None and abs(float(hint) - json_credits) > 0.25:
                    notes = list(ref.get("notes") or [])
                    notes.append(
                        f"Wiki/catalog creditsHint {hint} aligned to semester JSON {json_credits}.",
                    )
                    ref["notes"] = notes
                if hint != json_credits:
                    ref["creditsHint"] = json_credits
                    aligned += 1
    return aligned
