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
    from app.planning.prerequisite_resolver import canonical_course_number

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
    from app.planning.prerequisite_resolver import canonical_course_number

    candidates: list[str] = []
    course_code = canonical_course_number(str(frontmatter.get("course_code") or ""))
    if course_code:
        candidates.append(course_code)
    stem = Path(relative_path).stem
    for segment in (stem, page_title, relative_path):
        candidates.extend(_extract_course_numbers(segment))
    return _merge_course_numbers(*candidates)


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
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section_title = match.group(2).strip()
        content = body[start:end].strip()
        if len(content) < 40 and not page_numbers:
            continue
        heading_path = (page_title, section_title)
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
