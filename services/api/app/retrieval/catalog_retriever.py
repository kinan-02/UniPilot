"""Structured catalog retriever for agent context."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.prerequisite_resolver import canonical_course_number
from app.planning.semester_planner import describe_missing_prerequisites, normalize_course_id
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.retrieval.provenance import provenance_claim
from app.services.degree_program_resolver import resolve_degree_program_for_profile
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.requirement_contribution_service import evaluate_requirement_contribution


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
        completed_ids = set(user_context.get("completedCourseIds") or [])
        if not completed_ids:
            records = await find_all_completed_courses_by_user_id(database, user_id)
            completed_ids = {
                normalize_course_id(str(record.get("courseId")))
                for record in records
                if record.get("courseId") is not None
            }
            completed_ids.discard("")

        course = academic["course"]
        course_id = str(course.get("id") or "")
        catalog_course = await catalog_repository.find_course_by_id(database, course_id) if course_id else None
        if catalog_course:
            courses_by_id = {normalize_course_id(str(catalog_course.get("_id"))): catalog_course}
            prereq = describe_missing_prerequisites(
                {
                    **catalog_course,
                    "number": catalog_course.get("courseNumber"),
                    "title": catalog_course.get("title"),
                },
                completed_ids,
                courses_by_id,
            )
            academic["prerequisiteResult"] = {
                **prereq,
                "eligible": len(prereq.get("missingPrerequisiteIds") or []) == 0,
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
            contribution = await evaluate_requirement_contribution(
                database,
                course_number=course_number,
                program_code=program_code,
            )
            academic["requirementContribution"] = contribution
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
