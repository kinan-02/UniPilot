"""Tests for the course code -> display-name lookup used at the answer boundary.

The live evals shipped answers like "The courses on your record with a final
grade above 90 are: 00940704, 00940219, 03240033." -- correct, grounded, and
close to unreadable. 7 of 10 answers in the 2026-07-18 run carried bare codes.

The name CANNOT come from the model: the grounding backstop only checks numerals
(`_NUM.findall`), so a typed course name is never validated, and a plausible
fabricated name welded to a real code is worse than no name at all -- the user
has no reason to doubt it. So the name is looked up in code and rendered, never
composed.
"""

from __future__ import annotations

from app.agent_core.loop.course_names import course_display_name


def test_known_course_resolves_to_its_english_name(use_real_academic_engine):
    assert course_display_name("00940224") == "Data Structures and Algorithms"
    assert course_display_name("00960211") == "E-Commerce Models"


def test_a_qualifier_is_part_of_the_name_and_is_kept(use_real_academic_engine):
    """00940704 is "Introduction to Data Engineering (Advanced)". Stripping every
    parenthesised group -- the obvious way to drop the Hebrew gloss -- silently
    renames it to the non-Advanced course, which is a different course."""
    assert course_display_name("00940704") == "Introduction to Data Engineering (Advanced)"


def test_hebrew_gloss_is_dropped(use_real_academic_engine):
    """Titles read `<code> — <English> (<Hebrew>)`; the gloss would mix scripts
    into an English answer."""
    name = course_display_name("01040065")
    assert name == "Algebra 1M2"


def test_unknown_code_has_no_name(use_real_academic_engine):
    assert course_display_name("99999999") is None


def test_non_course_values_are_ignored(use_real_academic_engine):
    """Only 8-digit course codes are looked up -- a grade, a credit total or a
    semester must never be mistaken for one."""
    assert course_display_name("85") is None
    assert course_display_name("92.5") is None
    assert course_display_name("2025-1") is None
    assert course_display_name("") is None
