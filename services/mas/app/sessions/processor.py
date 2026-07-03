"""Persist and update MAS agent sessions in MongoDB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.db.mongo import get_database
from app.orchestrator.engine import run_negotiation
from app.sessions.continuations import build_session_lineage, merge_lineage_into_decision
from app.services.blackboard_snapshot import persist_session_completion_event
from app.services.user_context_loader import load_enriched_user_context
from app.services.what_if_scenario import apply_what_if_scenario, parse_what_if_scenario

AGENT_SESSIONS_COLLECTION = "agent_sessions"

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_agent_session_indexes(database: AsyncIOMotorDatabase) -> None:
    settings = get_settings()
    collection = database[settings.agent_sessions_collection]
    await collection.create_index([("userId", 1), ("createdAt", -1)], name="agent_sessions_user_created")
    await collection.create_index([("status", 1)], name="agent_sessions_status")


async def find_session_by_id(
    database: AsyncIOMotorDatabase,
    session_id: str,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(session_id):
        return None
    settings = get_settings()
    return await database[settings.agent_sessions_collection].find_one(
        {"_id": ObjectId(session_id)}
    )


async def mark_session_processing(database: AsyncIOMotorDatabase, session_id: str) -> None:
    settings = get_settings()
    await database[settings.agent_sessions_collection].update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": "processing", "updatedAt": _utc_now()}},
    )


async def complete_session(
    database: AsyncIOMotorDatabase,
    session_id: str,
    *,
    status: str,
    transcript: list[dict[str, Any]],
    final_decision: dict[str, Any] | None,
    utility_breakdown: dict[str, Any] | None,
    rounds: int,
    error: str | None = None,
) -> None:
    settings = get_settings()
    await database[settings.agent_sessions_collection].update_one(
        {"_id": ObjectId(session_id)},
        {
            "$set": {
                "status": status,
                "transcript": transcript,
                "finalDecision": final_decision,
                "utilityBreakdown": utility_breakdown,
                "rounds": rounds,
                "error": error,
                "updatedAt": _utc_now(),
            }
        },
    )


async def process_session(session_id: str) -> dict[str, Any]:
    database = await get_database()
    await ensure_agent_session_indexes(database)

    session = await find_session_by_id(database, session_id)
    if session is None:
        raise ValueError(f"Agent session not found: {session_id}")

    if session.get("status") not in {"pending", "processing"}:
        return session

    await mark_session_processing(database, session_id)
    user_id = str(session["userId"])
    user_context = await load_enriched_user_context(
        database,
        user_id,
        constraints=session.get("constraints") or {},
        settings=get_settings(),
    )
    completed_count = len(user_context.get("completed_courses") or [])
    context_source = user_context.get("context_source")
    data_quality = user_context.get("data_quality") or {}
    warnings = data_quality.get("warnings") if isinstance(data_quality, dict) else None
    logger.info(
        "Loaded user context for session=%s user=%s source=%s completed=%s warnings=%s",
        session_id,
        user_id,
        context_source,
        completed_count,
        warnings,
    )

    goal = str(session.get("goal") or "")
    what_if = parse_what_if_scenario(goal)
    if what_if:
        baseline_snapshot = {
            "completed_courses": list(user_context.get("completed_courses") or []),
            "track_slug": user_context.get("track_slug"),
            "constraints": dict(user_context.get("constraints") or {}),
        }
        user_context = apply_what_if_scenario(user_context, what_if)
        user_context["what_if_baseline"] = baseline_snapshot
    elif user_context.get("planning_ready") is False:
        data_quality = user_context.get("data_quality") or {}
        warnings = (
            list(data_quality.get("warnings") or [])
            if isinstance(data_quality, dict)
            else []
        )
        warning_hint = warnings[0] if warnings else "graduation_unavailable"
        planning_error = (
            "Cannot generate a degree-aligned plan without graduation progress. "
            f"Resolve data issue: {warning_hint}."
        )
        await complete_session(
            database,
            session_id,
            status="failed",
            transcript=[],
            final_decision=None,
            utility_breakdown=None,
            rounds=0,
            error=planning_error,
        )
        await persist_session_completion_event(
            session_id=session_id,
            status="failed",
            rounds=0,
            final_decision=None,
            error=planning_error,
        )
        return await find_session_by_id(database, session_id) or session

    prior_transcript = list(session.get("priorTranscript") or [])
    lineage = build_session_lineage(session)

    try:
        result = await run_negotiation(
            goal=goal,
            user_context=user_context,
            session_id=session_id,
            initial_transcript=prior_transcript,
        )
        final_decision = merge_lineage_into_decision(result.final_decision, lineage)
        await complete_session(
            database,
            session_id,
            status=result.status,
            transcript=result.transcript,
            final_decision=final_decision,
            utility_breakdown=result.utility_breakdown,
            rounds=result.rounds,
            error=result.error,
        )
        await persist_session_completion_event(
            session_id=session_id,
            status=result.status,
            rounds=result.rounds,
            final_decision=final_decision,
            error=result.error,
        )
    except Exception as exc:  # noqa: BLE001
        await complete_session(
            database,
            session_id,
            status="failed",
            transcript=[],
            final_decision=None,
            utility_breakdown=None,
            rounds=0,
            error=str(exc),
        )
        await persist_session_completion_event(
            session_id=session_id,
            status="failed",
            rounds=0,
            final_decision=None,
            error=str(exc),
        )
        raise

    updated = await find_session_by_id(database, session_id)
    return updated or session
