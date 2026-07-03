"""Metadata filter behavior for DDS semantic course discovery."""

from __future__ import annotations

from app.retrieval.metadata_filter import filter_wiki_chunks
from app.retrieval.obsidian_wiki_indexer import WikiChunk


def _chunk(source_file: str, *, track: str | None = None) -> WikiChunk:
    return WikiChunk(
        source_file=source_file,
        page_title="Test",
        section_title="Section",
        heading_path=("Test", "Section"),
        content="content",
        track=track,
    )


def test_dds_track_slug_includes_faculty_course_pages():
    dds_course = _chunk("courses/009-dds/00940219-software-engineering.md")
    track_page = _chunk(
        "entities/tracks/track-data-information-engineering.md",
        track="track-data-information-engineering",
    )
    other_course = _chunk("courses/003-mechanical/00360049-nonlinear-vibrations.md")
    log_page = _chunk("log.md")

    filtered = filter_wiki_chunks(
        [dds_course, track_page, other_course, log_page],
        track_slug="track-data-information-engineering",
        catalog_year=2025,
    )

    assert dds_course in filtered
    assert track_page in filtered
    assert other_course not in filtered
    assert log_page not in filtered


def test_semantic_must_retrieve_pattern_matches_dds_course_source_id():
    source_id = "wiki:course:00940219"
    pattern = "wiki:course:009"
    assert pattern in source_id
