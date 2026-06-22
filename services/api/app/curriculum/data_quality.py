"""Data-quality flags for vault-sourced curriculum nodes."""

from __future__ import annotations

import re
from typing import Any

ALT_PATTERN = re.compile(r"Alt:\s*(\d{6,8})", re.IGNORECASE)
CREDITS_RANGE_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)"
)


def parse_alternatives_from_text(*texts: str | None) -> list[str]:
    alternatives: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in ALT_PATTERN.finditer(text):
            number = match.group(1)
            if number not in seen:
                seen.add(number)
                alternatives.append(number)
    return alternatives


def parse_credits_range(raw: str | None) -> dict[str, float] | None:
    if raw is None:
        return None
    cleaned = raw.replace("≈", "").strip()
    match = CREDITS_RANGE_PATTERN.match(cleaned)
    if not match:
        return None
    low = float(match.group(1))
    high = float(match.group(2))
    if low > high:
        low, high = high, low
    return {"min": low, "max": high}


def build_credits_display(
    *,
    credits: float | None,
    credits_range: dict[str, float] | None,
    credits_hint: float | None,
) -> dict[str, Any]:
    if credits_range:
        low = credits_range["min"]
        high = credits_range["max"]
        display = f"{low:g}–{high:g}"
        return {
            "display": display,
            "value": None,
            "uncertain": True,
            "range": credits_range,
        }

    resolved = credits if credits is not None else credits_hint
    if resolved is None:
        return {
            "display": "—",
            "value": None,
            "uncertain": True,
            "range": None,
        }

    return {
        "display": f"{resolved:g}",
        "value": float(resolved),
        "uncertain": False,
        "range": None,
    }


def build_data_quality_flags(
    *,
    course_ref: dict[str, Any] | None,
    catalog_course: dict[str, Any] | None,
    alternatives: list[str],
    credits_uncertain: bool,
) -> dict[str, Any]:
    ref = course_ref or {}
    notes = list(ref.get("notes") or [])
    manual_review = bool(
        ref.get("manualReviewRequired")
        or (course_ref is None and catalog_course is None)
    )
    confidence = ref.get("confidence") or (
        "high" if catalog_course else "low"
    )
    has_alternatives = len(alternatives) > 0
    verify_with_registrar = manual_review or credits_uncertain or has_alternatives

    return {
        "manualReviewRequired": manual_review,
        "confidence": confidence,
        "hasAlternatives": has_alternatives,
        "creditsUncertain": credits_uncertain,
        "verifyWithRegistrar": verify_with_registrar,
        "sourceNotes": notes[:5],
    }
