"""Wiki entity alias → slug resolution (Layer 1 graph index).

Alias phrases are ingested from wiki YAML frontmatter (title, title_he, aliases)
when the academic graph engine loads. Static fallbacks cover high-frequency
abbreviations used in eval and live queries.
"""

from __future__ import annotations

import re
from typing import Any

# High-frequency aliases not always present in frontmatter aliases arrays.
STATIC_ENTITY_ALIASES: dict[str, str] = {
    "robotics minor": "minor-robotics",
    "inter-faculty robotics minor": "minor-robotics",
    "minor in robotics": "minor-robotics",
    "מינור רובוטיקה": "minor-robotics",
    "התמחות משנה ברובוטיקה": "minor-robotics",
    "bme": "track-biomedical-engineering",
    "biomedical engineering": "track-biomedical-engineering",
    "biomedical engineering bsc": "track-biomedical-engineering",
    "biomedical engineering bsc track": "track-biomedical-engineering",
    "הנדסה ביו-רפואית": "track-biomedical-engineering",
    "מסלול הנדסה ביו-רפואית": "track-biomedical-engineering",
    "iem": "track-industrial-engineering-management",
    "industrial engineering & management": "track-industrial-engineering-management",
    "industrial engineering and management": "track-industrial-engineering-management",
    "הנדסת תעשייה וניהול": "track-industrial-engineering-management",
    "dne": "track-data-information-engineering",
    "data information engineering": "track-data-information-engineering",
    "הנדסת נתונים ומידע": "track-data-information-engineering",
    "4-year general computer science": "track-computer-science-general-4year",
    "general computer science track": "track-computer-science-general-4year",
    "general cs track": "track-computer-science-general-4year",
    "cs 4-year": "track-computer-science-general-4year",
    "undergraduate regulations": "regulations-undergraduate",
    "regulations undergraduate": "regulations-undergraduate",
    "תקנות לימודי הסמכה": "regulations-undergraduate",
    "תקנון לימודי הסמכה": "regulations-undergraduate",
}

_ALIAS_NORMALIZE_RE = re.compile(r"[\s_\-]+")
_MIN_ALIAS_PHRASE_LEN = 3


def normalize_alias_phrase(phrase: str) -> str:
    cleaned = (phrase or "").strip().lower()
    if not cleaned:
        return ""
    return _ALIAS_NORMALIZE_RE.sub(" ", cleaned).strip()


def _phrase_matches_query(phrase: str, normalized_query: str) -> bool:
    """Match alias phrases without spurious substring hits (e.g. ``pl`` in *complete*)."""
    if not phrase or not normalized_query:
        return False
    if phrase not in normalized_query:
        return False
    if " " in phrase:
        return True
    if len(phrase) < _MIN_ALIAS_PHRASE_LEN:
        return False
    pattern = rf"(?:^|\s){re.escape(phrase)}(?:\s|$)"
    return bool(re.search(pattern, normalized_query))


def build_alias_index_from_catalog(wiki_catalog: list[dict[str, Any]]) -> dict[str, str]:
    """Build alias phrase → slug map from loaded wiki catalog metadata."""
    index: dict[str, str] = {}
    for alias, slug in STATIC_ENTITY_ALIASES.items():
        index[normalize_alias_phrase(alias)] = slug

    for entry in wiki_catalog:
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        phrases = [
            slug,
            slug.replace("-", " "),
            str(entry.get("title") or ""),
            str(entry.get("title_he") or ""),
            *[str(alias) for alias in (entry.get("aliases") or [])],
        ]
        for phrase in phrases:
            normalized = normalize_alias_phrase(phrase)
            if len(normalized) < _MIN_ALIAS_PHRASE_LEN and normalized not in {
                normalize_alias_phrase(alias) for alias in STATIC_ENTITY_ALIASES
            }:
                continue
            if len(normalized) < 2:
                continue
            existing = index.get(normalized)
            if existing and existing != slug:
                # Prefer track/program/minor slugs over generic wiki pages on collision.
                if _slug_priority(slug) >= _slug_priority(existing):
                    index[normalized] = slug
            else:
                index[normalized] = slug
    return index


def _slug_priority(slug: str) -> int:
    if slug.startswith("track-"):
        return 4
    if slug.startswith("minor-") or slug.startswith("program-"):
        return 4
    if slug.startswith("faculty-"):
        return 3
    if slug.startswith("regulations-"):
        return 3
    return 1


def resolve_entity_slugs(
    query: str,
    alias_index: dict[str, str],
    *,
    max_slugs: int = 4,
) -> list[str]:
    """Longest-match-first slug resolution from free text."""
    if not query or not alias_index:
        return []

    normalized_query = normalize_alias_phrase(query)
    if not normalized_query:
        return []

    candidates: list[tuple[int, str, str]] = []
    for phrase, slug in alias_index.items():
        if not phrase or not _phrase_matches_query(phrase, normalized_query):
            continue
        candidates.append((len(phrase), phrase, slug))

    candidates.sort(key=lambda item: (-item[0], item[2]))
    resolved: list[str] = []
    accepted_phrases: list[str] = []
    seen: set[str] = set()
    for _length, phrase, slug in candidates:
        if slug in seen:
            continue
        if " " not in phrase and any(
            re.search(rf"(?:^|\s){re.escape(phrase)}(?:\s|$)", longer)
            for longer in accepted_phrases
            if " " in longer
        ):
            continue
        seen.add(slug)
        accepted_phrases.append(phrase)
        resolved.append(slug)
        if len(resolved) >= max_slugs:
            break
    return resolved


def residual_search_query(query: str, resolved_slugs: list[str], alias_index: dict[str, str]) -> str:
    """Return query text with matched alias phrases stripped (for fallback wiki_search)."""
    text = normalize_alias_phrase(query)
    if not text:
        return ""

    phrases = [
        phrase
        for phrase, slug in alias_index.items()
        if slug in resolved_slugs and phrase and _phrase_matches_query(phrase, text)
    ]
    phrases.sort(key=len, reverse=True)
    for phrase in phrases:
        text = text.replace(phrase, " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugs_from_entities(entities: dict[str, Any]) -> list[str]:
    slugs: list[str] = []
    for key in ("wikiSlug", "trackSlug", "programSlug", "requirementSlug"):
        value = entities.get(key)
        if isinstance(value, str) and value.strip():
            slugs.append(value.strip())
    extra = entities.get("resolvedWikiSlugs")
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str) and item.strip() and item.strip() not in slugs:
                slugs.append(item.strip())
    return slugs
