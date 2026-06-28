"""Normalize Technion course numbers to 8-digit 0-prefixed strings."""

from __future__ import annotations

import re

_COURSE_NUMBER_PATTERN = re.compile(r"^0\d{7}$")


def normalize_course_number(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits or len(digits) < 6 or len(digits) > 9:
        return None
    padded = digits.zfill(8)[-8:]
    if not _COURSE_NUMBER_PATTERN.fullmatch(padded):
        return None
    return padded
