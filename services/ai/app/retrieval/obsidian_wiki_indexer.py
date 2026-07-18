"""Chunk Obsidian wiki markdown by section headings (spec §15.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
COURSE_NUMBER_PATTERN = re.compile(r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def canonical_course_number(raw: str | None) -> str | None:
    """Normalize Technion course numbers to 8-digit 0-prefixed strings.

    Standalone copy of `app.planning.prerequisite_resolver.canonical_course_number`
    -- pure, zero-dependency logic, inlined here rather than pulling in the
    planning package as a dependency.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits or len(digits) < 6 or len(digits) > 9:
        return None
    padded = digits.zfill(8)[-8:]
    if not re.fullmatch(r"0\d{7}", padded):
        return None
    return padded


@dataclass(frozen=True)
class WikiChunk:
    source_file: str
    page_title: str
    section_title: str
    heading_path: tuple[str, ...]
    content: str
    catalog_year: str | None = None
    faculty: str | None = None
    degree_program: str | None = None
    track: str | None = None
    course_numbers_mentioned: tuple[str, ...] = ()
    primary_course_number: str | None = None
    language: str = "he"

    def to_snippet_dict(self, *, score: float | None = None) -> dict[str, Any]:
        return {
            "sourceType": "catalog_wiki",
            "sourceFile": self.source_file,
            "pageTitle": self.page_title,
            "sectionTitle": self.section_title,
            "headingPath": list(self.heading_path),
            "catalogYear": self.catalog_year,
            "faculty": self.faculty,
            "degreeProgram": self.degree_program,
            "track": self.track,
            "courseNumbersMentioned": list(self.course_numbers_mentioned),
            "language": self.language,
            "content": self.content,
            "score": score,
        }


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")
    return frontmatter, text[match.end() :]


def _extract_course_numbers(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    numbers: list[str] = []
    for match in COURSE_NUMBER_PATTERN.finditer(text):
        number = canonical_course_number(match.group(1))
        if number and number not in seen:
            seen.add(number)
            numbers.append(number)
    return tuple(numbers)


def _merge_course_numbers(*parts: str | tuple[str, ...] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, tuple):
            candidates = part
        else:
            candidates = _extract_course_numbers(part)
        for number in candidates:
            if number not in seen:
                seen.add(number)
                merged.append(number)
    return tuple(merged)


def _page_course_numbers(*, relative_path: str, frontmatter: dict[str, str], page_title: str) -> tuple[str, ...]:
    candidates: list[str] = []
    course_code = canonical_course_number(str(frontmatter.get("course_code") or ""))
    if course_code:
        candidates.append(course_code)
    stem = Path(relative_path).stem
    for segment in (stem, page_title, relative_path):
        candidates.extend(_extract_course_numbers(segment))
    return _merge_course_numbers(*candidates)


def _normalized_heading(value: str) -> str:
    return re.sub(r"\W+", " ", value or "").strip().lower()


def _build_heading_path(
    *,
    page_title: str,
    ancestors: list[str],
    section_title: str,
) -> tuple[str, ...]:
    """`(page, ...enclosing sections, section)` with near-duplicates removed.

    Most pages open with an H1 restating their own title, and that H1 is
    itself a section that ends up on the ancestor stack. Left alone, every
    heading beneath it carried the page name twice -- which then gets fed
    verbatim into `embedding_text`, so the repetition would dilute the
    embedding rather than add context.
    """
    page_key = _normalized_heading(page_title)
    path: list[str] = [page_title]
    seen = {page_key}
    for title in ancestors:
        key = _normalized_heading(title)
        if not key or key in seen:
            continue
        # The restatement is usually a prefix extension rather than an exact
        # match -- page "Academic Calendar 2025/2026" opening with
        # "# Academic Calendar 2025/2026 — Technion". Applied to ancestors
        # only; a chunk's own section title is never dropped this way.
        if page_key and (key.startswith(page_key) or page_key.startswith(key)):
            continue
        seen.add(key)
        path.append(title)
    section_key = _normalized_heading(section_title)
    if section_key and section_key not in seen:
        path.append(section_title)
    elif len(path) == 1:
        path.append(section_title)
    return tuple(path)


def chunk_wiki_page(*, relative_path: str, text: str) -> list[WikiChunk]:
    frontmatter, body = _parse_frontmatter(text)
    page_title = frontmatter.get("title") or frontmatter.get("title_he") or Path(relative_path).stem
    catalog_year = frontmatter.get("catalog_year") or frontmatter.get("catalogYear")
    faculty = frontmatter.get("faculty")
    degree_program = frontmatter.get("degree_program") or frontmatter.get("degreeProgram")
    track = frontmatter.get("track") or frontmatter.get("track_slug")
    page_numbers = _page_course_numbers(
        relative_path=relative_path,
        frontmatter=frontmatter,
        page_title=page_title,
    )
    primary_course_number = page_numbers[0] if page_numbers else None

    matches = list(HEADING_PATTERN.finditer(body))
    if not matches:
        content = body.strip()
        if not content:
            return []
        return [
            WikiChunk(
                source_file=relative_path,
                page_title=page_title,
                section_title=page_title,
                heading_path=(page_title,),
                content=content[:4000],
                catalog_year=catalog_year,
                faculty=faculty,
                degree_program=degree_program,
                track=track,
                primary_course_number=primary_course_number,
                course_numbers_mentioned=_merge_course_numbers(
                    page_numbers,
                    _extract_course_numbers(content),
                    _extract_course_numbers(page_title),
                ),
            )
        ]

    chunks: list[WikiChunk] = []
    # Tracks the enclosing headings by depth so a nested section keeps its
    # parents. `heading_path` was hardcoded to (page, section), so a
    # `### Notes` under `## Fall Semester` was indexed as if top-level --
    # 1,184 headings in this corpus (9.2%) sit at depth >= 3. It also feeds
    # `embedding_text`, so the vector lost that context too, not just the
    # metadata.
    heading_stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        depth = len(match.group(1))
        section_title = match.group(2).strip()
        content = body[start:end].strip()

        while heading_stack and heading_stack[-1][0] >= depth:
            heading_stack.pop()
        heading_path = _build_heading_path(
            page_title=page_title,
            ancestors=[title for _, title in heading_stack],
            section_title=section_title,
        )
        heading_stack.append((depth, section_title))

        # A short section is dropped only when it carries no retrievable
        # signal at all. This used to key off `page_numbers`, so an identical
        # 30-character section survived on a course-numbered page and
        # vanished on any other -- a whole-page property deciding the fate of
        # one section.
        if len(content) < 40 and not page_numbers and not _extract_course_numbers(content):
            continue
        chunks.append(
            WikiChunk(
                source_file=relative_path,
                page_title=page_title,
                section_title=section_title,
                heading_path=heading_path,
                content=content[:4000],
                catalog_year=catalog_year,
                faculty=faculty,
                degree_program=degree_program,
                track=track,
                primary_course_number=primary_course_number,
                course_numbers_mentioned=_merge_course_numbers(
                    page_numbers,
                    _extract_course_numbers(content),
                    _extract_course_numbers(section_title),
                ),
            )
        )
    return chunks


@lru_cache(maxsize=1)
def load_wiki_chunks(wiki_root: str) -> tuple[WikiChunk, ...]:
    root = Path(wiki_root)
    if not root.is_dir():
        return tuple()

    chunks: list[WikiChunk] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = str(path.relative_to(root))
        chunks.extend(chunk_wiki_page(relative_path=relative, text=text))
    return tuple(chunks)


def reset_wiki_index_cache() -> None:
    load_wiki_chunks.cache_clear()
