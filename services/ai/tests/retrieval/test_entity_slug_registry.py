"""Tests for wiki entity alias → slug resolution."""

from __future__ import annotations

from app.retrieval.entity_slug_registry import (
    build_alias_index_from_catalog,
    normalize_alias_phrase,
    resolve_entity_slugs,
    residual_search_query,
)


def test_normalize_alias_phrase() -> None:
    assert normalize_alias_phrase("  Robotics   Minor ") == "robotics minor"


def test_resolve_robotics_minor_slug() -> None:
    index = build_alias_index_from_catalog([])
    slugs = resolve_entity_slugs(
        "I'm interested in the Inter-Faculty Robotics Minor admission requirements",
        index,
    )
    assert "minor-robotics" in slugs


def test_resolve_bme_track_slug() -> None:
    index = build_alias_index_from_catalog([])
    slugs = resolve_entity_slugs(
        "What is the total credit requirement for the Biomedical Engineering BSc track?",
        index,
    )
    assert "track-biomedical-engineering" in slugs


def test_residual_search_strips_matched_aliases() -> None:
    index = build_alias_index_from_catalog([])
    slugs = resolve_entity_slugs("Biomedical Engineering BSc track semester 1 courses", index)
    residual = residual_search_query(
        "Biomedical Engineering BSc track semester 1 courses",
        slugs,
        index,
    )
    assert "biomedical engineering" not in residual
    assert "semester 1" in residual or "courses" in residual


def test_short_alias_substrings_do_not_false_match() -> None:
    """``pl`` / ``ee`` inside *complete* / *need* must not resolve course slugs."""
    index = build_alias_index_from_catalog(
        [
            {
                "slug": "02360319-programming-languages",
                "title": "Programming Languages",
                "title_he": "שפות תכנות",
                "aliases": ["pl", "ee"],
            }
        ]
    )
    slugs = resolve_entity_slugs("how many credits do I need to complete it?", index)
    assert slugs == []


def test_generic_token_skipped_when_longer_track_phrase_matches() -> None:
    index = build_alias_index_from_catalog(
        [
            {
                "slug": "track-biomedical-engineering",
                "title": "Biomedical Engineering BSc Track",
                "aliases": ["biomedical engineering", "BME"],
            },
            {
                "slug": "00180501-sea-systems-engineering",
                "title": "Sea Systems Engineering",
                "aliases": ["engineering"],
            },
        ]
    )
    slugs = resolve_entity_slugs(
        "Biomedical Engineering BSc track credit breakdown",
        index,
    )
    assert slugs == ["track-biomedical-engineering"]
