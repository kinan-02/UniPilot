"""Redis snapshots and replay log for MAS negotiation."""

from __future__ import annotations

import json
from typing import Any

from app.db.redis_client import get_redis_client
from app.orchestrator.blackboard import Blackboard

SNAPSHOT_TTL_SECONDS = 86_400
REPLAY_MAX_EVENTS = 64
REPLAY_KEY_SUFFIX = ":replay"
SNAPSHOT_KEY_SUFFIX = ":snapshot"


def replay_key(session_id: str) -> str:
    return f"mas:session:{session_id}{REPLAY_KEY_SUFFIX}"


def snapshot_key(session_id: str) -> str:
    return f"mas:session:{session_id}{SNAPSHOT_KEY_SUFFIX}"


def _serialize_blackboard(blackboard: Blackboard) -> dict[str, Any]:
    return {
        "goal": blackboard.goal,
        "round": blackboard.round,
        "transcriptLength": len(blackboard.transcript),
        "goalSpec": blackboard.goal_spec.model_dump() if blackboard.goal_spec else None,
        "candidatePlan": (
            blackboard.candidate_plan.model_dump() if blackboard.candidate_plan else None
        ),
        "candidatePlans": [plan.model_dump() for plan in blackboard.candidate_plans],
        "openVetoes": blackboard.open_vetoes,
        "openCritiques": blackboard.open_critiques,
        "variantEvaluations": [
            evaluation.model_dump() for evaluation in blackboard.variant_evaluations
        ],
        "utilityBreakdown": blackboard.utility_breakdown,
        "relaxedConstraints": blackboard.relaxed_constraints,
    }


def build_snapshot_payload(
    *,
    session_id: str,
    blackboard: Blackboard,
    event: str,
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "event": event,
        "round": blackboard.round,
        "state": _serialize_blackboard(blackboard),
        "transcriptTail": blackboard.transcript[-3:],
    }


async def persist_blackboard_snapshot(
    *,
    session_id: str,
    blackboard: Blackboard,
    event: str,
) -> None:
    """Best-effort latest snapshot + append-only replay log."""
    await _append_replay_event(
        session_id=session_id,
        payload=build_snapshot_payload(
            session_id=session_id,
            blackboard=blackboard,
            event=event,
        ),
        update_snapshot=True,
    )


async def persist_session_completion_event(
    *,
    session_id: str,
    status: str,
    rounds: int,
    final_decision: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Append a terminal replay marker when the worker finishes a session."""
    if not session_id:
        return

    payload: dict[str, Any] = {
        "sessionId": session_id,
        "event": "session_completed",
        "status": status,
        "rounds": rounds,
        "hasFinalDecision": final_decision is not None,
    }
    if error:
        payload["error"] = error

    await _append_replay_event(session_id=session_id, payload=payload, update_snapshot=False)


async def _append_replay_event(
    *,
    session_id: str,
    payload: dict[str, Any],
    update_snapshot: bool,
) -> None:
    client = get_redis_client()
    if client is None or not session_id:
        return

    encoded = json.dumps(payload, default=str)
    try:
        if update_snapshot:
            await client.set(snapshot_key(session_id), encoded, ex=SNAPSHOT_TTL_SECONDS)
        await client.lpush(replay_key(session_id), encoded)
        await client.ltrim(replay_key(session_id), 0, REPLAY_MAX_EVENTS - 1)
        await client.expire(replay_key(session_id), SNAPSHOT_TTL_SECONDS)
    except Exception:  # noqa: BLE001 — snapshots must not break negotiation
        return


async def load_replay_events(session_id: str) -> list[dict[str, Any]]:
    """Return replay events oldest-first."""
    client = get_redis_client()
    if client is None or not session_id:
        return []

    try:
        raw_events = await client.lrange(replay_key(session_id), 0, REPLAY_MAX_EVENTS - 1)
    except Exception:  # noqa: BLE001
        return []

    events: list[dict[str, Any]] = []
    for raw in reversed(raw_events):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events
