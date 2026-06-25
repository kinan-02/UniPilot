"""Technion course-number normalization and extraction helpers."""

from __future__ import annotations

import re

from app.utils.hebrew_rtl import reverse_rtl_line_fragment

COURSE_NUMBER_PATTERN = re.compile(
    r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)",
)
WIKILINK_CELL_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
INLINE_COURSE_TITLE_PATTERN = re.compile(
    r"(?<!\d)(0\d{6,8}|\d{7,8})\s+([א-תA-Za-z0-9][^\n|+]{2,80}?)(?=\s{2,}0\d|\s*$|\||\n|\+)",
)


def _score_candidate(value: str, *, raw_digits: str = "") -> int:
    score = 0
    if value.startswith("00"):
        score += 1
    if value[:4] in {"0094", "0096", "0104", "0098", "0090", "0234", "0114", "0324", "0044"}:
        score += 4
    if raw_digits and value == raw_digits.zfill(8)[-8:]:
        score += 2
    if value.startswith("0010") or value.startswith("0009"):
        score -= 2
    return score


def _candidate_normalized_values(digits: str) -> list[str]:
    candidates: list[str] = []
    if not digits:
        return candidates

    raw = digits
    candidates.append(raw.zfill(8)[-8:])

    if len(raw) == 7:
        candidates.append(raw.zfill(8)[-8:])

    # Trailing-zero truncation applies only when the value is not already a valid 8-digit course id.
    if len(raw) == 8 and raw.endswith("0") and not re.fullmatch(r"0\d{7}", raw):
        candidates.append(raw[:-1].zfill(8)[-8:])

    if len(raw) == 8 and raw.startswith("0") and raw.endswith("0"):
        truncated = raw[:-1]
        if len(truncated) == 7:
            candidates.append(truncated.zfill(8)[-8:])

    if len(raw) == 9 and raw.startswith("0"):
        candidates.append(raw[1:].zfill(8)[-8:])

    # Leading junk digit from spaced OCR like "3 0980413" -> 30980413
    if len(raw) == 8 and not re.fullmatch(r"0\d{7}", raw):
        candidates.append(raw[1:].zfill(8)[-8:])

    unique: list[str] = []
    for value in candidates:
        if re.fullmatch(r"0\d{7}", value) and value not in unique:
            unique.append(value)
    return unique


def normalize_course_number(raw: str) -> str | None:
    """Normalize Technion course numbers to 8-digit 0-prefixed strings."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None

    valid = _candidate_normalized_values(digits)
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    return max(valid, key=lambda candidate: _score_candidate(candidate, raw_digits=digits))


def resolve_course_number_token(raw: str) -> str | None:
    """Normalize a table cell or inline token that may use Obsidian wikilinks."""
    text = (raw or "").strip()
    if not text:
        return None

    if not text.startswith("[["):
        direct = normalize_course_number(text)
        if direct is not None:
            return direct

    for match in WIKILINK_CELL_PATTERN.finditer(text):
        alias = (match.group(2) or "").strip()
        slug = (match.group(1) or "").strip()
        slug_prefix = slug.split("-", 1)[0] if slug else ""
        for candidate in (alias, slug_prefix, slug):
            if not candidate:
                continue
            normalized = normalize_course_number(candidate)
            if normalized is not None:
                return normalized

    for match in COURSE_NUMBER_PATTERN.finditer(text):
        normalized = normalize_course_number(match.group(1))
        if normalized is not None:
            return normalized

    return None


def collect_course_numbers_from_text(text: str) -> list[str]:
    """Extract unique normalized course numbers from wiki body text."""
    numbers: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        normalized = resolve_course_number_token(raw)
        if normalized is None or normalized in seen:
            return
        seen.add(normalized)
        numbers.append(normalized)

    for match in WIKILINK_CELL_PATTERN.finditer(text):
        alias = (match.group(2) or "").strip()
        slug = (match.group(1) or "").strip()
        slug_prefix = slug.split("-", 1)[0] if slug else ""
        for candidate in (alias, slug_prefix):
            if candidate:
                add(candidate)

    for match in COURSE_NUMBER_PATTERN.finditer(text):
        add(match.group(1))

    return numbers


def strip_wikilinks_for_inline_scan(text: str) -> str:
    """Replace wikilinks with alias/slug text so inline title regex does not see `]]`."""
    def _replace(match: re.Match[str]) -> str:
        alias = (match.group(2) or "").strip()
        slug = (match.group(1) or "").strip()
        slug_prefix = slug.split("-", 1)[0] if slug else slug
        return alias or slug_prefix or ""

    return WIKILINK_CELL_PATTERN.sub(_replace, text)


def clean_cell_text(text: str) -> str:
    cleaned = reverse_rtl_line_fragment(text.strip())
    cleaned = cleaned.replace("⸋", "").replace("׳", "'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_course_title_pairs(text: str) -> list[dict[str, object]]:
    """Extract course number + title (+ optional credits) pairs from free text."""
    results: list[dict[str, object]] = []
    seen: set[str] = set()

    for match in INLINE_COURSE_TITLE_PATTERN.finditer(text):
        number = normalize_course_number(match.group(1))
        if number is None or number in seen:
            continue
        title = clean_cell_text(match.group(2))
        if not title or title in {"(table cell)", "נק", "נק'"}:
            continue
        if re.fullmatch(r"[\d\.\s\-]+", title):
            continue
        seen.add(number)
        results.append(
            {
                "courseNumber": number,
                "titleHint": title[:120],
                "creditsHint": None,
            }
        )

    for match in COURSE_NUMBER_PATTERN.finditer(text):
        number = normalize_course_number(match.group(1))
        if number is None or number in seen:
            continue
        seen.add(number)
        results.append(
            {
                "courseNumber": number,
                "titleHint": None,
                "creditsHint": None,
            }
        )

    return results


def split_subject_number(course_number: str) -> tuple[str, str]:
    return course_number[:4], course_number[4:]
