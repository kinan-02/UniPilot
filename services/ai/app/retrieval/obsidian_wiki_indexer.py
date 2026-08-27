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


_HEBREW_CHAR = re.compile(r"[֐-׿]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")

# A section carrying no retrievable information. The catalog ingest emits a
# fixed placeholder wherever a course has no description (2,086 chunks, all
# byte-identical), and "Sources" sections are frequently a single wiki link
# repeated across thousands of pages (the top one appears 1,875 times).
# Indexed, they consumed up to 38% of the keyword candidate budget for
# queries containing ordinary words like "description" or "catalog", and
# 2,032 of them shared one embedding.
_PLACEHOLDER_CONTENT = re.compile(r"^_no description available", re.IGNORECASE)
_LINK_ONLY_CONTENT = re.compile(r"^(?:[-*]\s*\[\[[^\]]+\]\]\s*)+$")
_MIN_SUBSTANTIVE_CHARS = 20

# Pages whose entire body fits comfortably in one chunk are indexed whole.
# The median page holds just 414 characters of text yet was split into ~4.6
# fragments averaging ~90 characters -- too little text to embed meaningfully.
_PAGE_MERGE_MAX_CHARS = 600


def detect_language(text: str) -> str:
    """`he` / `en` / `mixed` by script, replacing a hardcoded default.

    `language` was never assigned -- every one of the 12,586 chunks claimed
    Hebrew, including the wholly-English ones, and that value rode along into
    the vector store's metadata.
    """
    hebrew = len(_HEBREW_CHAR.findall(text or ""))
    latin = len(_LATIN_CHAR.findall(text or ""))
    if not hebrew and not latin:
        return "und"
    if not hebrew:
        return "en"
    if not latin:
        return "he"
    ratio = hebrew / (hebrew + latin)
    if ratio > 0.7:
        return "he"
    if ratio < 0.3:
        return "en"
    return "mixed"


def is_substantive(content: str) -> bool:
    """False for placeholder text, bare link lists, and near-empty sections."""
    body = (content or "").strip()
    if len(body) < _MIN_SUBSTANTIVE_CHARS:
        return False
    if _PLACEHOLDER_CONTENT.match(body):
        return False
    return not _LINK_ONLY_CONTENT.match(body)


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
    # Frontmatter that exists on ~2,750 pages and was previously read by
    # nobody. `aliases` matters most: they are the Hebrew/English name
    # variants students actually type ("discrete math", "מתמטיקה דיסקרטית"),
    # and only the slug registry ever saw them, so neither BM25 nor the
    # embeddings could match on them.
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    credits: str | None = None
    level: str | None = None

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


def _track_from_path(relative_path: str) -> str | None:
    """Track slug for `entities/tracks/track-*.md`, else None.

    The `track` frontmatter key the old reader looked for is present in zero
    files; for track pages themselves the slug is right there in the path.
    """
    normalized = relative_path.replace("\\", "/")
    if not normalized.startswith("entities/tracks/"):
        return None
    stem = Path(normalized).stem
    return stem[len("track-") :] if stem.startswith("track-") else stem


def _parse_frontmatter_list(raw: str | None) -> tuple[str, ...]:
    """Parse `key: [a, b, c]` values.

    `_parse_frontmatter` keeps whole values as strings, so list-valued keys
    arrived as the literal text "[a, b, c]".
    """
    value = (raw or "").strip()
    if not value:
        return ()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    items = [item.strip().strip("\"'") for item in value.split(",")]
    return tuple(item for item in items if item)


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
    faculty = frontmatter.get("faculty")
    aliases = _parse_frontmatter_list(frontmatter.get("aliases"))
    tags = _parse_frontmatter_list(frontmatter.get("tags"))
    credits = frontmatter.get("credits")
    level = frontmatter.get("level")
    # `catalog_year`, `degree_program` and `track` appear in ZERO files under
    # any spelling the old reader tried, so those fields stayed permanently
    # None and the five rerank boosts keyed on them could never fire. Track
    # membership really lives in `tags` (e.g. "required-dne"); faculty and
    # track slugs are otherwise recoverable from the path.
    track = _track_from_path(relative_path)
    page_numbers = _page_course_numbers(
        relative_path=relative_path,
        frontmatter=frontmatter,
        page_title=page_title,
    )
    primary_course_number = page_numbers[0] if page_numbers else None

    def _make(
        *,
        section_title: str,
        heading_path: tuple[str, ...],
        content: str,
    ) -> WikiChunk:
        return WikiChunk(
            source_file=relative_path,
            page_title=page_title,
            section_title=section_title,
            heading_path=heading_path,
            content=content[:4000],
            faculty=faculty,
            track=track,
            primary_course_number=primary_course_number,
            course_numbers_mentioned=_merge_course_numbers(
                page_numbers,
                _extract_course_numbers(content),
                _extract_course_numbers(section_title),
            ),
            language=detect_language(f"{section_title} {content}"),
            aliases=aliases,
            tags=tags,
            credits=credits,
            level=level,
        )

    matches = list(HEADING_PATTERN.finditer(body))
    if not matches:
        content = body.strip()
        if not content:
            return []
        return [
            _make(
                section_title=page_title,
                heading_path=(page_title,),
                content=content,
            )
        ]

    sections: list[tuple[str, tuple[str, ...], str]] = []
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

        # Placeholder text, bare link lists and near-empty sections carry
        # nothing retrievable. A section that is merely SHORT is kept when it
        # names a course number, which is exactly the case the old
        # whole-page-property check got wrong.
        if not is_substantive(content) and not _extract_course_numbers(content):
            continue
        sections.append((section_title, heading_path, content))

    if not sections:
        return []

    # Small pages are indexed whole. The median page holds ~414 characters
    # split across ~4.6 sections of ~90 characters each -- too little text
    # per fragment to embed meaningfully, and it forces a reader that wants
    # one course to reassemble it from pieces. Longer pages keep their
    # section structure, where splitting genuinely aids precision.
    total_chars = sum(len(content) for _, _, content in sections)
    if total_chars <= _PAGE_MERGE_MAX_CHARS and len(sections) > 1:
        merged = "\n\n".join(
            f"## {section_title}\n{content}" for section_title, _, content in sections
        )
        return [
            _make(
                section_title=page_title,
                heading_path=(page_title,),
                content=merged,
            )
        ]

    return [
        _make(section_title=section_title, heading_path=heading_path, content=content)
        for section_title, heading_path, content in sections
    ]


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
