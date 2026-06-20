"""Semester plan routes (Phase 16)."""

from __future__ import annotations

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
)
from app.schemas.semester_plan import (
    CreateManualSemesterPlanRequest,
    CreateSemesterPlanVersionRequest,
    GenerateSemesterPlanRequest,
    OBJECT_ID_PATTERN,
    UpdateSemesterPlanRequest,
)
from app.services.manual_semester_plan_service import (
    archive_semester_plan_by_user,
    create_manual_semester_plan,
    create_semester_plan_version_by_user,
    update_semester_plan_by_user,
)
from app.services.semester_plan_service import generate_and_store_semester_plan

router = APIRouter(prefix="/semester-plans", tags=["semester-plans"])

_semester_plan_indexes_ready = False

LIST_QUERY_ALLOWED = frozenset({"page", "limit"})


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
        {"semesterPlan": to_public_semester_plan(result["plan"])}
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
        {"semesterPlan": to_public_semester_plan(result["plan"])}
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

    return success_response({"semesterPlan": to_public_semester_plan(plan)})


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
            "semesterPlan": to_public_semester_plan(result["plan"]),
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
        {"semesterPlan": to_public_semester_plan(result["plan"])}
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
        {"semesterPlan": to_public_semester_plan(result["plan"])}
    )
