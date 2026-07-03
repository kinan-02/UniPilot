"""Tests for course-number aware wiki indexing and metadata filtering."""

from __future__ import annotations

from app.retrieval.metadata_filter import filter_wiki_chunks
from app.retrieval.obsidian_wiki_indexer import WikiChunk, chunk_wiki_page, reset_wiki_index_cache


COURSE_PAGE = """---
title: "00906292 — Course 00906292 (מסחר אלגוריתמי בתדירות גבוהה)"
course_code: "00906292"
faculty: faculty-dds
---

# 00906292 — Course 00906292

**Hebrew name:** מסחר אלגוריתמי בתדירות גבוהה

## Description

_No description available in catalog source._
"""


def setup_function() -> None:
    reset_wiki_index_cache()


def test_chunk_wiki_page_includes_frontmatter_course_code():
    chunks = chunk_wiki_page(relative_path="courses/009-dds/00906292-course.md", text=COURSE_PAGE)
    assert chunks
    assert all("00906292" in chunk.course_numbers_mentioned for chunk in chunks)


def test_course_number_filter_ignores_track_mismatch():
    chunks = [
        WikiChunk(
            source_file="courses/009-dds/00906292-course.md",
            page_title="00906292 — Course 00906292",
            section_title="Description",
            heading_path=("00906292 — Course 00906292", "Description"),
            content="_No description available in catalog source._",
            track=None,
            course_numbers_mentioned=("00906292",),
        ),
        WikiChunk(
            source_file="tracks/track-data-information-engineering/overview.md",
            page_title="DDS track overview",
            section_title="Overview",
            heading_path=("DDS track overview", "Overview"),
            content="Track-data-information-engineering overview for DDS students.",
            track="track-data-information-engineering",
            course_numbers_mentioned=(),
        ),
    ]
    filtered = filter_wiki_chunks(
        chunks,
        track_slug="track-data-information-engineering",
        catalog_year=2025,
        degree_program="DDS",
        course_number="00906292",
    )
    assert len(filtered) == 1
    assert filtered[0].source_file.endswith("00906292-course.md")
