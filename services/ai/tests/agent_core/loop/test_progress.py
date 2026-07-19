"""Tests for the per-turn progress sentence shown while a question runs.

This text goes straight into a student's chat window, so the tests here are
mostly about what must NEVER appear in it: tool names, field names, ObjectIds.
"""

from __future__ import annotations

from app.agent_core.loop.course_names import set_catalog_names
from app.agent_core.loop.progress import GENERIC, phrase_for
from app.agent_core.loop.runner import _META_TOOLS
import app.agent_core.loop.progress as progress


# -- the key the model actually emits -----------------------------------------


def test_reads_the_key_the_model_emits():
    """The model emits `tool`; `_split_calls` renames it to `tool_name` only when
    building data-tool requests. Reading the renamed key matched nothing, so every
    turn reported the generic phrase -- three identical lines over a live 35s
    request, and the unit tests asserted the same wrong key, so they passed."""
    assert phrase_for([{"tool": "check_eligibility"}]) == "Checking your eligibility"
    assert phrase_for([{"tool_name": "check_eligibility"}]) == "Checking your eligibility"


# -- subjects make the line worth reading -------------------------------------


def test_names_the_course_being_checked(use_real_academic_engine):
    calls = [{"tool": "check_eligibility", "arguments": {"course_id": "00960211"}}]
    assert phrase_for(calls) == "Checking whether you can take E-Commerce Models"


def test_falls_back_to_the_code_when_the_course_has_no_name():
    calls = [{"tool": "get_course_profile", "arguments": {"course_id": "00000001"}}]
    assert phrase_for(calls) == "Reading the details for course 00000001"


def test_prettifies_a_track_slug():
    calls = [{"tool": "get_track_requirements", "arguments": {"track_slug": "track-information-systems-engineering"}}]
    assert phrase_for(calls) == "Reading the Information Systems Engineering requirements"


def test_quotes_a_free_text_query():
    calls = [{"tool": "search_knowledge", "arguments": {"query": "grade appeal deadline"}}]
    assert phrase_for(calls) == "Searching for “grade appeal deadline”"


def test_truncates_an_overlong_subject():
    calls = [{"tool": "search_knowledge", "arguments": {"query": "x" * 200}}]
    phrase = phrase_for(calls)
    assert len(phrase) < 90
    assert phrase.endswith("…”")


def test_entity_type_gets_its_own_sentence():
    """`get_entity` names a closed vocabulary, so each type reads as a sentence
    rather than echoing `completed_courses` at a student."""
    assert phrase_for([{"tool": "get_entity", "arguments": {"entity_type": "completed_courses"}}]) == (
        "Reading your completed courses"
    )
    assert phrase_for([{"tool": "get_entity", "arguments": {"entity_type": "student_profile"}}]) == (
        "Reading your profile"
    )


def test_a_batched_turn_counts_instead_of_naming_one(use_real_academic_engine):
    """Naming only the first of six courses would misrepresent the turn."""
    calls = [
        {"tool": "check_eligibility", "arguments": {"course_id": code}}
        for code in ("00960211", "00940224", "00960262")
    ]
    assert phrase_for(calls) == "Checking your eligibility for 3 courses"


# -- what must never leak ------------------------------------------------------


def test_never_echoes_an_object_id():
    """`entity_id` and friends carry Mongo ids. One in a chat window is a leak and
    reads as a crash."""
    calls = [{"tool": "traverse_relationship", "arguments": {"entity": "6a3db0e382df7b7cb04552c9"}}]
    phrase = phrase_for(calls)
    assert "6a3db0e382df7b7cb04552c9" not in phrase
    assert phrase == "Following prerequisite chains"


def test_never_echoes_an_unmapped_tool_name():
    phrase = phrase_for([{"tool": "some_future_internal_tool"}])
    assert phrase == GENERIC
    assert "some_future_internal_tool" not in phrase


def test_meta_tools_never_echo_their_field_names():
    """Meta-tool arguments are fact keys and field names -- `call_2`, `track_slug`.
    They are deliberately given no subject."""
    calls = [{"tool": "select", "arguments": {"key": "codes", "from_fact": "call_2", "field": "courseNumber"}}]
    phrase = phrase_for(calls)
    assert phrase == "Picking out the details that matter"
    for internal in ("call_2", "courseNumber", "from_fact"):
        assert internal not in phrase


def test_every_meta_tool_has_a_phrase():
    """`_preload_student_state` has the record by turn 1, so most turns of a
    typical question are meta. A meta-tool added later without a phrase silently
    degrades every turn that uses it back to the generic line."""
    missing = _META_TOOLS - progress._PHRASES.keys()
    assert not missing, f"meta-tools with no student-facing phrase: {sorted(missing)}"


def test_no_phrase_contains_an_underscore():
    """A cheap proxy for "this is an identifier, not a sentence"."""
    for phrase in progress._PHRASES.values():
        for text in (phrase.bare, phrase.with_subject, phrase.plural):
            assert text is None or "_" not in text, text
    for text in progress._ENTITY_PHRASES.values():
        assert "_" not in text, text


# -- degrading safely ----------------------------------------------------------


def test_handles_a_turn_with_no_tools():
    assert phrase_for([]) == GENERIC
    assert phrase_for([{}]) == GENERIC


def test_handles_malformed_arguments():
    """Arguments come from model output; a wrong shape must not raise into a turn."""
    for arguments in (None, "not a dict", [], {"course_id": None}, {"course_id": 12345}):
        assert phrase_for([{"tool": "check_eligibility", "arguments": arguments}])


def test_skips_unmapped_tools_to_find_a_known_one():
    calls = [{"tool": "some_future_internal_tool"}, {"tool": "get_entity", "arguments": {"entity_type": "course"}}]
    assert phrase_for(calls) == "Reading the course details"


def test_catalog_names_reach_the_progress_line():
    """The wiki does not cover every course; the catalog fallback should still
    give the student a name rather than a number."""
    set_catalog_names({"03240305": "היסטוריה של המדע"})
    try:
        calls = [{"tool": "get_course_profile", "arguments": {"course_id": "03240305"}}]
        assert phrase_for(calls) == "Reading the details for היסטוריה של המדע"
    finally:
        set_catalog_names({})
