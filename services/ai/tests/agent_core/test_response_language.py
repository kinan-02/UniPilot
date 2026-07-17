"""The answer's language is decided from the student's message, in code.

Regression for the 2026-07-16 ise_correctness run, where three of six English
questions came back entirely in Hebrew because the model inferred "dominant
language" from a prompt full of Hebrew course names instead of from the student.
"""

from __future__ import annotations

from app.agent_core.response_language import (
    ENGLISH,
    HEBREW,
    detect_message_language,
    response_language_directive,
)

_ENGLISH_QUESTION = "Am I eligible to take course 00960211?"
_HEBREW_QUESTION = "האם אני זכאי להירשם לקורס 00960211?"


def test_english_question_is_detected_as_english():
    assert detect_message_language(_ENGLISH_QUESTION) == ENGLISH


def test_hebrew_question_is_detected_as_hebrew():
    assert detect_message_language(_HEBREW_QUESTION) == HEBREW


def test_an_english_question_naming_a_hebrew_course_is_still_english():
    # The exact shape that fooled the model: Hebrew present, English dominant.
    message = 'Am I eligible for 00960211 -- "מודלים למסחר אלקטרוני"?'

    assert detect_message_language(message) == ENGLISH


def test_a_message_with_no_letters_defaults_to_english():
    # A bare course number carries no language signal; do not guess Hebrew.
    assert detect_message_language("00960211?") == ENGLISH
    assert detect_message_language("") == ENGLISH


def test_directive_names_the_students_language_and_disclaims_the_context():
    directive = response_language_directive(_ENGLISH_QUESTION)

    assert "English" in directive
    # The whole point: the retrieved context's language must not decide this.
    assert "context is irrelevant" in directive
    # ...while quoting a Hebrew course name stays explicitly allowed, or the
    # model over-corrects and translates course names.
    assert "Quote course names verbatim" in directive


def test_directive_follows_a_hebrew_student_into_hebrew():
    directive = response_language_directive(_HEBREW_QUESTION)

    assert "Hebrew" in directive
    assert "English" not in directive
