"""Resolve Technion program codes from faculty wiki tables and curated overrides."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.paths import catalog_vault_root, service_root
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root

PROGRAM_CODE_PATTERN = re.compile(r"(0\d{5}-\d-\d{3})")
SHORT_PROGRAM_CODE_PATTERN = re.compile(r"\b(0\d{5})\b")
TRACK_LINK_PATTERN = re.compile(r"\[\[(track-[^\]|#]+)(?:\|[^\]]+)?\]\]")
TRACK_PAGES_SECTION = re.compile(r"^#{2,3}\s+.*(Track Pages|רשימת מסלולים)", re.IGNORECASE)


def normalize_program_code(raw: str) -> str:
    full_match = PROGRAM_CODE_PATTERN.search(raw)
    if full_match:
        return full_match.group(1)
    short_match = SHORT_PROGRAM_CODE_PATTERN.search(raw)
    if short_match:
        return f"{short_match.group(1)}-1-000"
    return raw


def overrides_path() -> Path:
    return service_root() / "data" / "contracts" / "track_program_code_overrides.json"


@lru_cache(maxsize=1)
def load_track_program_code_overrides() -> dict[str, str]:
    path = overrides_path()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    overrides = payload.get("overrides") or {}
    return {str(slug): str(code) for slug, code in overrides.items()}


def _codes_on_line(line: str) -> list[str]:
    codes = PROGRAM_CODE_PATTERN.findall(line)
    if codes:
        return codes
    return [normalize_program_code(match) for match in SHORT_PROGRAM_CODE_PATTERN.findall(line)]


def _track_slugs_on_line(line: str) -> list[str]:
    return TRACK_LINK_PATTERN.findall(line)


def _track_slugs_from_track_pages_section(text: str) -> list[str]:
    slugs: list[str] = []
    in_section = False
    for line in text.splitlines():
        if TRACK_PAGES_SECTION.match(line.strip()):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                break
            if stripped.startswith("### ") and not TRACK_PAGES_SECTION.match(stripped):
                break
            if stripped.startswith("- "):
                slugs.extend(_track_slugs_on_line(line))
    return slugs


BSC_TRACKS_SECTION = re.compile(
    r"^#{2,3}\s+.*(BSc Tracks|מסלולי לימוד לתואר ראשון|מסלולי לימוד)",
    re.IGNORECASE,
)


def _codes_from_bsc_table(text: str) -> list[str]:
    codes: list[str] = []
    in_section = False
    for line in text.splitlines():
        if BSC_TRACKS_SECTION.match(line.strip()):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                break
            if "|" not in line or _track_slugs_on_line(line):
                continue
            line_codes = _codes_on_line(line)
            if line_codes:
                codes.append(line_codes[-1])
    return codes


def _ordered_bsc_table_mappings(text: str) -> dict[str, str]:
    """Zip Track Pages slugs with BSc table codes when faculty pages list them separately."""
    track_slugs = _track_slugs_from_track_pages_section(text)
    if not track_slugs:
        return {}

    table_codes = _codes_from_bsc_table(text)
    if len(track_slugs) != len(table_codes):
        return {}
    return dict(zip(track_slugs, table_codes, strict=True))


def parse_faculty_track_codes(page: WikiPage) -> dict[str, str]:
    """Extract track-slug → program-code mappings from a faculty entity page."""
    text = page.english_body + "\n" + page.body
    mapping: dict[str, str] = {}
    mapping.update(_ordered_bsc_table_mappings(text))
    for line in text.splitlines():
        slugs = _track_slugs_on_line(line)
        if not slugs:
            continue
        codes = _codes_on_line(line)
        if not codes:
            continue
        code = codes[-1]
        for slug in slugs:
            mapping[slug] = code
    return mapping


@lru_cache(maxsize=1)
def build_faculty_track_program_index() -> dict[str, str]:
    root = wiki_root(catalog_vault_root())
    pages = load_pages_by_slug(root)
    index: dict[str, str] = {}
    for slug, page in pages.items():
        if not slug.startswith("faculty-"):
            continue
        index.update(parse_faculty_track_codes(page))
    index.update(load_track_program_code_overrides())
    return index


def resolve_program_code(page: WikiPage, extracted: str | None) -> str | None:
    """Return wiki-extracted code, faculty-table code, or a curated slug override."""
    if extracted:
        return extracted
    index = build_faculty_track_program_index()
    return index.get(page.slug)


def clear_faculty_track_program_index_cache() -> None:
    build_faculty_track_program_index.cache_clear()
    load_track_program_code_overrides.cache_clear()
