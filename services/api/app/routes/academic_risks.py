"""Academic risk routes (Phase 17)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies.auth import AuthContext, require_auth
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.db.mongo import get_database
from app.repositories.academic_risk_repository import (
    ensure_academic_risk_indexes,
    to_public_academic_risk_analysis,
    to_public_academic_risk_summary,
)
from app.schemas.academic_risk import AnalyzeAcademicRiskRequest
from app.schemas.semester_plan import OBJECT_ID_PATTERN
from app.services.academic_risk_service import (
    analyze_and_store_academic_risks,
    get_academic_risk_analysis_for_user,
    list_academic_risk_analyses_for_user,
)

router = APIRouter(prefix="/academic-risks", tags=["academic-risks"])

_academic_risk_indexes_ready = False

LIST_QUERY_ALLOWED = frozenset({"page", "limit"})


def reset_academic_risk_indexes_state() -> None:
    global _academic_risk_indexes_ready
    _academic_risk_indexes_ready = False


async def _ensure_academic_risk_indexes_once() -> None:
    global _academic_risk_indexes_ready

    if _academic_risk_indexes_ready:
        return

    database = await get_database()
    await ensure_academic_risk_indexes(database)
    _academic_risk_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def _handle_analysis_context_error(result: dict[str, Any]) -> None:
    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")

    if result["status"] == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail=(
                "A degree must be selected on the student profile before "
                "analyzing academic risks"
            ),
        )

    if result["status"] == "degree_not_found":
        raise HTTPException(
            status_code=400,
            detail="Referenced degree was not found in the catalog",
        )

    if result["status"] == "plan_not_found":
        raise HTTPException(status_code=404, detail="Semester plan not found")


def validate_analysis_id_param(analysis_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(analysis_id):
        raise HTTPException(status_code=400, detail="Identifier must be a valid ObjectId")
    return analysis_id


@router.post("/analyze", status_code=201)
async def analyze_academic_risks_route(
    request: Request,
    payload: AnalyzeAcademicRiskRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_academic_risk_indexes_once()
    database = await get_database()

    result = await analyze_and_store_academic_risks(
        database,
        auth.user_id,
        payload.model_dump(exclude_none=True),
    )
    _handle_analysis_context_error(result)

    return success_response(
        {"academicRiskAnalysis": to_public_academic_risk_analysis(result["analysis"])}
    )


@router.get("")
async def list_academic_risks(
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
    list_result = await list_academic_risk_analyses_for_user(
        database,
        auth.user_id,
        {"page": page, "limit": limit},
    )

    return success_response(
        {
            "academicRiskAnalyses": [
                summary
                for analysis in list_result["analyses"]
                if (summary := to_public_academic_risk_summary(analysis)) is not None
            ],
            "pagination": {
                "total": list_result["total"],
                "page": list_result["page"],
                "limit": list_result["limit"],
            },
        }
    )


@router.get("/{analysis_id}")
async def get_academic_risk_analysis(
    analysis_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_analysis_id_param(analysis_id)

    database = await get_database()
    result = await get_academic_risk_analysis_for_user(
        database,
        auth.user_id,
        analysis_id,
    )

    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Academic risk analysis not found")

    return success_response(
        {"academicRiskAnalysis": to_public_academic_risk_analysis(result["analysis"])}
    )
