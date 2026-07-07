"""Parse structured facts from Obsidian wiki markdown pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.planning.prerequisite_resolver import canonical_course_number, extract_course_numbers_from_text

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_FIELD_LINE_RE = re.compile(r"^\*\*(?P<label>[^*]+):\*\*\s*(?P<value>.+)$", re.MULTILINE)


@dataclass(frozen=True)
class WikiFrontmatter:
    raw: dict[str, str] = field(default_factory=dict)


def parse_frontmatter(text: str) -> WikiFrontmatter:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return WikiFrontmatter()
    raw: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        raw[key.strip()] = value.strip().strip('"')
    return WikiFrontmatter(raw=raw)


def extract_wiki_links(value: str) -> list[tuple[str, str | None]]:
    links: list[tuple[str, str | None]] = []
    for match in _WIKI_LINK_RE.finditer(value):
        slug = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else None
        links.append((slug, display))
    return links


def extract_field_value(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def slug_to_course_number(slug: str) -> str | None:
    prefix = slug.split("-", 1)[0]
    return canonical_course_number(prefix)


def slug_to_track_slug(slug: str) -> str | None:
    cleaned = slug.strip().lower()
    if cleaned.startswith("track-"):
        return cleaned
    return None


def wiki_page_path(wiki_root: Path, relative_path: str) -> Path:
    return wiki_root / relative_path.removeprefix("wiki/")


def relative_wiki_path(path: Path, wiki_root: Path) -> str:
    rel = path.relative_to(wiki_root).as_posix()
    return f"wiki/{rel}"


def read_wiki_page(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def find_course_wiki_page(wiki_root: Path, course_number: str) -> Path | None:
    normalized = canonical_course_number(course_number)
    if not normalized:
        return None
    courses_dir = wiki_root / "courses"
    if not courses_dir.is_dir():
        return None
    candidates = sorted(courses_dir.rglob(f"{normalized}*.md"))
    if candidates:
        return candidates[0]
    stripped = normalized.lstrip("0")
    if stripped != normalized:
        candidates = sorted(courses_dir.rglob(f"*{stripped}*.md"))
        if candidates:
            return candidates[0]
    return None


def find_track_wiki_page(wiki_root: Path, track_slug: str) -> Path | None:
    slug = track_slug.strip().lower()
    if not slug.startswith("track-"):
        slug = f"track-{slug}"
    path = wiki_root / "entities" / "tracks" / f"{slug}.md"
    return path if path.is_file() else None


def find_regulations_page(wiki_root: Path) -> Path | None:
    path = wiki_root / "concepts" / "regulations-undergraduate.md"
    return path if path.is_file() else None


def build_track_code_index(wiki_root: Path) -> dict[str, str]:
    """Map faculty track code prefix (e.g. 023023) to track slug."""
    index: dict[str, str] = {}
    tracks_dir = wiki_root / "entities" / "tracks"
    if not tracks_dir.is_dir():
        return index
    code_pattern = re.compile(r"\*\*Track code:\*\*\s*([\d]+)-", re.IGNORECASE)
    for path in tracks_dir.glob("track-*.md"):
        text = read_wiki_page(path)
        if not text:
            continue
        match = code_pattern.search(text)
        if not match:
            continue
        prefix = match.group(1)
        slug = path.stem
        index[prefix] = slug
        index[canonical_course_number(prefix) or prefix] = slug
    return index


def parse_course_page(text: str, *, source_path: str) -> dict[str, Any]:
    frontmatter = parse_frontmatter(text)
    fm = frontmatter.raw
    course_code = canonical_course_number(fm.get("course_code") or fm.get("course_code_full") or "") or ""
    title = fm.get("title") or ""
    title_he = fm.get("title_he") or ""
    credits = fm.get("credits") or extract_field_value(text, "Credits")
    level = fm.get("level") or ""

    prereq_value = extract_field_value(text, "Prerequisites") or ""
    required_value = extract_field_value(text, "Required in") or ""

    prerequisites: list[dict[str, str]] = []
    if prereq_value.lower() not in {"", "none", "אין"}:
        for slug, display in extract_wiki_links(prereq_value):
            code = slug_to_course_number(slug)
            if code:
                label = display or _humanize_slug(slug)
                prerequisites.append(
                    {
                        "courseNumber": code,
                        "label": label,
                    }
                )

    required_tracks: list[str] = []
    for slug, _display in extract_wiki_links(required_value):
        track = slug_to_track_slug(slug)
        if track:
            required_tracks.append(track)

    # Hebrew section fallback
    if not prerequisites:
        hebrew_prereq = extract_field_value(text, "קדם")
        if hebrew_prereq and hebrew_prereq.lower() not in {"אין", "none"}:
            for slug, display in extract_wiki_links(hebrew_prereq):
                code = slug_to_course_number(slug)
                if code:
                    prerequisites.append(
                        {
                            "courseNumber": code,
                            "label": display or slug,
                        }
                    )
    if not required_tracks:
        hebrew_required = extract_field_value(text, "נדרש ב")
        if hebrew_required:
            for slug, _display in extract_wiki_links(hebrew_required):
                track = slug_to_track_slug(slug)
                if track:
                    required_tracks.append(track)

    return {
        "courseNumber": course_code,
        "title": title,
        "titleHebrew": title_he,
        "credits": credits,
        "level": level,
        "prerequisites": prerequisites,
        "requiredTracks": sorted(set(required_tracks)),
        "sourceWikiPage": source_path,
    }


def _extract_total_credits(text: str) -> float | None:
    for label in (
        "Total credits required",
        "Total Credits Required",
        "Total Credits",
        "Total credits",
    ):
        parsed = _parse_float(extract_field_value(text, label))
        if parsed is not None:
            return parsed
    return None


def _extract_program_code(text: str) -> str | None:
    for label in ("Track code", "Program Code", "Program code"):
        value = extract_field_value(text, label)
        if value:
            return value.strip()
    return None


def _classify_credit_breakdown_row(label: str) -> str | None:
    lowered = label.lower()
    if any(token in lowered for token in ("mandatory", "required", "חובה")):
        return "required"
    if "faculty" in lowered and "technion" not in lowered:
        return "faculty"
    if "technion" in lowered and "of which" not in lowered:
        return "technion"
    if "enrichment" in lowered or "העשרה" in label:
        return "enrichment"
    if "physical education" in lowered or "חינוך גופני" in label:
        return "pe"
    return None


def parse_track_page(text: str, *, source_path: str) -> dict[str, Any]:
    frontmatter = parse_frontmatter(text)
    fm = frontmatter.raw
    track_slug = Path(source_path).stem if source_path else ""
    title = fm.get("title") or ""
    title_he = fm.get("title_he") or ""
    faculty = fm.get("faculty") or ""

    total_credits = _extract_total_credits(text)
    track_code = _extract_program_code(text)

    required_credits = faculty_electives = technion_electives = None
    duration = degree = None
    enrichment_min = pe_min = None

    table_match = re.search(
        r"\| Category \| Credits \|\n\|[-| ]+\n((?:\|[^\n]+\n)+)",
        text,
        re.IGNORECASE,
    )
    if table_match:
        for row in table_match.group(1).splitlines():
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            if len(cells) < 2:
                continue
            label, value = cells[0], _parse_float(cells[1])
            if value is None:
                continue
            row_kind = _classify_credit_breakdown_row(label)
            if row_kind == "required":
                required_credits = value
            elif row_kind == "faculty":
                faculty_electives = value
            elif row_kind == "technion":
                technion_electives = value
            elif row_kind == "enrichment":
                enrichment_min = value
            elif row_kind == "pe":
                pe_min = value

    duration_match = re.search(r"\*\*Duration:\*\*\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if duration_match:
        duration = duration_match.group(1).strip()
    degree_match = re.search(r"\*\*Degree:\*\*\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if degree_match:
        degree = degree_match.group(1).strip()

    note_match = re.search(
        r"Note:.*at least\s+(\d+)\s+credits enrichment.*at least\s+(\d+)\s+credits physical education",
        text,
        re.IGNORECASE,
    )
    if note_match:
        enrichment_min = float(note_match.group(1))
        pe_min = float(note_match.group(2))

    if total_credits is None and None not in (required_credits, faculty_electives, technion_electives):
        total_credits = round(required_credits + faculty_electives + technion_electives, 1)

    return {
        "trackSlug": track_slug,
        "title": title,
        "titleHebrew": title_he,
        "faculty": faculty,
        "trackCode": track_code,
        "totalCredits": total_credits,
        "requiredCourseCredits": required_credits,
        "facultyElectiveCredits": faculty_electives,
        "technionWideElectiveCredits": technion_electives,
        "enrichmentMinimumCredits": enrichment_min,
        "peMinimumCredits": pe_min,
        "duration": duration,
        "degree": degree,
        "sourceWikiPage": source_path,
    }


def _humanize_slug(slug: str) -> str:
    return slug.split("-", 1)[-1].replace("-", " ").strip()


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"([\d]+(?:\.\d+)?)", value.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def parse_non_regular_standing_section(text: str) -> list[dict[str, str]]:
    section_match = re.search(
        r"### 5\.6 Non-Regular Academic Standing.*?\n\n(.*?)(?=\n### |\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return []
    section = section_match.group(1)
    rows: list[dict[str, str]] = []
    for match in re.finditer(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|$", section, re.MULTILINE):
        rows.append({"number": match.group(1), "text": match.group(2).strip()})
    return rows
