"""Normalize course numbers and expand catalog reference alternatives."""

from __future__ import annotations

from typing import Any

from app.curriculum.data_quality import parse_alternatives_from_text
from app.curriculum.cross_track_equivalence import cross_track_equivalence_sets
from app.planning.prerequisite_resolver import canonical_course_number


def course_number_keys(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    value = str(raw)
    keys = {value}
    canonical = canonical_course_number(value)
    if canonical:
        keys.add(canonical)
    return keys


def course_reference_number_keys(reference: dict[str, Any]) -> set[str]:
    """Primary course number plus explicit/text alternatives for one catalog reference."""
    numbers: set[str] = set()

    primary = reference.get("courseNumber")
    if primary is not None:
        numbers |= course_number_keys(str(primary))

    for alternative in reference.get("alternatives") or []:
        numbers |= course_number_keys(str(alternative))

    notes = reference.get("notes") or []
    notes_text = " ".join(str(note) for note in notes)
    for alternative in parse_alternatives_from_text(
        notes_text,
        reference.get("prerequisitesText"),
    ):
        numbers |= course_number_keys(alternative)

    return numbers


def course_references_number_keys(references: list[dict[str, Any]] | None) -> set[str]:
    numbers: set[str] = set()
    for reference in references or []:
        numbers |= course_reference_number_keys(reference)
    return numbers


def build_matrix_mandatory_equivalence_groups(
    semester_matrix_documents: list[dict[str, Any]] | None,
) -> list[set[str]]:
    """Equivalence sets from semester matrix rows only (no cross-track pairs)."""
    groups: list[set[str]] = []
    for document in semester_matrix_documents or []:
        for reference in document.get("courseReferences") or []:
            keys = course_reference_number_keys(reference)
            if keys:
                groups.append(keys)
    return merge_overlapping_equivalence_groups(groups)


def build_mandatory_equivalence_groups(
    semester_matrix_documents: list[dict[str, Any]] | None,
) -> list[set[str]]:
    """Matrix row groups merged with documented cross-track code pairs."""
    return merge_with_cross_track_equivalence_groups(
        build_matrix_mandatory_equivalence_groups(semester_matrix_documents)
    )


def build_progress_equivalence_groups(
    semester_matrix_documents: list[dict[str, Any]] | None,
    catalog_courses: list[dict[str, Any]] | None = None,
) -> list[set[str]]:
    """Matrix + cross-track + catalog overlap (מקצועות ללא זיכוי נוסף) groups."""
    from app.services.catalog_overlap_groups import build_catalog_overlap_groups

    combined = [set(group) for group in build_mandatory_equivalence_groups(semester_matrix_documents)]
    if catalog_courses:
        combined.extend(build_catalog_overlap_groups(catalog_courses))
    return merge_overlapping_equivalence_groups(combined)


def merge_with_cross_track_equivalence_groups(groups: list[set[str]]) -> list[set[str]]:
    """Union matrix/graph groups with registrar-documented cross-track code pairs."""
    combined = [set(group) for group in groups]
    combined.extend(cross_track_equivalence_sets())
    return merge_overlapping_equivalence_groups(combined)


def merge_overlapping_equivalence_groups(groups: list[set[str]]) -> list[set[str]]:
    """Union matrix rows that refer to the same course slot (duplicate catalog rows)."""
    merged: list[set[str]] = []
    for raw_group in groups:
        group = set(raw_group)
        if not group:
            continue

        overlap_indexes: list[int] = []
        for index, existing in enumerate(merged):
            if group & existing:
                overlap_indexes.append(index)

        for index in reversed(overlap_indexes):
            group |= merged.pop(index)

        merged.append(group)

    return merged


def completed_mandatory_course_number_keys(
    completed_courses: list[dict[str, Any]],
) -> set[str]:
    keys: set[str] = set()
    for course in completed_courses:
        keys |= course_number_keys(course.get("courseNumber"))
    return keys


def filter_remaining_mandatory_courses(
    remaining_courses: list[dict[str, Any]],
    completed_courses: list[dict[str, Any]],
    *,
    satisfied_group_keys: set[frozenset[str]] | None = None,
    mandatory_groups: list[set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Drop remaining slots already satisfied by a completed course or equivalence group."""
    completed_keys = completed_mandatory_course_number_keys(completed_courses)
    filtered: list[dict[str, Any]] = []
    seen_group_keys: set[frozenset[str]] = set()

    for entry in remaining_courses:
        course_number = entry.get("courseNumber")
        group_key = (
            mandatory_group_for_course(str(course_number) if course_number else None, mandatory_groups or [])
            if mandatory_groups
            else None
        )
        if group_key is not None:
            if group_key in (satisfied_group_keys or set()) or group_key in seen_group_keys:
                continue
            entry_keys = course_number_keys(str(course_number) if course_number else None)
            if entry_keys & completed_keys:
                continue
            seen_group_keys.add(group_key)
            filtered.append(entry)
            continue

        entry_keys = course_number_keys(str(course_number) if course_number else None)
        if entry_keys & completed_keys:
            continue
        filtered.append(entry)

    return filtered


def build_mandatory_course_number_keys(
    semester_matrix_documents: list[dict[str, Any]] | None,
) -> set[str]:
    numbers: set[str] = set()
    for group in build_mandatory_equivalence_groups(semester_matrix_documents):
        numbers |= group
    return numbers


def course_matches_equivalence_group(
    course_number: str | None,
    group: set[str],
) -> bool:
    if not course_number or not group:
        return False
    return bool(course_number_keys(course_number) & group)


def mandatory_group_for_course(
    course_number: str | None,
    mandatory_groups: list[set[str]],
) -> frozenset[str] | None:
    if not course_number:
        return None
    keys = course_number_keys(course_number)
    for group in mandatory_groups:
        if keys & group:
            return frozenset(group)
    return None


def is_mandatory_curriculum_course(
    course_number: str | None,
    mandatory_groups: list[set[str]] | set[str],
) -> bool:
    if not course_number or not mandatory_groups:
        return False
    if isinstance(mandatory_groups, set):
        return bool(course_number_keys(course_number) & mandatory_groups)
    return any(course_matches_equivalence_group(course_number, group) for group in mandatory_groups)


MANDATORY_BUCKET_SUFFIX_PRIORITY: tuple[str, ...] = (
    "core-mandatory",
    "mandatory-technion-and-faculty-courses",
    "track-mandatory-courses",
)


def resolve_mandatory_bucket_suffix(
    buckets_by_suffix: dict[str, dict[str, Any]],
) -> str | None:
    """Pick the credit bucket that receives semester-matrix mandatory completions."""
    for suffix in MANDATORY_BUCKET_SUFFIX_PRIORITY:
        requirement = buckets_by_suffix.get(suffix)
        if requirement and bool(requirement.get("isMandatory", True)):
            return suffix
    for suffix, requirement in buckets_by_suffix.items():
        if bool(requirement.get("isMandatory", True)):
            return suffix
    return None


def build_remaining_mandatory_course_entries(
    semester_matrix_documents: list[dict[str, Any]] | None,
    satisfied_group_keys: set[frozenset[str]],
    catalog_courses_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One remaining entry per unsatisfied matrix equivalence group."""
    remaining: list[dict[str, Any]] = []
    seen_groups: set[frozenset[str]] = set()
    mandatory_groups = build_mandatory_equivalence_groups(semester_matrix_documents)

    for document in semester_matrix_documents or []:
        for reference in document.get("courseReferences") or []:
            keys = course_reference_number_keys(reference)
            if not keys:
                continue
            primary = reference.get("courseNumber")
            lookup_number = str(primary) if primary is not None else sorted(keys)[0]
            group_key = mandatory_group_for_course(lookup_number, mandatory_groups) or frozenset(keys)
            if group_key in satisfied_group_keys or group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            title = reference.get("titleHint") or reference.get("title")
            catalog_credits = None
            course_id: str | None = None

            if catalog_courses_by_id:
                for candidate_id, catalog_course in catalog_courses_by_id.items():
                    candidate_number = catalog_course.get("courseNumber") or catalog_course.get("number")
                    if candidate_number is None:
                        continue
                    if not course_matches_equivalence_group(str(candidate_number), keys):
                        continue
                    course_id = str(candidate_id)
                    title = title or catalog_course.get("title") or catalog_course.get("titleHebrew")
                    catalog_credits = catalog_course.get("credits")
                    break

            display_number = str(primary) if primary is not None else sorted(keys)[0]
            remaining.append(
                {
                    "courseId": course_id or f"matrix:{display_number}",
                    "courseNumber": display_number,
                    "courseTitle": title,
                    "catalogCredits": catalog_credits,
                    "creditsEarned": None,
                    "grade": None,
                    "semesterCode": None,
                }
            )

    return remaining
