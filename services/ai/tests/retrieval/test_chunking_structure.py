"""Tests for heading hierarchy and section retention in the chunker."""

from __future__ import annotations

from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page

_NESTED = """---
title: Academic Calendar
---
# Academic Calendar — Technion
Intro text long enough to survive the short-section filter comfortably here.
## Undergraduate School
Body for the undergraduate school section, long enough to be indexed fine.
### Winter Semester
Winter semester dates and details, long enough to be indexed without issue.
### Spring Semester
Spring semester dates and details, long enough to be indexed without issue.
## Graduate School
Graduate body text that is also long enough to survive the length filter.
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
