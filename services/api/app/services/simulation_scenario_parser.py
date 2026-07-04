"""Rule-based natural-language scenario parser (Scenario Parser agent, v1)."""

from __future__ import annotations

import re
from typing import Any

_COURSE_CODE_RE = re.compile(r"\b0\d{7}\b")

_DROP_PATTERNS = (
    re.compile(r"\bdrop\s+(?:course\s+)?(?P<number>0\d{7})\b", re.IGNORECASE),
    re.compile(r"\bremove\s+(?:course\s+)?(?P<number>0\d{7})\b", re.IGNORECASE),
    re.compile(r"לזרוק\s+(?:את\s+)?(?:קורס\s+)?(?P<number>0\d{7})"),
    re.compile(r"להוריד\s+(?:את\s+)?(?:קורס\s+)?(?P<number>0\d{7})"),
)

_ADD_COMPLETED_PATTERNS = (
    re.compile(r"\bcomplete\s+(?:course\s+)?(?P<number>0\d{7})\b", re.IGNORECASE),
    re.compile(r"לסיים\s+(?:את\s+)?(?:קורס\s+)?(?P<number>0\d{7})"),
)

_ADD_PLANNED_PATTERNS = (
    re.compile(
        r"\badd\s+(?P<number>0\d{7})\s+(?:to\s+)?(?:my\s+)?(?:next\s+)?(?:semester|plan)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\badd\s+(?:course\s+)?(?P<number>0\d{7})\s+(?:to\s+)?(?:my\s+)?plan\b", re.IGNORECASE),
    re.compile(r"לקחת\s+(?:את\s+)?(?P<number>0\d{7})\s+(?:בסמסטר|בתוכנית)"),
    re.compile(r"להוסיף\s+(?:לתוכנית|לסמסטר)\s+(?:את\s+)?(?P<number>0\d{7})"),
)

_ADD_TRANSCRIPT_PATTERNS = (
    re.compile(r"\badd\s+(?:course\s+)?(?P<number>0\d{7})\b", re.IGNORECASE),
    re.compile(r"להוסיף\s+(?:את\s+)?(?:קורס\s+)?(?P<number>0\d{7})"),
)

_TRACK_PATTERNS = (
    re.compile(
        r"\bswitch\s+to\s+track\s+(?P<slug>[a-z0-9-]+)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bchange\s+track\s+to\s+(?P<slug>[a-z0-9-]+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"לעבור\s+למסלול\s+(?P<slug>[a-z0-9-]+)"),
)


def parse_simulation_text(text: str) -> list[dict[str, Any]]:
    """
    Parse NL what-if prompts into structured simulation operations.
  Falls back to a single add_planned_course when only one course code appears
    in a planning-style sentence.
    """
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []

    operations: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()

    def append_unique(operation: dict[str, Any], number: str | None = None) -> None:
        key = number or operation.get("trackSlug") or operation.get("type")
        if key in seen_numbers:
            return
        operations.append(operation)
        if key:
            seen_numbers.add(key)

    for pattern in _DROP_PATTERNS:
        for match in pattern.finditer(normalized):
            append_unique(
                {"type": "drop_course", "courseNumber": match.group("number")},
                match.group("number"),
            )

    for pattern in _ADD_PLANNED_PATTERNS:
        for match in pattern.finditer(normalized):
            append_unique(
                {"type": "add_planned_course", "courseNumber": match.group("number")},
                f"plan:{match.group('number')}",
            )

    for pattern in _ADD_TRANSCRIPT_PATTERNS:
        for match in pattern.finditer(normalized):
            append_unique(
                {"type": "add_course", "courseNumber": match.group("number")},
                f"add:{match.group('number')}",
            )

    for pattern in _ADD_COMPLETED_PATTERNS:
        for match in pattern.finditer(normalized):
            append_unique(
                {"type": "add_course", "courseNumber": match.group("number")},
                f"complete:{match.group('number')}",
            )

    for pattern in _TRACK_PATTERNS:
        for match in pattern.finditer(normalized):
            append_unique(
                {"type": "change_track", "trackSlug": match.group("slug")},
                f"track:{match.group('slug')}",
            )

    if not operations:
        numbers = _COURSE_CODE_RE.findall(normalized)
        lowered = normalized.lower()
        planning_hint = any(
            token in lowered
            for token in (
                "next semester",
                "semester plan",
                "spring",
                "winter",
                "סמסטר",
                "תוכנית",
                "לקחת",
            )
        )
        drop_hint = any(token in lowered for token in ("drop", "remove", "לזרוק", "להוריד"))
        if len(numbers) == 1:
            number = numbers[0]
            if drop_hint:
                operations.append({"type": "drop_course", "courseNumber": number})
            elif planning_hint:
                operations.append({"type": "add_planned_course", "courseNumber": number})
            else:
                operations.append({"type": "add_planned_course", "courseNumber": number})

    return operations
