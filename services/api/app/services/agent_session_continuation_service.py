"""Shared helpers for resuming or branching MAS agent sessions."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.queue.mas_jobs import enqueue_mas_session


async def enqueue_existing_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    session_id: str,
) -> bool:
    """Re-queue an existing session document for the MAS worker."""
    _ = database
    return await enqueue_mas_session(session_id)


def build_second_opinion_constraints(
    *,
    source_session_id: str,
    utility_profile: str,
    base_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = dict(base_constraints or {})
    constraints["utilityProfile"] = utility_profile
    constraints["secondOpinionOf"] = source_session_id
    return constraints
