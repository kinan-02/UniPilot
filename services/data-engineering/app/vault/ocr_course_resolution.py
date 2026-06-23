"""Resolve known OCR artifacts in vault-exported catalog course references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.catalog.course_reference_policy import (
    KNOWN_OCR_CORRECTIONS,
    is_cross_faculty_course_reference,
    is_dds_scoped_course_number,
)

# Backward-compatible alias for tests and reports.
KNOWN_OCR_CORRECTIONS_MAP = KNOWN_OCR_CORRECTIONS


@dataclass(frozen=True)
class OcrResolution:
    group_id: str
    from_course_number: str
    to_course_number: str | None
    reason: str
    auto_applied: bool


def suggest_ocr_correction(
    course_number: str,
    *,
    ingestible_course_numbers: set[str],
) -> tuple[str | None, str]:
    if course_number in KNOWN_OCR_CORRECTIONS:
        target = KNOWN_OCR_CORRECTIONS[course_number]
        if target is None:
            return None, "known-ocr-removal"
        return target, "known-ocr-correction"

    if course_number in ingestible_course_numbers:
        return course_number, "already-ingestible"

    if is_cross_faculty_course_reference(course_number):
        return course_number, "cross-faculty-reference"

    if not is_dds_scoped_course_number(course_number):
        return course_number, "out-of-scope"

    return course_number, "vault-reference-preserved"


def apply_ocr_resolutions_to_catalog(
    document: dict[str, Any],
    *,
    ingestible_course_numbers: set[str],
) -> list[OcrResolution]:
    """Normalize DDS OCR typos in-place; cross-faculty refs are preserved."""
    resolutions: list[OcrResolution] = []

    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            group_id = str(group.get("groupId") or "")
            updated_refs: list[dict[str, Any]] = []
            seen_numbers: set[str] = set()

            for ref in group.get("courseReferences", []):
                original = str(ref.get("courseNumber") or "")
                if not original:
                    continue

                target, reason = suggest_ocr_correction(
                    original,
                    ingestible_course_numbers=ingestible_course_numbers,
                )
                auto_applied = target != original or (target is None and original in KNOWN_OCR_CORRECTIONS)

                if target is None:
                    if original in KNOWN_OCR_CORRECTIONS:
                        resolutions.append(
                            OcrResolution(
                                group_id=group_id,
                                from_course_number=original,
                                to_course_number=None,
                                reason=reason,
                                auto_applied=True,
                            )
                        )
                    continue

                if target in seen_numbers:
                    if auto_applied and original != target:
                        resolutions.append(
                            OcrResolution(
                                group_id=group_id,
                                from_course_number=original,
                                to_course_number=target,
                                reason=f"{reason}-deduplicated",
                                auto_applied=True,
                            )
                        )
                    continue

                seen_numbers.add(target)
                if auto_applied and original != target:
                    resolutions.append(
                        OcrResolution(
                            group_id=group_id,
                            from_course_number=original,
                            to_course_number=target,
                            reason=reason,
                            auto_applied=True,
                        )
                    )

                if original != target:
                    updated_ref = dict(ref)
                    updated_ref["courseNumber"] = target
                    notes = list(updated_ref.get("notes") or [])
                    notes.append(f"ocr-resolution:{original}->{target}")
                    updated_ref["notes"] = notes
                    updated_refs.append(updated_ref)
                else:
                    updated_refs.append(ref)

            group["courseReferences"] = updated_refs

    report = document.setdefault("curationReport", {})
    report["ocrResolutions"] = [
        {
            "groupId": item.group_id,
            "fromCourseNumber": item.from_course_number,
            "toCourseNumber": item.to_course_number,
            "reason": item.reason,
            "autoApplied": item.auto_applied,
        }
        for item in resolutions
    ]
    return resolutions
