"""Known cross-track course code equivalents (same course, different track catalog codes)."""

from __future__ import annotations

from app.planning.prerequisite_resolver import canonical_course_number

# Vault: 0960211 (DNE/IEM) and 0960221 (ISE) — same e-commerce models course.
KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("00960211", "00960221"),
)


def _course_number_keys(raw: str) -> set[str]:
    keys = {raw}
    canonical = canonical_course_number(raw)
    if canonical:
        keys.add(canonical)
    return keys


def cross_track_equivalence_sets() -> list[set[str]]:
    groups: list[set[str]] = []
    for members in KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS:
        keys: set[str] = set()
        for member in members:
            keys |= _course_number_keys(member)
        if keys:
            groups.append(keys)
    return groups
