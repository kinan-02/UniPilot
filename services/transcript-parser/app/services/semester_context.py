"""Semester heading detection for Technion transcript text."""

from __future__ import annotations

import re

SEMESTER_CODE_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<term>[123])$")
ACADEMIC_YEAR_PATTERN = re.compile(r"(?P<start>\d{4})\s*[-–—/]\s*(?P<end>\d{4})")
HEBREW_SEMESTER_A = re.compile(r"סמ\s*[\"']?א|סמסטר\s*א|חורף", re.IGNORECASE)
HEBREW_SEMESTER_B = re.compile(r"סמ\s*[\"']?ב|סמסטר\s*ב|אביב", re.IGNORECASE)
HEBREW_SEMESTER_C = re.compile(r"סמ\s*[\"']?ג|סמסטר\s*ג|קיץ", re.IGNORECASE)
ENGLISH_SEMESTER_WINTER = re.compile(r"\bwinter\b", re.IGNORECASE)
ENGLISH_SEMESTER_SPRING = re.compile(r"\bspring\b", re.IGNORECASE)
ENGLISH_SEMESTER_SUMMER = re.compile(r"\bsummer\b", re.IGNORECASE)


def infer_term_from_line(line: str) -> int | None:
    if HEBREW_SEMESTER_A.search(line) or ENGLISH_SEMESTER_WINTER.search(line):
        return 1
    if HEBREW_SEMESTER_B.search(line) or ENGLISH_SEMESTER_SPRING.search(line):
        return 2
    if HEBREW_SEMESTER_C.search(line) or ENGLISH_SEMESTER_SUMMER.search(line):
        return 3
    return None


def parse_semester_code(line: str) -> str | None:
    stripped = line.strip()
    direct = SEMESTER_CODE_PATTERN.match(stripped)
    if direct:
        year = direct.group("year")
        term = direct.group("term")
        return f"{year}-{term}"

    year_match = ACADEMIC_YEAR_PATTERN.search(stripped)
    if not year_match:
        return None

    term = infer_term_from_line(stripped)
    if term is None:
        return None
    start_year = int(year_match.group("start"))
    return f"{start_year}-{term}"


def extract_student_id(text: str) -> str | None:
    for line in text.splitlines()[:40]:
        match = re.search(r"\b(\d{9})\b", line)
        if match:
            return match.group(1)
    return None
