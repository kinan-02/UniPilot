"""Structured catalog retriever for agent context."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.internal_api_client import fetch_course_requirement_contribution
from app.planning.prerequisite_helpers import describe_missing_prerequisites, normalize_course_id
from app.planning.prerequisite_resolver import canonical_course_number
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.retrieval.provenance import provenance_claim
from app.services.academic_lookup_service import course_prerequisites
from app.services.degree_program_resolver import resolve_degree_program_for_profile
from app.repositories.student_profile_repository import find_student_profile_by_user_id


async def retrieve_catalog_context(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    queries: list[str | dict[str, Any]],
    entities: dict[str, Any],
    user_context: dict[str, Any],
) -> tuple[dict[str, Any], list[Any]]:
    academic: dict[str, Any] = {}
    provenance: list[Any] = []
    query_keys = {str(item) if isinstance(item, str) else str(item.get("type") or "") for item in queries}

    course_number = canonical_course_number(str(entities.get("courseNumber") or ""))

    if course_number and ("course_record" in query_keys or "course" in query_keys):
        course = await catalog_repository.get_course_by_number(database, course_number)
        if course:
            academic["course"] = course
            provenance.append(
                provenance_claim(
                    claim=f"Loaded catalog record for course {course_number}",
                    source_type="catalog",
                    source_id=f"course:{course_number}",
                    retrieval_method="exact_lookup",
                    field_path="academicContext.course",
                )
            )
        else:
            academic["course"] = None

    need_requirements = bool(
        query_keys & {"degree_requirements", "requirement_contribution", "catalog"}
    )
    if need_requirements:
        profile = await find_student_profile_by_user_id(database, user_id)
        program = await resolve_degree_program_for_profile(database, profile) if profile else None
        if program:
            program_code = str(program.get("programCode") or "")
            requirements = await catalog_repository.list_hard_requirements_for_program(
                database,
                program_code,
            )
            academic["degreeRequirements"] = requirements
            academic["degreeProgram"] = {
                "programCode": program_code,
                "name": program.get("name"),
                "catalogYear": program.get("catalogYear"),
            }
            provenance.append(
                provenance_claim(
                    claim=f"Loaded {len(requirements)} degree requirement rule(s)",
                    source_type="catalog",
                    source_id=f"degree_requirements:{program_code}",
                    retrieval_method="exact_lookup",
                    field_path="academicContext.degreeRequirements",
                )
            )

    if course_number and academic.get("course") and "prerequisiteResult" in query_keys:
        completed_ids = {
            normalize_course_id(str(record_id))
            for record_id in (user_context.get("completedCourseIds") or [])
            if record_id is not None
        }
        completed_numbers = {
            canonical_course_number(str(number))
            for number in (user_context.get("completedCourses") or [])
            if str(number).strip()
        }
        if not completed_ids and not completed_numbers:
            records = await find_all_completed_courses_by_user_id(database, user_id)
            completed_ids = {
                normalize_course_id(str(record.get("courseId")))
                for record in records
                if record.get("courseId") is not None
            }
            completed_ids.discard("")

        satisfied_ids = set(completed_ids) | set(completed_numbers)

        course = academic["course"]
        course_id = str(course.get("id") or "")
        catalog_course = await catalog_repository.find_course_by_id(database, course_id) if course_id else None
        if catalog_course:
            prerequisite_ids = [
                normalize_course_id(course_id_value)
                for course_id_value in (catalog_course.get("prerequisites") or [])
            ]
            if not prerequisite_ids:
                prerequisite_ids = [
                    canonical_course_number(str(item.get("courseNumber") or ""))
                    for item in course_prerequisites(course_number)
                    if str(item.get("courseNumber") or "").strip()
                ]

            courses_by_id: dict[str, dict[str, Any]] = {}
            for prereq_id in prerequisite_ids:
                lookup = await catalog_repository.get_course_by_number(database, prereq_id)
                if lookup:
                    courses_by_id[normalize_course_id(str(lookup.get("id") or prereq_id))] = {
                        **lookup,
                        "number": lookup.get("courseNumber"),
                        "title": lookup.get("title"),
                    }
                else:
                    courses_by_id[normalize_course_id(prereq_id)] = {
                        "number": prereq_id,
                        "courseNumber": prereq_id,
                    }

            catalog_key = normalize_course_id(str(catalog_course.get("_id") or course_id))
            courses_by_id.setdefault(
                catalog_key,
                {
                    **catalog_course,
                    "number": catalog_course.get("courseNumber"),
                    "title": catalog_course.get("title"),
                },
            )

            prereq = describe_missing_prerequisites(
                {
                    **catalog_course,
                    "number": catalog_course.get("courseNumber"),
                    "title": catalog_course.get("title"),
                    "prerequisites": prerequisite_ids,
                },
                satisfied_ids,
                courses_by_id,
            )
            has_required_prereqs = bool(prerequisite_ids)
            academic["prerequisiteResult"] = {
                **prereq,
                "eligible": not has_required_prereqs or len(prereq.get("missingPrerequisiteIds") or []) == 0,
            }
            provenance.append(
                provenance_claim(
                    claim=f"Validated prerequisites for course {course_number}",
                    source_type="catalog",
                    source_id=f"prerequisites:{course_number}",
                    retrieval_method="exact_lookup",
                    field_path="academicContext.prerequisiteResult",
                )
            )

    if (
        course_number
        and academic.get("course")
        and "requirement_contribution" in query_keys
    ):
        program = academic.get("degreeProgram")
        program_code = str((program or {}).get("programCode") or "")
        if not program_code:
            profile = await find_student_profile_by_user_id(database, user_id)
            resolved_program = await resolve_degree_program_for_profile(database, profile) if profile else None
            program_code = str((resolved_program or {}).get("programCode") or "")

        if program_code:
            contribution_response = await fetch_course_requirement_contribution(
                program_code=program_code,
                course_number=course_number,
            )
            academic["requirementContribution"] = contribution_response.get("contribution")
            provenance.append(
                provenance_claim(
                    claim=f"Checked requirement contribution for course {course_number}",
                    source_type="catalog",
                    source_id=f"requirement_contribution:{course_number}",
                    retrieval_method="exact_lookup",
                    field_path="academicContext.requirementContribution",
                )
            )

    return academic, provenance
