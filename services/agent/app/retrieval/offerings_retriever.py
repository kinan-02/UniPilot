"""Structured course offerings retriever (Mongo + optional JSON)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.planning.prerequisite_resolver import canonical_course_number
from app.planning.semester_codes import offering_keys_to_plan_semester_code, plan_semester_to_offering_keys
from app.repositories import catalog_repository
from app.retrieval.provenance import provenance_claim


def _offering_source_id(*, semester_code: str, course_number: str) -> str:
    return f"offering:{semester_code}:{course_number}"


async def retrieve_offerings_context(
    database: AsyncIOMotorDatabase,
    *,
    queries: list[str | dict[str, Any]],
    entities: dict[str, Any],
    settings: Settings | None = None,
) -> tuple[dict[str, Any], list[Any]]:
    cfg = settings or get_settings()
    academic: dict[str, Any] = {}
    provenance: list[Any] = []

    for query in queries:
        if isinstance(query, dict):
            semester = str(query.get("semester") or entities.get("targetSemesterCode") or "")
            course_number = canonical_course_number(
                str(query.get("courseNumber") or entities.get("courseNumber") or "")
            )
        else:
            semester = str(entities.get("targetSemesterCode") or "")
            course_number = canonical_course_number(str(entities.get("courseNumber") or ""))

        if not course_number:
            continue

        keys = plan_semester_to_offering_keys(semester) if semester else None
        offerings: list[dict[str, Any]] = []
        if keys:
            academic_year, semester_code = keys
            best = await catalog_repository.list_best_offerings_for_courses(
                database,
                [course_number],
                academic_year=academic_year,
                semester_code=semester_code,
            )
            offering = best.get(course_number)
            if offering:
                offerings = [offering]
                plan_code = semester or offering_keys_to_plan_semester_code(
                    int(offering.get("academicYear") or academic_year),
                    int(offering.get("semesterCode") or semester_code),
                ) or f"{academic_year}-{semester_code}"
                provenance.append(
                    provenance_claim(
                        claim=f"Course {course_number} offering found for {semester}",
                        source_type="course_offering_mongo",
                        source_id=_offering_source_id(
                            semester_code=plan_code,
                            course_number=course_number,
                        ),
                        retrieval_method="exact_lookup",
                        field_path="academicContext.offering",
                    )
                )
        else:
            offerings = await catalog_repository.list_offerings_for_course(database, course_number)
            if offerings:
                provenance.append(
                    provenance_claim(
                        claim=f"Loaded offerings for course {course_number}",
                        source_type="course_offering_mongo",
                        source_id=course_number,
                        retrieval_method="exact_lookup",
                        field_path="academicContext.offering",
                    )
                )

        if not offerings:
            json_offering = _lookup_offering_json(
                course_number=course_number,
                semester_code=semester,
                settings=cfg,
            )
            if json_offering:
                offerings = [json_offering]
                plan_code = semester or offering_keys_to_plan_semester_code(
                    int(json_offering.get("academicYear") or 0),
                    int(json_offering.get("semesterCode") or 0),
                ) or semester or course_number
                provenance.append(
                    provenance_claim(
                        claim=f"Course {course_number} offering loaded from JSON for {semester or 'any'}",
                        source_type="course_offering_json",
                        source_id=_offering_source_id(
                            semester_code=str(plan_code),
                            course_number=course_number,
                        ),
                        retrieval_method="exact_lookup",
                        field_path="academicContext.offering",
                    )
                )

        if offerings:
            academic["offering"] = offerings[0]
            academic["offerings"] = offerings
        else:
            academic.setdefault("offering", None)

    return academic, provenance


def _lookup_offering_json(
    *,
    course_number: str,
    semester_code: str,
    settings: Settings,
) -> dict[str, Any] | None:
    raw_dir = settings.technion_raw_dir
    if not raw_dir:
        return None

    keys = plan_semester_to_offering_keys(semester_code) if semester_code else None
    if not keys:
        return None

    academic_year, term_code = keys
    filename = f"courses_{academic_year}_{term_code}.json"
    path = Path(raw_dir) / filename
    if not path.is_file():
        return None

    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    courses = payload.get("courses") if isinstance(payload, dict) else payload
    if not isinstance(courses, list):
        return None

    for entry in courses:
        if not isinstance(entry, dict):
            continue
        number = canonical_course_number(str(entry.get("course_number") or entry.get("number") or ""))
        if number == course_number:
            return {
                "courseNumber": course_number,
                "academicYear": academic_year,
                "semesterCode": term_code,
                "source": "technion_json",
                "raw": entry,
            }
    return None
