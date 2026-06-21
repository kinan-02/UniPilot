"""Read-only catalog routes (Phase 13 — production DDS data)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.mongo import get_database
from app.dependencies.auth import AuthContext, require_auth
from app.repositories import catalog_repository
from app.schemas.catalog import (
    COURSE_NUMBER_PATTERN,
    PROGRAM_CODE_PATTERN,
    AdvisoryCatalogRule,
    CatalogSummary,
    CourseDetail,
    CourseListQuery,
    CourseOffering,
    CourseSummary,
    DegreeProgram,
    DegreeRequirement,
    PaginatedCourseResponse,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

COURSE_NUMBER_RE = re.compile(COURSE_NUMBER_PATTERN)
PROGRAM_CODE_RE = re.compile(PROGRAM_CODE_PATTERN)


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def validate_course_number_param(course_number: str) -> str:
    if not COURSE_NUMBER_RE.fullmatch(course_number):
        raise HTTPException(status_code=400, detail="course_number must be an 8-digit Technion course number")
    return course_number


def validate_program_code_param(program_code: str) -> str:
    if not PROGRAM_CODE_RE.fullmatch(program_code):
        raise HTTPException(
            status_code=400,
            detail="program_code must match Technion DDS format, e.g. 009216-1-000",
        )
    return program_code


@router.get("/courses")
async def list_catalog_courses(
    q: str | None = Query(default=None, max_length=200),
    faculty: str | None = Query(default=None, max_length=200),
    courseNumber: str | None = Query(default=None, max_length=8),
    academicYear: int | None = Query(default=None, ge=1990, le=2100),
    semesterCode: int | None = Query(default=None),
    minCredits: float | None = Query(default=None, ge=0),
    maxCredits: float | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    includeOfferings: bool = Query(default=False),
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    try:
        query = CourseListQuery(
            q=q,
            faculty=faculty,
            courseNumber=courseNumber,
            academicYear=academicYear,
            semesterCode=semesterCode,
            minCredits=minCredits,
            maxCredits=maxCredits,
            limit=limit,
            offset=offset,
            includeOfferings=includeOfferings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database = await get_database()
    items, total = await catalog_repository.list_courses(
        database,
        q=query.q,
        faculty=query.faculty,
        course_number=query.courseNumber,
        academic_year=query.academicYear,
        semester_code=query.semesterCode,
        min_credits=query.minCredits,
        max_credits=query.maxCredits,
        limit=query.limit,
        offset=query.offset,
    )

    summaries = [CourseSummary.model_validate(item) for item in items]
    if query.includeOfferings:
        detailed_items: list[CourseDetail] = []
        for summary in summaries:
            offerings = await catalog_repository.list_offerings_for_course(
                database,
                summary.courseNumber,
            )
            detail = CourseDetail(
                **summary.model_dump(),
                offerings=[CourseOffering.model_validate(o) for o in offerings],
            )
            detailed_items.append(detail)
        return success_response(
            {
                "items": [item.model_dump() for item in detailed_items],
                "total": total,
                "limit": query.limit,
                "offset": query.offset,
            }
        )

    return success_response(
        PaginatedCourseResponse(
            items=summaries,
            total=total,
            limit=query.limit,
            offset=query.offset,
        ).model_dump()
    )


@router.get("/courses/{course_number}")
async def get_catalog_course(
    course_number: str,
    includeOfferings: bool = Query(default=False),
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_course_number_param(course_number)
    database = await get_database()
    course = await catalog_repository.get_course_by_number(database, course_number)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    detail = CourseDetail.model_validate(course)
    if includeOfferings:
        offerings = await catalog_repository.list_offerings_for_course(database, course_number)
        detail = detail.model_copy(
            update={"offerings": [CourseOffering.model_validate(o) for o in offerings]}
        )
    return success_response({"course": detail.model_dump()})


@router.get("/courses/{course_number}/offerings")
async def get_catalog_course_offerings(
    course_number: str,
    academicYear: int | None = Query(default=None, ge=1990, le=2100),
    semesterCode: int | None = Query(default=None),
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_course_number_param(course_number)
    if semesterCode is not None and semesterCode not in {200, 201, 202}:
        raise HTTPException(status_code=400, detail="semesterCode must be one of 200, 201, 202")

    database = await get_database()
    course = await catalog_repository.get_course_by_number(database, course_number)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    offerings = await catalog_repository.list_offerings_for_course(
        database,
        course_number,
        academic_year=academicYear,
        semester_code=semesterCode,
    )
    return success_response(
        {
            "courseNumber": course_number,
            "offerings": [CourseOffering.model_validate(item).model_dump() for item in offerings],
            "total": len(offerings),
        }
    )


@router.get("/degree-programs")
async def list_catalog_degree_programs(
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    programs = await catalog_repository.list_degree_programs(database)
    return success_response(
        {
            "items": [DegreeProgram.model_validate(item).model_dump() for item in programs],
            "total": len(programs),
        }
    )


@router.get("/degree-programs/{program_code}")
async def get_catalog_degree_program(
    program_code: str,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_program_code_param(program_code)
    database = await get_database()
    program = await catalog_repository.get_degree_program_by_code(database, program_code)
    if not program:
        raise HTTPException(status_code=404, detail="Degree program not found")
    return success_response({"program": DegreeProgram.model_validate(program).model_dump()})


@router.get("/degree-programs/{program_code}/requirements")
async def get_catalog_hard_requirements(
    program_code: str,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_program_code_param(program_code)
    database = await get_database()
    program = await catalog_repository.get_degree_program_by_code(database, program_code)
    if not program:
        raise HTTPException(status_code=404, detail="Degree program not found")

    requirements = await catalog_repository.list_hard_requirements_for_program(
        database,
        program_code,
    )
    return success_response(
        {
            "programCode": program_code,
            "catalogYear": program.get("catalogYear"),
            "catalogVersion": program.get("catalogVersion"),
            "requirements": [
                DegreeRequirement.model_validate(item).model_dump() for item in requirements
            ],
            "total": len(requirements),
            "note": "Hard executable requirements only — advisory catalog rules are excluded.",
        }
    )


@router.get("/degree-programs/{program_code}/advisory-rules")
async def get_catalog_advisory_rules(
    program_code: str,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_program_code_param(program_code)
    database = await get_database()
    program = await catalog_repository.get_degree_program_by_code(database, program_code)
    if not program:
        raise HTTPException(status_code=404, detail="Degree program not found")

    rules = await catalog_repository.list_advisory_rules_for_program(database, program_code)
    return success_response(
        {
            "programCode": program_code,
            "catalogYear": program.get("catalogYear"),
            "catalogVersion": program.get("catalogVersion"),
            "advisoryRules": [
                AdvisoryCatalogRule.model_validate(item).model_dump() for item in rules
            ],
            "total": len(rules),
            "note": (
                "Advisory/manual-review metadata only — not auto-enforced in graduation progress."
            ),
        }
    )


@router.get("/degree-programs/{program_code}/catalog-summary")
async def get_catalog_degree_summary(
    program_code: str,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_program_code_param(program_code)
    database = await get_database()
    program = await catalog_repository.get_degree_program_by_code(database, program_code)
    if not program:
        raise HTTPException(status_code=404, detail="Degree program not found")

    hard_requirements = await catalog_repository.list_hard_requirements_for_program(
        database,
        program_code,
    )
    advisory_rules = await catalog_repository.list_advisory_rules_for_program(
        database,
        program_code,
    )
    summary = CatalogSummary(
        program=DegreeProgram.model_validate(program),
        hardRequirements=[DegreeRequirement.model_validate(item) for item in hard_requirements],
        advisoryRules=[AdvisoryCatalogRule.model_validate(item) for item in advisory_rules],
        counts={
            "hardRequirements": len(hard_requirements),
            "advisoryRules": len(advisory_rules),
        },
    )
    return success_response({"catalogSummary": summary.model_dump()})
