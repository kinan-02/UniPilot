"""`propose_action` -- the one generic write primitive (docs/agent/AGENT_VISION.md
§5, primitive 9b). Always proposal-only, never a direct mutation -- same
human-confirm boundary as the rest of the system. The only primitive allowed
to declare `side_effect="propose"` (enforced by `ToolRegistry.register`).

`action_type` is a plain, unvalidated `str` -- unlike every other
vocabulary field in this codebase (`entity_type`, `relation`,
`change["type"]`, `rule["type"]`, `fact_type`, constraint `type`s), this
primitive's own logic never branches on `action_type` at all: it always
does exactly one thing (persist a pending proposal record) regardless of
what kind of action is being proposed. There is nothing to validate against
a known set, so nothing is -- the caller (eventually an Interpretation/
Simulation-Planning subagent) owns the meaning of `action_type`/`payload`;
this primitive only owns durably recording the proposal.

Writes to `agent_action_proposals` -- the agent's own operational
collection (see `app.repositories.agent_action_proposal_repository`), not a
shared student-state collection this service otherwise only reads.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor
from app.db.mongo import get_database
from app.repositories.agent_action_proposal_repository import create_action_proposal

TOOL_NAME = "propose_action"


class ProposeActionInput(BaseModel):
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


async def run_propose_action(payload: ProposeActionInput) -> ToolOutputEnvelope:
    action_type = (payload.action_type or "").strip()
    if not action_type:
        return ToolOutputEnvelope(ok=False, data=None, error="action_type_required")

    try:
        database = await get_database()
        proposal = await create_action_proposal(database, action_type=action_type, payload=payload.payload)
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"proposal_creation_failed: {exc}")

    return ToolOutputEnvelope(
        ok=True,
        data={
            "proposalId": str(proposal["_id"]),
            "actionType": proposal["actionType"],
            "payload": proposal["payload"],
            "status": proposal["status"],
            "createdAt": proposal["createdAt"].isoformat(),
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Create a proposal for a write action (completed-course edit, profile "
    "change, plan change) -- never a direct mutation; always requires human confirmation.",
    input_model=ProposeActionInput,
    output_model=ToolOutputEnvelope,
    side_effect="propose",
    callable=run_propose_action,
)
