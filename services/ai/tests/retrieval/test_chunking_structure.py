"""Tests for heading hierarchy and section retention in the chunker."""

from __future__ import annotations

from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page

_NESTED = """---
title: Academic Calendar
---
# Academic Calendar — Technion
Intro text long enough to survive the short-section filter comfortably here. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
## Undergraduate School
Body for the undergraduate school section, long enough to be indexed fine. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
### Winter Semester
Winter semester dates and details, long enough to be indexed without issue. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
### Spring Semester
Spring semester dates and details, long enough to be indexed without issue. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
## Graduate School
Graduate body text that is also long enough to survive the length filter. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
"""


def _by_title(text: str, path: str = "calendar.md"):
    return {c.section_title: c for c in chunk_wiki_page(relative_path=path, text=text)}


def test_nested_section_keeps_its_parent_section():
    """`heading_path` was hardcoded to (page, section), so a `### Winter
    Semester` under `## Undergraduate School` was indexed as if top-level --
    and since `embedding_text` embeds the path, the vector lost it too."""
    winter = _by_title(_NESTED)["Winter Semester"]
    assert "Undergraduate School" in winter.heading_path
    assert winter.heading_path[-1] == "Winter Semester"


def test_sibling_subsections_get_different_parents():
    chunks = _by_title(_NESTED)
    assert "Undergraduate School" in chunks["Winter Semester"].heading_path
    assert "Graduate School" not in chunks["Winter Semester"].heading_path


def test_heading_stack_pops_when_depth_decreases():
    """`## Graduate School` follows a `###`, so the deeper heading must not
    linger on the stack as its parent."""
    graduate = _by_title(_NESTED)["Graduate School"]
    assert "Winter Semester" not in graduate.heading_path
    assert graduate.heading_path == ("Academic Calendar", "Graduate School")


def test_h1_restating_the_page_title_is_not_duplicated():
    """Most pages open with an H1 restating their title, and it lands on the
    ancestor stack. Left alone every nested path carried the page name twice,
    diluting `embedding_text`."""
    winter = _by_title(_NESTED)["Winter Semester"]
    assert winter.heading_path == (
        "Academic Calendar",
        "Undergraduate School",
        "Winter Semester",
    )


def test_page_title_always_leads_the_path():
    for chunk in chunk_wiki_page(relative_path="calendar.md", text=_NESTED):
        assert chunk.heading_path[0] == "Academic Calendar"


def test_short_section_is_kept_when_it_carries_a_course_number():
    """Retention keyed off a whole-page property, so an identical short
    section survived on a course-numbered page and vanished on any other."""
    text = """---
title: Track Overview
---
## Required
00440105
## Empty Notes
n/a
"""
    titles = {c.section_title for c in chunk_wiki_page(relative_path="entities/tracks/t.md", text=text)}
    assert "Required" in titles
    assert "Empty Notes" not in titles


# -- content quality filtering -------------------------------------------

_BOILERPLATE = """---
title: Some Course
aliases: [discrete math, מתמטיקה בדידה]
tags: [required-dne, mathematics]
credits: 3.5
level: undergraduate
faculty: faculty-dds
---
## Description
_No description available in catalog source._
## Sources
- [[technion-full-catalog-2025-2026]]
## Real Section
Actual substantive prose about the course that carries retrievable meaning.
"""


def test_placeholder_and_link_only_sections_are_not_indexed():
    """2,086 chunks were the identical 'no description' placeholder and 2,672
    were bare link lists -- together 38.5% of the corpus, consuming up to 38%
    of the keyword candidate budget."""
    titles = {c.section_title for c in chunk_wiki_page(relative_path="courses/x.md", text=_BOILERPLATE)}
    assert "Description" not in titles
    assert "Sources" not in titles


def test_frontmatter_that_exists_is_actually_read():
    chunk = chunk_wiki_page(relative_path="courses/x.md", text=_BOILERPLATE)[0]
    assert chunk.aliases == ("discrete math", "מתמטיקה בדידה")
    assert chunk.tags == ("required-dne", "mathematics")
    assert chunk.credits == "3.5"
    assert chunk.level == "undergraduate"
    assert chunk.faculty == "faculty-dds"


def test_track_is_derived_from_the_path_for_track_pages():
    """The `track` frontmatter key is present in zero files; for track pages
    the slug is in the path."""
    text = "---\ntitle: T\n---\n## Body\n" + "Long enough body text to be indexed on its own. " * 20
    chunk = chunk_wiki_page(relative_path="entities/tracks/track-aerospace.md", text=text)[0]
    assert chunk.track == "aerospace"
    assert chunk_wiki_page(relative_path="courses/x.md", text=text)[0].track is None


def test_language_is_detected_rather_than_hardcoded():
    """Every one of the 12,586 chunks previously claimed Hebrew."""
    from app.retrieval.obsidian_wiki_indexer import detect_language

    assert detect_language("Introduction to computer science") == "en"
    assert detect_language("מבוא למדעי המחשב ותכנות") == "he"
    assert detect_language("Discrete Mathematics מתמטיקה בדידה") == "mixed"


# -- page merging ---------------------------------------------------------


def test_small_page_is_indexed_as_one_chunk():
    """The median page held ~414 chars split into ~4.6 fragments of ~90 --
    too little text per fragment to embed meaningfully."""
    text = """---
title: Tiny Course
---
## Description
Short description of the course.
## Notes
A brief note about scheduling.
"""
    chunks = chunk_wiki_page(relative_path="courses/tiny.md", text=text)
    assert len(chunks) == 1
    assert "Description" in chunks[0].content
    assert "Notes" in chunks[0].content


def test_large_page_keeps_its_section_structure():
    assert len(chunk_wiki_page(relative_path="calendar.md", text=_NESTED)) > 1
