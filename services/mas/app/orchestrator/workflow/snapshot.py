"""Best-effort blackboard snapshots during workflow phases."""

from __future__ import annotations

from app.orchestrator.blackboard import Blackboard
from app.services.blackboard_snapshot import persist_blackboard_snapshot


async def workflow_snapshot(blackboard: Blackboard, event: str) -> None:
    session_id = blackboard.session_id
    if session_id:
        await persist_blackboard_snapshot(
            session_id=session_id,
            blackboard=blackboard,
            event=event,
        )
