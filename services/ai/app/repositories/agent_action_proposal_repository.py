"""Read/write access to `agent_action_proposals` -- the agent's own
operational state (docs/agent/AGENT_VISION.md §2.1: "agent_clarification_states
(and the rest of the agent's own conversation/audit trail -- runs, steps,
tool calls, action proposals) -- the agent's own operational state, not
academic knowledge"), never a shared student-state collection.

Unlike every other repository in this package (`student_profile_repository.py`,
`completed_course_repository.py`, `semester_plan_repository.py`, all
deliberately read-only -- "this service never writes to shared student-state
collections"), this one writes, because `agent_action_proposals` is the
agent's own collection, not one it shares read-only access to. Only ever
*creates* a `status="pending"` proposal -- confirming/rejecting it (the
actual mutation) stays out of scope for `propose_action`/this repository,
matching §5.1's "always proposal-only, never a direct mutation" rule.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

AGENT_ACTION_PROPOSALS_COLLECTION = "agent_action_proposals"


async def create_action_proposal(
    database: AsyncIOMotorDatabase,
    *,
    action_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Insert one pending proposal document and return it (with its real
    `_id`) -- never updates/deletes; this repository has no other write
    method by design.
    """
    document = {
        "actionType": action_type,
        "payload": payload,
        "status": "pending",
        "createdAt": datetime.now(timezone.utc),
    }
    result = await database[AGENT_ACTION_PROPOSALS_COLLECTION].insert_one(document)
    return {**document, "_id": result.inserted_id}
