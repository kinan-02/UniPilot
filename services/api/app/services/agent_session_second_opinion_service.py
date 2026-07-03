"""Second-opinion agent sessions with alternate utility profiles."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_session_repository import find_agent_session_by_id_and_user
from app.services.agent_session_continuation_service import build_second_opinion_constraints
from app.services.agent_session_service import start_agent_session

UtilityProfile = Literal["balanced", "risk_averse", "aggressive"]

VALID_PROFILES = frozenset({"balanced", "risk_averse", "aggressive"})


async def start_second_opinion_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
    utility_profile: UtilityProfile,
) -> dict[str, Any]:
    source = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if source is None:
        return {"status": "not_found"}
    if source.get("status") != "completed":
        return {
            "status": "invalid_state",
            "error": "Second opinion requires a completed source session.",
        }

    profile = str(utility_profile).strip().lower()
    if profile not in VALID_PROFILES:
        return {
            "status": "validation_error",
            "errors": [f"utilityProfile must be one of: {', '.join(sorted(VALID_PROFILES))}"],
        }

    constraints = build_second_opinion_constraints(
        source_session_id=session_id,
        utility_profile=profile,
        base_constraints=dict(source.get("constraints") or {}),
    )

    session = await start_agent_session(
        database,
        user_id=user_id,
        session_type=str(source.get("type") or "next_semester_plan"),
        goal=str(source.get("goal") or ""),
        constraints=constraints,
    )
    return {
        "status": "ok",
        "session": session,
        "utilityProfile": profile,
        "sourceSessionId": session_id,
    }
