"""Metadata filters for wiki chunk retrieval (spec §15.2)."""

from __future__ import annotations

from typing import Any

from app.retrieval.obsidian_wiki_indexer import WikiChunk

_DDS_TRACK_SLUGS = frozenset(
    {
        "track-data-information-engineering",
        "track-industrial-engineering-management",
        "track-information-systems-engineering",
    }
)
_DDS_COURSE_PATH = "courses/009-dds/"


def _track_matches_chunk(chunk: WikiChunk, track_slug: str) -> bool:
    slug = track_slug.strip().lower()
    if not slug:
        return True
    normalized_path = chunk.source_file.replace("\\", "/").lower()
    if slug in _DDS_TRACK_SLUGS and _DDS_COURSE_PATH in normalized_path:
        return True
    return bool(
        (chunk.track and slug in chunk.track.lower())
        or slug in normalized_path
        or slug in chunk.page_title.lower()
    )


def filter_wiki_chunks(
    chunks: list[WikiChunk],
    *,
    track_slug: str | None = None,
    catalog_year: str | int | None = None,
    degree_program: str | None = None,
    course_number: str | None = None,
) -> list[WikiChunk]:
    if not chunks:
        return []

    if course_number:
        number = course_number.strip()
        if number:
            course_matches = [
                chunk
                for chunk in chunks
                if number in chunk.course_numbers_mentioned
                or number in chunk.content
                or number in chunk.source_file
                or number in chunk.page_title
                or number in chunk.section_title
            ]
            if course_matches:
                return course_matches
            return []

    filtered = list(chunks)
    had_metadata_filter = False

    if track_slug:
        slug = track_slug.strip().lower()
        if slug:
            had_metadata_filter = True
        filtered = [chunk for chunk in filtered if _track_matches_chunk(chunk, slug)]

    if catalog_year is not None:
        year_text = str(catalog_year).strip()
        if year_text:
            had_metadata_filter = True
            filtered = [
                chunk
                for chunk in filtered
                if not chunk.catalog_year or year_text in str(chunk.catalog_year)
            ]

    if degree_program:
        program = degree_program.strip().lower()
        if program:
            had_metadata_filter = True
            filtered = [
                chunk
                for chunk in filtered
                if (chunk.degree_program and program in chunk.degree_program.lower())
                or program in chunk.page_title.lower()
            ]

    if not filtered and had_metadata_filter:
        return []

    return filtered if filtered else list(chunks)


def filters_from_user_context(
    user_context: dict[str, Any],
    entities: dict[str, Any],
) -> dict[str, Any]:
    profile = user_context.get("profile") or {}
    return {
        "track_slug": profile.get("track") or user_context.get("track_slug"),
        "catalog_year": profile.get("catalogYear") or user_context.get("catalog_year"),
        "degree_program": profile.get("degreeProgram"),
        "course_number": entities.get("courseNumber"),
    }
