"""Best-effort Hebrew / RTL cleanup for PDF text extraction."""

from __future__ import annotations

import re

HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")
PROGRAM_CODE_PATTERN = re.compile(r"00\d{4}-\d-\d{3}")
COURSE_NUMBER_PATTERN = re.compile(r"\b0\d{6,7}\b")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return MULTI_NEWLINE_PATTERN.sub("\n\n", normalized).strip()


def normalize_hebrew_punctuation(text: str) -> str:
    replacements = {
        "„": '"',
        "”": '"',
        "’": "'",
        "–": "-",
        "—": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def hebrew_letter_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha() or HEBREW_CHAR_PATTERN.match(char)]
    if not letters:
        return 0.0
    hebrew_count = sum(1 for char in letters if HEBREW_CHAR_PATTERN.match(char))
    return hebrew_count / len(letters)


def should_reverse_line(line: str) -> bool:
    if not line.strip():
        return False
    if hebrew_letter_ratio(line) < 0.4:
        return False
    stripped = line.strip()
    if stripped and stripped[0] in "([*" and hebrew_letter_ratio(stripped) > 0.6:
        return True
    if stripped[:1].isspace() is False and HEBREW_CHAR_PATTERN.match(stripped[:1]):
        return True
    return hebrew_letter_ratio(line) >= 0.55


def _protect_tokens(line: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"<<{len(tokens) - 1}>>"

    protected = PROGRAM_CODE_PATTERN.sub(replacer, line)
    protected = COURSE_NUMBER_PATTERN.sub(replacer, protected)
    return protected, tokens


def _restore_tokens(line: str, tokens: list[str]) -> str:
    restored = line
    for index, token in enumerate(tokens):
        restored = restored.replace(f">>{index}<<", token)
        restored = restored.replace(f"<<{index}>>", token)
    return restored


def reverse_rtl_line_fragment(line: str) -> str:
    protected, tokens = _protect_tokens(line)
    if should_reverse_line(protected):
        protected = protected[::-1]
    return _restore_tokens(protected, tokens)


def process_hebrew_text(raw_text: str) -> tuple[str, str]:
    """Return (raw_text, processed_text) preserving the original."""
    normalized = normalize_whitespace(raw_text)
    normalized = normalize_hebrew_punctuation(normalized)
    processed_lines = [reverse_rtl_line_fragment(line) for line in normalized.splitlines()]
    processed = "\n".join(processed_lines)
    return raw_text, processed
