"""Determine how a course contributes to degree requirements (spec §30.2 step 9)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories import catalog_repository
from app.services.course_pool_classification import resolve_claiming_pool
from app.services.course_reference_keys import (
    build_mandatory_equivalence_groups,
    is_mandatory_curriculum_course,
)
from app.services.graduation_progress_calculator import is_course_eligible_for_pools
from app.services.matrix_semester_filters import filter_executable_matrix_documents


async def evaluate_requirement_contribution(
    database: AsyncIOMotorDatabase,
    *,
    course_number: str,
    program_code: str,
) -> dict[str, Any]:
    pools = await catalog_repository.list_course_pools_for_program(database, program_code)
    matrix_documents = await catalog_repository.list_semester_matrix_rules_for_program(
        database,
        program_code,
    )
    executable_matrix = filter_executable_matrix_documents(matrix_documents)
    mandatory_groups = build_mandatory_equivalence_groups(executable_matrix)

    eligible_pools: list[dict[str, Any]] = []
    for pool in pools:
        if is_course_eligible_for_pools(
            course_number,
            [pool],
            program_code=program_code,
        ):
            eligible_pools.append(
                {
                    "requirementGroupId": pool.get("requirementGroupId"),
                    "title": pool.get("title"),
                    "ruleType": (pool.get("ruleExpression") or {}).get("type"),
                }
            )

    claiming_pool = resolve_claiming_pool(
        course_number,
        pools,
        program_code=program_code,
    )
    is_mandatory = is_mandatory_curriculum_course(course_number, mandatory_groups)

    referenced_pools: list[str] = []
    for pool in pools:
        for reference in pool.get("courseReferences") or []:
            if str(reference.get("courseNumber") or "") == course_number:
                title = pool.get("title")
                if title:
                    referenced_pools.append(str(title))

    counts = bool(eligible_pools or referenced_pools or is_mandatory or claiming_pool)
    summary = _build_summary(
        course_number=course_number,
        counts=counts,
        is_mandatory=is_mandatory,
        eligible_pools=eligible_pools,
        referenced_pools=referenced_pools,
        claiming_pool=claiming_pool,
    )

    return {
        "countsTowardDegree": counts,
        "isMandatoryCurriculum": is_mandatory,
        "eligiblePools": eligible_pools,
        "referencedInPools": referenced_pools,
        "claimingPool": (
            {
                "requirementGroupId": claiming_pool.get("requirementGroupId"),
                "title": claiming_pool.get("title"),
            }
            if claiming_pool
            else None
        ),
        "summary": summary,
        "status": "matched" if counts else "no_match",
    }


def _build_summary(
    *,
    course_number: str,
    counts: bool,
    is_mandatory: bool,
    eligible_pools: list[dict[str, Any]],
    referenced_pools: list[str],
    claiming_pool: dict[str, Any] | None,
) -> str:
    if is_mandatory:
        return f"Course {course_number} is part of the mandatory curriculum matrix."
    if claiming_pool and claiming_pool.get("title"):
        return f"Course {course_number} can count toward: {claiming_pool['title']}."
    if eligible_pools:
        titles = [str(pool.get("title") or pool.get("requirementGroupId")) for pool in eligible_pools[:3]]
        return f"Course {course_number} is eligible for: {', '.join(titles)}."
    if referenced_pools:
        return f"Course {course_number} is listed in: {', '.join(referenced_pools[:3])}."
    if not counts:
        return f"Course {course_number} was not matched to a known requirement pool for your program."
    return f"Course {course_number} may contribute to your degree requirements."
