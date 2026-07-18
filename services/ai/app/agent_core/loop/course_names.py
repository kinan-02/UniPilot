"""Course code -> human-readable name, for rendering answers a student can read.

The live evals shipped grounded, correct, near-unreadable answers: "The courses
on your record with a final grade above 90 are: 00940704, 00940219, 03240033."
Seven of ten answers in the 2026-07-18 run carried bare codes.

The name cannot come from the model. The grounding backstop checks NUMERALS
only (`answer_boundary._NUM`), so a course name typed into prose is never
validated -- and a plausible fabricated name attached to a real code is worse
than no name, because nothing about it invites doubt. So the name is read from
the catalog here, in code, and slotted at the answer boundary exactly as every
other grounded value is.

Source is the course wiki page's frontmatter title, which reads
`<code> — <English name> (<Hebrew name>)` and covers 2601 of 2611 course pages.
`engine.graph.nodes[code]["name"]` is NOT the source: it is Hebrew-only and
missing outright for some courses (00940704, 01040065 among them).
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.retrieval.graph_engine.graph_registry import graph_registry

# A course code as it appears in a fact value: exactly 8 digits. Narrow on
# purpose -- a grade, a credit total and a semester code must never be looked up
# as if they were courses.
_COURSE_CODE = re.compile(r"^\d{8}$")
_FRONTMATTER_TITLE = re.compile(r"^title:\s*\"?(.+?)\"?\s*$", re.M)
# The title's leading `<code> — ` prefix; the code is already in the answer.
_TITLE_LEAD = re.compile(r"^\s*\d{6,8}\s*[—\-–]\s*")
_TRAILING_PARENS = re.compile(r"\s*\(([^()]*)\)\s*$")
_HEBREW = re.compile(r"[֐-׿]")
# Frontmatter sits at the top; no need to scan whole course pages.
_FRONTMATTER_SCAN_CHARS = 1500


def _english_name(title: str) -> str | None:
    """The English portion of a wiki title, or None if it has none.

    Drops ONLY a trailing parenthesised group that contains Hebrew. Stripping
    every parenthesised group instead would turn "Introduction to Data
    Engineering (Advanced)" into the name of a different course.
    """
    name = _TITLE_LEAD.sub("", title.strip())
    trailing = _TRAILING_PARENS.search(name)
    if trailing and _HEBREW.search(trailing.group(1)):
        name = name[: trailing.start()].strip()
    if not name or _HEBREW.search(name):
        return None
    return name


@lru_cache(maxsize=1)
def _name_index() -> dict[str, str]:
    """code -> English name, built once from the loaded wiki pages (~20ms).

    Degrades to an empty index if the graph is not configured: a missing name
    costs readability, never correctness, so it must not raise into an answer.
    """
    try:
        engine = graph_registry.get_engine()
    except Exception:  # noqa: BLE001 -- unconfigured/unloadable graph is not fatal here
        return {}
    index: dict[str, str] = {}
    for slug, code in engine.slug_to_course_code.items():
        content = (engine.wiki_pages.get(slug) or {}).get("content") or ""
        title = _FRONTMATTER_TITLE.search(content[:_FRONTMATTER_SCAN_CHARS])
        if not title:
            continue
        name = _english_name(title.group(1))
        if name:
            index[code] = name
    return index


def course_display_name(value: str) -> str | None:
    """The course's English name, or None if `value` is not a known course code."""
    if not _COURSE_CODE.match(value or ""):
        return None
    return _name_index().get(value)


def reset_course_name_index() -> None:
    """Test hook -- the index is built from whichever graph engine is loaded."""
    _name_index.cache_clear()
