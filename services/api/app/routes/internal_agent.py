"""Internal-only endpoints backing the `agent` service's deep academic computation.

The `agent` service has its own direct read-only MongoDB access for simple
lookups (catalog, offerings, profile, completed courses, semester plans —
see `services/agent/app/repositories/`). These three endpoints exist only
for computation that stays exclusively in `api` to avoid duplicating
complex, actively-evolving business rules that are also used by `api`'s own
plain REST endpoints (`graduation_progress_calculator`, the semester
planning/suggestion engine, requirement-contribution matrix evaluation).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.db.mongo import get_database
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.agent_context_snapshot import AgentContextSnapshot
from app.services.graduation_audit_service import run_graduation_audit
from app.services.requirement_contribution_service import evaluate_requirement_contribution
from app.services.semester_planning_service import generate_semester_plan_options

router = APIRouter(
    prefix="/internal/agent",
    tags=["internal-agent"],
    dependencies=[Depends(require_internal_service_token)],
)


def success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


class SemesterPlanOptionsRequest(AgentContextSnapshot):
    pass


@router.get("/graduation-audit/users/{user_id}")
async def internal_graduation_audit(user_id: str) -> dict[str, Any]:
    """Full `GraduationAuditResult` (blockers, assumptions, can-graduate) for a user."""
    database = await get_database()
    result = await run_graduation_audit(database, user_id=user_id)
    return success_response({"graduationAudit": result.model_dump()})


@router.post("/semester-plan-options/users/{user_id}")
async def internal_semester_plan_options(
    user_id: str,
    payload: SemesterPlanOptionsRequest,
) -> dict[str, Any]:
    """Generate semester plan option(s) for the agent's semester planning workflow."""
    database = await get_database()
    result = await generate_semester_plan_options(database, user_id=user_id, context=payload)
    return success_response({"semesterPlanning": result.model_dump()})


@router.get("/course-requirement-contribution")
async def internal_course_requirement_contribution(
    program_code: str = Query(alias="programCode", min_length=1, max_length=64),
    course_number: str = Query(alias="courseNumber", min_length=1, max_length=16),
) -> dict[str, Any]:
    """Evaluate how a course counts toward a resolved degree program's requirements.

    The agent service resolves `profile -> program_code` itself (a small,
    stable mapping it duplicates locally); this endpoint only wraps the
    pool/matrix classification engine, which stays exclusively in `api`.
    """
    database = await get_database()
    contribution = await evaluate_requirement_contribution(
        database,
        course_number=course_number,
        program_code=program_code,
    )
    return success_response({"contribution": contribution})
