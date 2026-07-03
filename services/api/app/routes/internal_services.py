"""Internal-only routes for trusted backend services (MAS, workers)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.mongo import get_database
from app.dependencies.internal_auth import require_internal_service_token
from app.services.academic_risk_service import preview_academic_risks_for_user
from app.services.graduation_progress_service import (
    get_graduation_progress_for_user,
    preview_graduation_progress_for_user,
)
from app.services.session_bootstrap_service import build_session_bootstrap_for_user
from app.services.semester_plan_suggestion_service import suggest_semester_courses
from app.services.student_user_context_service import build_student_user_context

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_service_token)],
)


def success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


class InternalGraduationProgressPreviewRequest(BaseModel):
    completed_course_numbers: list[str] | None = Field(default=None, max_length=200)
    additional_course_numbers: list[str] = Field(default_factory=list, max_length=24)


class InternalAcademicRiskPreviewRequest(BaseModel):
    course_numbers: list[str] = Field(min_length=1, max_length=24)
    semester_code: str = Field(min_length=1, max_length=32)
    max_credits: float | None = None
    min_credits: float | None = None


class InternalSemesterSuggestionRequest(BaseModel):
    semester_code: str = Field(min_length=1, max_length=32, alias="semesterCode")
    max_credits: float | None = Field(default=None, alias="maxCredits", gt=0, le=40)

    model_config = {"populate_by_name": True}


@router.get("/session-bootstrap/users/{user_id}")
async def internal_session_bootstrap_for_user(user_id: str) -> dict[str, Any]:
    """Return user context + graduation progress for MAS session start (single round trip)."""
    database = await get_database()
    return success_response(await build_session_bootstrap_for_user(database, user_id))


@router.get("/user-context/users/{user_id}")
async def internal_user_context_for_user(user_id: str) -> dict[str, Any]:
    """Return canonical student profile + transcript context (MAS session bootstrap)."""
    database = await get_database()
    return success_response({"userContext": await build_student_user_context(database, user_id)})


@router.get("/graduation-progress/users/{user_id}")
async def internal_graduation_progress_for_user(user_id: str) -> dict[str, Any]:
    """Return graduation progress for a user (MAS Progress Scout integration)."""
    database = await get_database()
    result = await get_graduation_progress_for_user(database, user_id)

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if result["status"] == "degree_not_selected":
        raise HTTPException(status_code=400, detail="Degree not selected on student profile")
    if result["status"] == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")

    return success_response({"graduationProgress": result["progress"]})


@router.post("/graduation-progress/preview/users/{user_id}")
async def internal_graduation_progress_preview_for_user(
    user_id: str,
    payload: InternalGraduationProgressPreviewRequest,
) -> dict[str, Any]:
    """Recompute graduation progress for hypothetical completions (MAS variant preview)."""
    database = await get_database()
    result = await preview_graduation_progress_for_user(
        database,
        user_id,
        completed_course_numbers=payload.completed_course_numbers,
        additional_course_numbers=payload.additional_course_numbers,
    )

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if result["status"] == "degree_not_selected":
        raise HTTPException(status_code=400, detail="Degree not selected on student profile")
    if result["status"] == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")

    return success_response({"graduationProgress": result["progress"]})


@router.post("/academic-risks/preview/users/{user_id}")
async def internal_academic_risk_preview_for_user(
    user_id: str,
    payload: InternalAcademicRiskPreviewRequest,
) -> dict[str, Any]:
    """Preview academic risks for proposed course numbers (MAS Risk Sentinel)."""
    database = await get_database()
    result = await preview_academic_risks_for_user(
        database,
        user_id,
        course_numbers=payload.course_numbers,
        semester_code=payload.semester_code,
        max_credits=payload.max_credits,
        min_credits=payload.min_credits,
    )

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if result["status"] == "degree_not_selected":
        raise HTTPException(status_code=400, detail="Degree not selected on student profile")
    if result["status"] == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})

    return success_response({"academicRiskAnalysis": result["analysis"]})


@router.post("/semester-suggestions/users/{user_id}")
async def internal_semester_suggestions_for_user(
    user_id: str,
    payload: InternalSemesterSuggestionRequest,
) -> dict[str, Any]:
    """Return Progress-aligned semester course suggestions from Mongo catalog offerings."""
    database = await get_database()
    result = await suggest_semester_courses(
        database,
        user_id,
        semester_code=payload.semester_code,
        max_credits=payload.max_credits,
    )

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if result["status"] == "degree_not_selected":
        raise HTTPException(status_code=400, detail="Degree not selected on student profile")
    if result["status"] == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})

    return success_response(result)
