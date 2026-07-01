"""Build required-curriculum graph from semester_matrix catalog rules."""

from __future__ import annotations

from typing import Any

from app.curriculum.cross_track_equivalence import KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS

from app.curriculum.data_quality import (
    build_credits_display,
    build_data_quality_flags,
    parse_alternatives_from_text,
    parse_credits_range,
)
from app.curriculum.rule_dsl import parse_rule_expression, summarize_elective_bucket
from app.services.graduation_requirement_links import credit_bucket_id_for_pool
from app.planning.academic_risk_analyzer import normalize_course_id
from app.planning.prerequisite_resolver import (
    canonical_course_number,
    extract_course_numbers_from_text,
)


def _serialize_cross_track_equivalence_groups() -> list[list[str]]:
    return [list(group) for group in KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS]


def _serialize_catalog_overlap_equivalence_groups(
    catalog_courses: list[dict[str, Any]],
) -> list[list[str]]:
    from app.services.catalog_overlap_groups import build_catalog_overlap_groups

    return [sorted(group) for group in build_catalog_overlap_groups(catalog_courses)]


def _course_number(document: dict[str, Any]) -> str | None:
    raw = document.get("courseNumber") or document.get("number")
    if raw is None:
        return None
    return canonical_course_number(str(raw)) or str(raw)


