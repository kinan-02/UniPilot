"""Conversation-level assumptions and recent message memory (spec §32)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_message_repository import list_messages_for_conversation


def assumptions_from_entities(entities: dict[str, Any]) -> list[str]:
    """Derive ephemeral assumptions from resolved entities."""
    assumptions: list[str] = []
    avoid_days = [str(day) for day in (entities.get("avoidDays") or []) if day]
    if avoid_days:
        assumptions.append(f"Avoiding classes on: {', '.join(avoid_days)}")

    max_credits = entities.get("maxCredits")
    if max_credits is not None:
        assumptions.append(f"Maximum credits this semester: {max_credits}")

    objective = entities.get("planningObjective")
    if objective == "lighter_workload":
        assumptions.append("Preferring a lighter workload")
    elif objective == "heavier_workload":
        assumptions.append("Preferring faster progress / heavier workload")

    target = entities.get("targetSemesterCode") or entities.get("targetSemester")
    if target:
        assumptions.append(f"Planning for semester: {target}")

    course_number = entities.get("courseNumber")
    if course_number:
        assumptions.append(f"Discussing course {course_number}")

    requirement = entities.get("requirementGroupId") or entities.get("requirementBucket")
    if requirement:
        assumptions.append(f"Focus requirement: {requirement}")

    return assumptions


async def load_conversation_memory(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    stored_assumptions: list[str] | None = None,
    entities: dict[str, Any] | None = None,
    message_limit: int = 8,
) -> dict[str, Any]:
    """Load assumptions and recent turns for context building."""
    messages = await list_messages_for_conversation(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=message_limit,
    )
    recent_turns = [
        {"role": message.get("role"), "content": message.get("content")}
        for message in messages[-message_limit:]
        if message.get("content")
    ]

    merged_assumptions = list(dict.fromkeys([*(stored_assumptions or []), *assumptions_from_entities(entities or {})]))
    return {
        "assumptions": merged_assumptions,
        "recentTurns": recent_turns,
    }
