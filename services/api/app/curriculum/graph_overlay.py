"""Transcript overlay and bottleneck detection for curriculum graph."""

from __future__ import annotations

from typing import Any

from app.planning.academic_risk_analyzer import normalize_course_id
from app.services.grade_evaluation import is_passing_grade


def _completed_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in completed_records:
        number = record.get("courseNumber")
        if number and is_passing_grade(record):
            numbers.add(str(number))
    return numbers


def _failed_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in completed_records:
        number = record.get("courseNumber")
        if number and not is_passing_grade(record):
            numbers.add(str(number))
    return numbers


def _in_progress_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in completed_records:
        if record.get("inProgress"):
            number = record.get("courseNumber")
            if number:
                numbers.add(str(number))
    return numbers


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
    satisfied = set(completed)

    nodes_by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    bottlenecks: list[dict[str, Any]] = []

    for node in graph["nodes"]:
        number = node["courseNumber"]
        missing_prereqs: list[str] = []
        for prereq in node.get("prerequisiteNumbers") or []:
            if prereq not in satisfied:
                missing_prereqs.append(prereq)

        if number in completed:
            status = "completed"
        elif number in failed:
            status = "failed"
        elif number in in_progress:
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
        if source in satisfied and target in nodes_by_number:
            target_node = nodes_by_number[target]
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