def _prerequisite_sources(
    catalog_course: dict[str, Any] | None,
    course_ref: dict[str, Any] | None,
    courses_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Return prerequisite/corequisite sources with requirement typing for edge styling."""
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(number: str | None, *, requirement_type: str, kind: str) -> None:
        if not number:
            return
        key = (number, kind)
        if key in seen:
            return
        seen.add(key)
        sources.append(
            {
                "number": number,
                "requirementType": requirement_type,
                "kind": kind,
            }
        )

    if catalog_course:
        for prerequisite_id in catalog_course.get("prerequisites") or []:
            prerequisite_doc = courses_by_id.get(normalize_course_id(prerequisite_id))
            if prerequisite_doc:
                number = _course_number(prerequisite_doc)
                add(number, requirement_type="hard", kind="prerequisite")

        for number in extract_course_numbers_from_text(catalog_course.get("prerequisitesText")):
            if not any(
                item["number"] == number and item["kind"] == "prerequisite"
                for item in sources
            ):
                add(number, requirement_type="catalog_text", kind="prerequisite")

        for number in extract_course_numbers_from_text(catalog_course.get("corequisitesText")):
            add(number, requirement_type="corequisite", kind="corequisite")

    if course_ref:
        for number in extract_course_numbers_from_text(course_ref.get("prerequisitesText")):
            if not any(
                item["number"] == number and item["kind"] == "prerequisite"
                for item in sources
            ):
                add(number, requirement_type="catalog_text", kind="prerequisite")

    return sources


def _node_from_reference(
    *,
    course_number: str,
    course_ref: dict[str, Any],
    semester: int,
    catalog_course: dict[str, Any] | None,
) -> dict[str, Any]:
    notes = course_ref.get("notes") or []
    notes_text = " ".join(str(note) for note in notes)
    alternatives = list(course_ref.get("alternatives") or [])
    if not alternatives:
        alternatives = parse_alternatives_from_text(
            notes_text,
            course_ref.get("prerequisitesText"),
        )

    credits_range = course_ref.get("creditsRange")
    if credits_range is None:
        raw_credits = None
        for note in notes:
            parsed = parse_credits_range(str(note))
            if parsed:
                credits_range = parsed
                break
        if credits_range is None and course_ref.get("creditsHintRaw"):
            credits_range = parse_credits_range(str(course_ref.get("creditsHintRaw")))

    catalog_credits = catalog_course.get("credits") if catalog_course else None
    credits_hint = course_ref.get("creditsHint")
    credits_uncertain = credits_range is not None or (
        catalog_credits is None and credits_hint is None
    )
    credits = build_credits_display(
        credits=catalog_credits,
        credits_range=credits_range,
        credits_hint=credits_hint,
    )
    data_quality = build_data_quality_flags(
        course_ref=course_ref,
        catalog_course=catalog_course,
        alternatives=alternatives,
        credits_uncertain=credits_uncertain,
    )

    title = (
        (catalog_course or {}).get("title")
        or (catalog_course or {}).get("titleHebrew")
        or course_ref.get("titleHint")
        or course_number
    )

    return {
        "nodeId": course_number,
        "courseNumber": course_number,
        "title": title,
        "semester": semester,
        "credits": credits,
        "alternatives": alternatives,
        "dataQuality": data_quality,
        "prerequisiteNumbers": [],
        "status": "available",
        "missingPrerequisites": [],
        "isBottleneck": False,
    }


def build_base_curriculum_graph(
    *,
    track_slug: str,
    program_code: str,
    catalog_year: int,
    catalog_version: str,
    semester_matrix_documents: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    catalog_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    courses_by_number: dict[str, dict[str, Any]] = {}
    courses_by_id: dict[str, dict[str, Any]] = {}
    for course in catalog_courses:
        number = _course_number(course)
        if number:
            courses_by_number[number] = course
        courses_by_id[normalize_course_id(course["_id"])] = course

    sorted_matrices = sorted(
        semester_matrix_documents,
        key=lambda doc: int((doc.get("ruleExpression") or {}).get("semester") or 0),
    )

    nodes_by_number: dict[str, dict[str, Any]] = {}
    refs_by_number: dict[str, dict[str, Any]] = {}
    semester_lanes: list[dict[str, Any]] = []

    for matrix_doc in sorted_matrices:
        expression = matrix_doc.get("ruleExpression") or {}
        semester = int(expression.get("semester") or 0)
        lane_nodes: list[dict[str, Any]] = []

        for course_ref in matrix_doc.get("courseReferences") or []:
            course_number = canonical_course_number(course_ref.get("courseNumber"))
            if not course_number:
                continue
            catalog_course = courses_by_number.get(course_number)
            node = _node_from_reference(
                course_number=course_number,
                course_ref=course_ref,
                semester=semester,
                catalog_course=catalog_course,
            )
            if course_number in nodes_by_number:
                existing = nodes_by_number[course_number]
                if existing["semester"] > semester:
                    existing["semester"] = semester
            else:
                nodes_by_number[course_number] = node
                refs_by_number[course_number] = course_ref
                lane_nodes.append(node)

        if lane_nodes:
            semester_lanes.append(
                {
                    "semester": semester,
                    "title": matrix_doc.get("title") or f"Semester {semester}",
                    "nodeIds": [node["nodeId"] for node in lane_nodes],
                    "collapsedByDefault": semester > 4,
                    "rule": parse_rule_expression(expression),
                    "advisoryOnly": bool(matrix_doc.get("advisoryOnly", True)),
                }
            )

    edges: list[dict[str, Any]] = []
    curriculum_numbers = set(nodes_by_number.keys())

    for course_number, node in nodes_by_number.items():
        catalog_course = courses_by_number.get(course_number)
        course_ref = refs_by_number.get(course_number)
        prereq_sources = _prerequisite_sources(catalog_course, course_ref, courses_by_id)
        node["prerequisiteNumbers"] = [
            item["number"] for item in prereq_sources if item["kind"] == "prerequisite"
        ]

        for source in prereq_sources:
            prereq_number = source["number"]
            requirement_type = source["requirementType"]
            edge_kind = source["kind"]
            if edge_kind == "prerequisite" and prereq_number not in curriculum_numbers:
                requirement_type = "external"
                edge_kind = "external_prerequisite"
            edges.append(
                {
                    "from": prereq_number,
                    "to": course_number,
                    "kind": edge_kind,
                    "requirementType": requirement_type,
                }
            )

    elective_buckets = [
        summarize_elective_bucket(
            pool_doc,
            program_code=program_code,
            courses_by_number=courses_by_number,
            linked_credit_bucket_id=credit_bucket_id_for_pool(
                program_code=program_code,
                pool_document=pool_doc,
            ),
        )
        for pool_doc in pool_documents
        if (pool_doc.get("ruleExpression") or {}).get("type") != "semester_matrix"
    ]

    advisories = [
        {
            "code": "semester_matrix_planning_only",
            "severity": "info",
            "message": (
                "Recommended semester layout is advisory; confirm sequencing with your "
                "faculty advisor and the registrar."
            ),
        }
    ]

    return {
        "trackSlug": track_slug,
        "programCode": program_code,
        "catalogYear": catalog_year,
        "catalogVersion": catalog_version,
        "viewDefault": "semester_swimlanes",
        "semesterLanes": semester_lanes,
        "nodes": list(nodes_by_number.values()),
        "edges": edges,
        "electiveBuckets": elective_buckets,
        "crossTrackEquivalenceGroups": _serialize_cross_track_equivalence_groups(),
        "catalogOverlapEquivalenceGroups": _serialize_catalog_overlap_equivalence_groups(
            catalog_courses,
        ),
        "advisories": advisories,
        "bottlenecks": [],
    }
