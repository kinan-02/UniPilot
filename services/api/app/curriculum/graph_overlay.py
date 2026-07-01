"""Transcript overlay and bottleneck detection for curriculum graph."""

from __future__ import annotations

from typing import Any

from app.planning.academic_risk_analyzer import normalize_course_id
from app.planning.prerequisite_resolver import canonical_course_number
from app.services.course_reference_keys import merge_with_cross_track_equivalence_groups
from app.services.grade_evaluation import is_passing_grade
from app.services.graduation_progress_calculator import pick_latest_records_by_course_id


def _register_number(numbers: set[str], raw: str | None) -> None:
    if not raw:
        return
    value = str(raw)
    numbers.add(value)
    canonical = canonical_course_number(value)
    if canonical:
        numbers.add(canonical)


def _completed_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in pick_latest_records_by_course_id(completed_records).values():
        number = record.get("courseNumber")
        if number and is_passing_grade(record):
            _register_number(numbers, str(number))
    return numbers


def _failed_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in pick_latest_records_by_course_id(completed_records).values():
        number = record.get("courseNumber")
        if number and not is_passing_grade(record):
            _register_number(numbers, str(number))
    return numbers


def _in_progress_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in completed_records:
        if record.get("inProgress"):
            number = record.get("courseNumber")
            if number:
                _register_number(numbers, str(number))
    return numbers


def _canonical_or_raw(raw: str) -> str:
    return canonical_course_number(raw) or raw


def build_equivalence_groups(nodes: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Map each course number to its full parallel/alternative equivalence set."""
    groups: dict[str, set[str]] = {}

    def merge_members(members: list[str]) -> set[str]:
        merged: set[str] = set()
        for member in members:
            canonical = _canonical_or_raw(member)
            merged.add(canonical)
            merged.add(member)
            if canonical in groups:
                merged |= groups[canonical]
            if member in groups:
                merged |= groups[member]
        for key in list(merged):
            groups[key] = merged
        return merged

    for node in nodes:
        primary = str(node.get("courseNumber") or "")
        if not primary:
            continue
        members = [primary, *(str(alt) for alt in node.get("alternatives") or [])]
        merge_members(members)

    node_groups = [set(group) for group in groups.values()]
    merged = merge_with_cross_track_equivalence_groups(node_groups)
    merged_groups: dict[str, set[str]] = {}
    for group in merged:
        for key in group:
            merged_groups[key] = group
    return merged_groups


def equivalence_group(number: str, groups: dict[str, set[str]]) -> set[str]:
    canonical = _canonical_or_raw(number)
    return groups.get(canonical) or groups.get(number) or {canonical, number}


def expand_with_equivalence(numbers: set[str], groups: dict[str, set[str]]) -> set[str]:
    expanded = set(numbers)
    for number in numbers:
        expanded |= equivalence_group(number, groups)
    return expanded


def _prerequisite_satisfied(
    prereq: str,
    satisfied: set[str],
    groups: dict[str, set[str]],
) -> bool:
    return bool(expand_with_equivalence({prereq}, groups) & satisfied)


def _completed_via_alternative(
    *,
    primary: str,
    completed: set[str],
    groups: dict[str, set[str]],
) -> str | None:
    primary_keys = equivalence_group(primary, groups)
    passed = primary_keys & completed
    if not passed:
        return None

    primary_canonical = _canonical_or_raw(primary)
    if primary in passed or primary_canonical in passed:
        return None

    for candidate in sorted(passed):
        if candidate != primary and candidate != primary_canonical:
            return candidate
    return None


def overlay_transcript_on_graph(
    base_graph: dict[str, Any],
    completed_records: list[dict[str, Any]],
) -> dict[str, Any]:
    graph = {
        **base_graph,
        "nodes": [dict(node) for node in base_graph.get("nodes") or []],
        "edges": list(base_graph.get("edges") or []),
        "bottlenecks": [],
    }

    completed = _completed_numbers(completed_records)
    failed = _failed_numbers(completed_records)
    in_progress = _in_progress_numbers(completed_records)
    equivalence_groups = build_equivalence_groups(graph["nodes"])
    satisfied = expand_with_equivalence(completed, equivalence_groups)

    nodes_by_id = {node["nodeId"]: node for node in graph["nodes"]}
    nodes_by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    bottlenecks: list[dict[str, Any]] = []

    for node in graph["nodes"]:
        number = node["courseNumber"]
        group = equivalence_group(number, equivalence_groups)
        passed_in_group = group & completed

        missing_prereqs: list[str] = []
        for prereq in node.get("prerequisiteNumbers") or []:
            if not _prerequisite_satisfied(prereq, satisfied, equivalence_groups):
                missing_prereqs.append(prereq)

        if passed_in_group:
            status = "completed"
        elif group & failed and not passed_in_group:
            status = "failed"
        elif group & in_progress and not passed_in_group:
            status = "in_progress"
        elif missing_prereqs:
            status = "blocked"
        elif node.get("dataQuality", {}).get("verifyWithRegistrar"):
            status = "verify_with_registrar"
        else:
            status = "available"

        node["status"] = status
        node["missingPrerequisites"] = missing_prereqs
        node["isBottleneck"] = False
        satisfied_via = _completed_via_alternative(
            primary=number,
            completed=completed,
            groups=equivalence_groups,
        )
        if satisfied_via:
            node["satisfiedViaAlternative"] = satisfied_via
        else:
            node.pop("satisfiedViaAlternative", None)

        if status == "blocked" and missing_prereqs:
            bottlenecks.append(
                {
                    "courseNumber": number,
                    "blockedBy": missing_prereqs,
                    "reason": "prerequisite",
                }
            )
            node["isBottleneck"] = True

    for edge in graph["edges"]:
        source = edge.get("from")
        target = edge.get("to")
        source_node = nodes_by_id.get(source) or nodes_by_number.get(source or "")
        target_node = nodes_by_id.get(target) or nodes_by_number.get(target or "")
        if source_node is None or target_node is None:
            continue
        source_number = source_node["courseNumber"]
        if expand_with_equivalence({source_number}, equivalence_groups) & satisfied:
            if target_node.get("status") == "blocked":
                edge["highlight"] = "bottleneck"

    graph["bottlenecks"] = bottlenecks
    graph["transcriptSummary"] = {
        "completedCount": len(completed),
        "failedCount": len(failed),
        "inProgressCount": len(in_progress),
    }
    return graph


def enrich_completed_records(
    completed_documents: list[dict[str, Any]],
    courses_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for document in completed_documents:
        course_id = normalize_course_id(document.get("courseId"))
        course = courses_by_id.get(course_id)
        number = None
        if course:
            number = course.get("courseNumber") or course.get("number")
        enriched.append(
            {
                **document,
                "courseNumber": str(number) if number else None,
                "inProgress": document.get("status") == "in_progress",
            }
        )
    return enriched
