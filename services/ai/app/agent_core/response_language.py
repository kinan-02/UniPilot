"""Which language the student's answer must be written in.

Decided in code, from the student's own message, because the model demonstrably
cannot decide it from context.

CAUGHT LIVE (2026-07-16, ise_correctness): three of six plain-English questions
came back entirely in Hebrew. The rule the model was given is reasonable read
aloud -- "match their language ... if they mix both, prefer the dominant
language" -- but it is evaluated against the whole prompt, and by composition
time the prompt is a wall of Hebrew course names
(`מודלים למסחר אלקטרוני`, `מבני נתונים ואלגוריתמים`, ...). The dominant language
of that soup is Hebrew, so the model dutifully answered in Hebrew. It followed
the instruction; the instruction pointed at the wrong text.

The student's language is a property of ONE string -- their message -- and is
decidable by script. So decide it here and hand composition a concrete
directive, rather than asking it to infer the answer from everything it can see.
Same instinct as `subagents/fact_projection.py` reading a fact's value out of
the recorded tool envelope instead of asking a model to report it honestly.

This does not make the model obey (that is still an instruction in a prompt, and
the eval gates it). It removes the INFERENCE, which is the part that failed.
"""

from __future__ import annotations

import re

# Hebrew is the only non-Latin script this institution's students write in.
# Widen this when that stops being true -- reactively, with a real case, the way
# `_OPERATORS` in expression_tree.py grows.
_HEBREW_CHARS = re.compile(r"[֐-׿]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")
_WORDS = re.compile(r"[^\s,.;:!?()\[\]{}\"'`/\\|<>~@#$%^&*+=-]+")

ENGLISH = "English"
HEBREW = "Hebrew"


def detect_message_language(text: str) -> str:
    """The dominant language of a piece of text, counted in WORDS not characters.

    Counting characters is the obvious implementation and it is wrong. A student
    writes:

        Am I eligible for 00960211 -- "מודלים למסחר אלקטרוני"?

    ...which is an English sentence quoting one Hebrew course name, and which has
    14 Latin characters to 20 Hebrew. By character it is "Hebrew"; by any honest
    reading it is English. Hebrew orthography drops vowels, so Hebrew words carry
    more meaning per character and a single quoted course title outweighs a whole
    English clause. A word-level count gets this right (4 English words to 3
    Hebrew) because language is a property of words.

    A token counts for whichever script it contains -- course numbers and
    punctuation contain neither and are ignored, which is correct: `00960211` is
    not evidence of anything.

    Ties, and text with no words at all, resolve to English: this institution's
    lingua franca, and the safer default for a message carrying no signal.
    """
    hebrew = 0
    latin = 0
    for word in _WORDS.findall(text or ""):
        if _HEBREW_CHARS.search(word):
            hebrew += 1
        elif _LATIN_CHARS.search(word):
            latin += 1
    return HEBREW if hebrew > latin else ENGLISH


def response_language_directive(message: str) -> str:
    """A `tone_language_notes` line naming the language to answer in.

    Explicit about the trap it exists to close: the retrieved context is full of
    Hebrew course names even when the student wrote English, and quoting one is
    correct and expected -- it is the PROSE that must not switch.
    """
    language = detect_message_language(message)
    return (
        f"Write the answer in {language}. The student wrote their message in {language}; "
        "the language of the retrieved context is irrelevant to this choice, however much of it "
        "there is. Quote course names verbatim in their own language -- that is not a language "
        f"switch -- but every sentence you write must be {language}."
    )


__all__ = ["ENGLISH", "HEBREW", "detect_message_language", "response_language_directive"]
