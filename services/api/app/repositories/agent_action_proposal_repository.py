"""MongoDB persistence for agent action proposals (spec §27.6)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

ProposalStatus = Literal["pending", "confirmed", "rejected", "expired", "executed", "failed"]

_indexes_ensured = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_id(value: Any) -> str:
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


def _serialize_proposal(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _format_id(document.get("_id")),
        "conversationId": _format_id(document.get("conversationId")),
        "userId": _format_id(document.get("userId")),
        "runId": _format_id(document.get("runId")) if document.get("runId") else None,
        "type": document.get("type"),
        "status": document.get("status"),
        "title": document.get("title"),
        "description": document.get("description"),
        "payload": document.get("payload") or {},
        "preview": document.get("preview") or {},
        "createdAt": _iso(document.get("createdAt")),
        "confirmedAt": _iso(document.get("confirmedAt")),
        "rejectedAt": _iso(document.get("rejectedAt")),
        "executedAt": _iso(document.get("executedAt")),
        "error": document.get("error"),
    }


async def ensure_agent_action_proposal_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_action_proposals_collection]
    await collection.create_index(
        [("conversationId", 1), ("createdAt", -1)],
        name="agent_action_proposals_conversation_created",
    )
    await collection.create_index(
        [("userId", 1), ("status", 1)],
        name="agent_action_proposals_user_status",
    )
    _indexes_ensured = True


def reset_agent_action_proposal_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


async def create_agent_action_proposal(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    run_id: str | None,
    action_type: str,
    title: str,
    description: str | None,
    payload: dict[str, Any],
    preview: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        raise ValueError("Invalid ids for agent action proposal")

    cfg = settings or get_settings()
    await ensure_agent_action_proposal_indexes(database, settings=cfg)
    now = _utc_now()
    document: dict[str, Any] = {
        "conversationId": ObjectId(conversation_id),
        "userId": ObjectId(user_id),
        "type": action_type,
        "status": "pending",
        "title": title,
        "description": description,
        "payload": payload,
        "preview": preview or {},
        "createdAt": now,
    }
    if run_id and ObjectId.is_valid(run_id):
        document["runId"] = ObjectId(run_id)

    result = await database[cfg.agent_action_proposals_collection].insert_one(document)
    return _serialize_proposal({"_id": result.inserted_id, **document})


async def find_agent_action_proposal_for_user(
    database: AsyncIOMotorDatabase,
    *,
    proposal_id: str,
    user_id: str,
    conversation_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(proposal_id) or not ObjectId.is_valid(user_id):
        return None
    cfg = settings or get_settings()
    query: dict[str, Any] = {
        "_id": ObjectId(proposal_id),
        "userId": ObjectId(user_id),
    }
    if conversation_id and ObjectId.is_valid(conversation_id):
        query["conversationId"] = ObjectId(conversation_id)

    document = await database[cfg.agent_action_proposals_collection].find_one(query)
    if document is None:
        return None
    return _serialize_proposal(document)


async def update_agent_action_proposal_status(
    database: AsyncIOMotorDatabase,
    *,
    proposal_id: str,
    user_id: str,
    status: ProposalStatus,
    error: str | None = None,
    from_status: ProposalStatus | None = "pending",
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(proposal_id) or not ObjectId.is_valid(user_id):
        return None
    cfg = settings or get_settings()
    now = _utc_now()
    update: dict[str, Any] = {"status": status}
    if status == "confirmed":
        update["confirmedAt"] = now
    elif status == "rejected":
        update["rejectedAt"] = now
    elif status in {"executed", "failed"}:
        update["executedAt"] = now
    if error:
        update["error"] = error

    query: dict[str, Any] = {
        "_id": ObjectId(proposal_id),
        "userId": ObjectId(user_id),
    }
    if from_status is not None:
        query["status"] = from_status

    result = await database[cfg.agent_action_proposals_collection].find_one_and_update(
        query,
        {"$set": update},
        return_document=True,
    )
    if result is None:
        return None
    return _serialize_proposal(result)
