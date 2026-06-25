"""Semester plan routes (Phase 16)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.repositories.semester_plan_repository import (
    ensure_semester_plan_indexes,
    find_semester_plan_by_id_and_user_id,
    find_semester_plans_by_user_id,
    to_public_semester_plan,
    to_public_semester_plan_summary,
    to_public_shared_semester_plan,
)
from app.services.planner_enrichment_service import resolve_public_plan_insights
from app.schemas.semester_plan import (
    CreateManualSemesterPlanRequest,
    CreateSemesterPlanVersionRequest,
    GenerateSemesterPlanRequest,
    OBJECT_ID_PATTERN,
    PatchLessonSelectionRequest,
    PatchMaybeCoursesRequest,
    PatchPlannedCourseRequest,
    ReorderPlannedCoursesRequest,
    SuggestSemesterCoursesForPlannerRequest,
    SuggestSemesterScheduleRequest,
    UpdateSemesterPlanRequest,
    UpdateSemesterPlanShareRequest,
)
from app.services.manual_semester_plan_service import (
    archive_semester_plan_by_user,
    create_manual_semester_plan,
    create_semester_plan_version_by_user,
    get_shared_semester_plan_by_token,
    patch_lesson_selection_by_user,
    patch_maybe_courses_by_user,
    patch_maybe_lesson_selection_by_user,
    patch_planned_course_by_user,
    reorder_planned_courses_by_user,
    update_semester_plan_by_user,
    update_semester_plan_share_by_user,
)
from app.services.semester_plan_service import generate_and_store_semester_plan
from app.services.semester_plan_suggestion_service import (
    suggest_semester_courses,
    suggest_semester_schedule,
)

router = APIRouter(prefix="/semester-plans", tags=["semester-plans"])

_semester_plan_indexes_ready = False

LIST_QUERY_ALLOWED = frozenset({"page", "limit"})
COURSE_NUMBER_RE = re.compile(r"^0\d{7}$")
SHARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def reset_semester_plan_indexes_state() -> None:
    global _semester_plan_indexes_ready
    _semester_plan_indexes_ready = False


async def _ensure_semester_plan_indexes_once() -> None:
    global _semester_plan_indexes_ready

    if _semester_plan_indexes_ready:
        return

    database = await get_database()
    await ensure_semester_plan_indexes(database)
    _semester_plan_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


async def _public_plan_with_insights(
    database,
    user_id: str,
    plan: dict[str, Any],
    *,
    recompute: bool = False,
    persist_snapshot: bool = False,
) -> dict[str, Any]:
    enriched = await resolve_public_plan_insights(
        database,
        user_id,
        plan,
        recompute=recompute,
        persist_snapshot=persist_snapshot,
    )
    public = to_public_semester_plan(enriched)
    if public is None:
        return {}
    insights = enriched.get("plannerInsights")
    if insights:
        public["plannerInsights"] = insights
    return public


def _handle_planning_context_error(result: dict[str, Any]) -> None:
    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")

    if result["status"] == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail=(
                "A degree must be selected on the student profile before "
                "generating a semester plan"
            ),
        )

    if result["status"] == "degree_not_found":
        raise HTTPException(
            status_code=400,
            detail="Referenced degree was not found in the catalog",
        )


def _handle_manual_plan_result(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if status == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if status == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail=(
                "A degree must be selected on the student profile before "
                "generating a semester plan"
            ),
        )
    if status == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Semester plan not found")
    if status == "archived":
        raise HTTPException(status_code=400, detail="Archived semester plans cannot be updated")
    if status == "archived_source":
        raise HTTPException(
            status_code=400,
            detail="Cannot create a new version from an archived semester plan",
        )
    if status == "validation_error":
        errors = result.get("errors") or ["Invalid semester plan payload"]
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return result


@router.post("", status_code=201)
async def create_manual_semester_plan_route(
    payload: CreateManualSemesterPlanRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_semester_plan_indexes_once()
    database = await get_database()

    result = _handle_manual_plan_result(
        await create_manual_semester_plan(
            database,
            auth.user_id,
            payload.model_dump(exclude_none=True),
        )
    )

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.post("/generate", status_code=201)
async def generate_semester_plan(
    payload: GenerateSemesterPlanRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_semester_plan_indexes_once()
    database = await get_database()

    result = await generate_and_store_semester_plan(
        database,
        auth.user_id,
        payload.model_dump(exclude_none=True),
    )
    _handle_planning_context_error(result)

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.post("/suggest-courses")
async def suggest_courses_for_planner(
    payload: SuggestSemesterCoursesForPlannerRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await suggest_semester_courses(
        database,
        auth.user_id,
        semester_code=payload.semesterCode,
        max_credits=payload.maxCredits,
        existing_planned_courses=[
            course.model_dump(exclude_none=True)
            for course in payload.existingPlannedCourses
        ],
    )
    _handle_planning_context_error(result)
    if result.get("status") == "validation_error":
        raise HTTPException(status_code=400, detail=result.get("errors") or ["Invalid request"])
    return success_response(
        {
            "plannedCourses": result["plannedCourses"],
            "explanation": result["explanation"],
        }
    )


@router.post("/suggest-schedule")
async def suggest_schedule_for_planner(
    payload: SuggestSemesterScheduleRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await suggest_semester_schedule(
        database,
        auth.user_id,
        semester_code=payload.semesterCode,
        planned_courses=[course.model_dump(exclude_none=True) for course in payload.plannedCourses],
    )
    _handle_planning_context_error(result)
    if result.get("status") == "validation_error":
        raise HTTPException(status_code=400, detail=result.get("errors") or ["Invalid request"])
    return success_response(
        {
            "selections": result["selections"],
            "skippedCourses": result["skippedCourses"],
            "examSummary": result["examSummary"],
        }
    )


@router.get("")
async def list_semester_plans(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    unknown = set(request.query_params.keys()) - LIST_QUERY_ALLOWED
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown query parameter(s): {', '.join(sorted(unknown))}",
        )

    database = await get_database()
    list_result = await find_semester_plans_by_user_id(
        database,
        auth.user_id,
        page=page,
        limit=limit,
    )

    return success_response(
        {
            "semesterPlans": [
                summary
                for plan in list_result["plans"]
                if (summary := to_public_semester_plan_summary(plan)) is not None
            ],
            "pagination": {
                "total": list_result["total"],
                "page": list_result["page"],
                "limit": list_result["limit"],
            },
        }
    )


def validate_plan_id_param(plan_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(plan_id):
        raise HTTPException(status_code=400, detail="Identifier must be a valid ObjectId")
    return plan_id


def validate_course_number_param(course_number: str) -> str:
    if not COURSE_NUMBER_RE.fullmatch(course_number):
        raise HTTPException(
            status_code=400,
            detail="course_number must be an 8-digit Technion course number",
        )
    return course_number


def validate_share_token_param(share_token: str) -> str:
    if not SHARE_TOKEN_RE.fullmatch(share_token):
        raise HTTPException(status_code=400, detail="Invalid share token")
    return share_token


@router.get("/shared/{share_token}")
async def get_shared_semester_plan(share_token: str) -> dict[str, Any]:
    validate_share_token_param(share_token)
    database = await get_database()
    result = await get_shared_semester_plan_by_token(database, share_token)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Shared semester plan not found")

    plan = result["plan"]
    user_id = str(plan.get("userId"))
    enriched = await resolve_public_plan_insights(
        database,
        user_id,
        plan,
        recompute=False,
        persist_snapshot=False,
    )
    public = to_public_shared_semester_plan(enriched)
    insights = enriched.get("plannerInsights")
    if insights and public is not None:
        public["plannerInsights"] = insights
    return success_response({"semesterPlan": public})


@router.get("/{plan_id}")
async def get_semester_plan(
    plan_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)

    database = await get_database()
    plan = await find_semester_plan_by_id_and_user_id(database, plan_id, auth.user_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Semester plan not found")

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, plan, recompute=False, persist_snapshot=False
            ),
        }
    )


@router.post("/{plan_id}/versions", status_code=201)
async def create_semester_plan_version(
    plan_id: str,
    payload: CreateSemesterPlanVersionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    await _ensure_semester_plan_indexes_once()
    database = await get_database()

    result = _handle_manual_plan_result(
        await create_semester_plan_version_by_user(
            database,
            auth.user_id,
            plan_id,
            name=payload.name,
        )
    )

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            ),
            "sourcePlanId": result.get("sourcePlanId"),
        }
    )


@router.put("/{plan_id}")
async def update_semester_plan(
    plan_id: str,
    payload: UpdateSemesterPlanRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    await _ensure_semester_plan_indexes_once()
    database = await get_database()

    result = _handle_manual_plan_result(
        await update_semester_plan_by_user(
            database,
            auth.user_id,
            plan_id,
            payload.model_dump(exclude_none=True),
        )
    )

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.patch("/{plan_id}/courses/{course_number}")
async def patch_planned_course(
    plan_id: str,
    course_number: str,
    payload: PatchPlannedCourseRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    validate_course_number_param(course_number)
    if payload.model_dump(exclude_none=True) == {}:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    database = await get_database()
    result = _handle_manual_plan_result(
        await patch_planned_course_by_user(
            database,
            auth.user_id,
            plan_id,
            course_number,
            payload.model_dump(exclude_none=True),
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.patch("/{plan_id}/courses/{course_number}/lesson-selection")
async def patch_lesson_selection(
    plan_id: str,
    course_number: str,
    payload: PatchLessonSelectionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    validate_course_number_param(course_number)
    database = await get_database()
    result = _handle_manual_plan_result(
        await patch_lesson_selection_by_user(
            database,
            auth.user_id,
            plan_id,
            course_number,
            payload.model_dump(),
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.patch("/{plan_id}/maybe-courses")
async def patch_maybe_courses(
    plan_id: str,
    payload: PatchMaybeCoursesRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    database = await get_database()
    result = _handle_manual_plan_result(
        await patch_maybe_courses_by_user(
            database,
            auth.user_id,
            plan_id,
            payload.model_dump(),
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=False, persist_snapshot=False
            )
        }
    )


@router.patch("/{plan_id}/maybe-courses/{course_number}/lesson-selection")
async def patch_maybe_lesson_selection(
    plan_id: str,
    course_number: str,
    payload: PatchLessonSelectionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    validate_course_number_param(course_number)
    database = await get_database()
    result = _handle_manual_plan_result(
        await patch_maybe_lesson_selection_by_user(
            database,
            auth.user_id,
            plan_id,
            course_number,
            payload.model_dump(),
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=False, persist_snapshot=False
            )
        }
    )


@router.put("/{plan_id}/courses/order")
async def reorder_planned_courses(
    plan_id: str,
    payload: ReorderPlannedCoursesRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    database = await get_database()
    result = _handle_manual_plan_result(
        await reorder_planned_courses_by_user(
            database,
            auth.user_id,
            plan_id,
            payload.courseIds,
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.patch("/{plan_id}/share")
async def update_semester_plan_share(
    plan_id: str,
    payload: UpdateSemesterPlanShareRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    database = await get_database()
    result = _handle_manual_plan_result(
        await update_semester_plan_share_by_user(
            database,
            auth.user_id,
            plan_id,
            share_enabled=payload.shareEnabled,
        )
    )
    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )


@router.delete("/{plan_id}")
async def archive_semester_plan(
    plan_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_plan_id_param(plan_id)
    database = await get_database()

    result = _handle_manual_plan_result(
        await archive_semester_plan_by_user(database, auth.user_id, plan_id)
    )

    return success_response(
        {
            "semesterPlan": await _public_plan_with_insights(
                database, auth.user_id, result["plan"], recompute=True, persist_snapshot=True
            )
        }
    )
