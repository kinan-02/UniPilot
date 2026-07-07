"""Vault-signed course numbers that must never appear in the public catalog API."""

from __future__ import annotations

# Keep aligned with data-engineering `PRODUCTION_EXCLUDED_COURSE_NUMBERS`.
PRODUCTION_EXCLUDED_COURSE_NUMBERS: frozenset[str] = frozenset(
    {
        "00960226",
        "00960244",
        "00960251",
        "00960293",
        "00960311",
        "00960335",
        "00960351",
        "00960470",
        "00970211",
        "00970280",
        "00970329",
        "00980312",
        "00980455",
        "02740300",
    }
)

EXCLUDED_COURSE = "00960226"


def is_production_excluded_course_number(course_number: str | None) -> bool:
    if not course_number:
        return False
    return str(course_number) in PRODUCTION_EXCLUDED_COURSE_NUMBERS
