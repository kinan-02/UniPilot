"""MongoDB persistence for cross-turn clarification state (Phase 18).

Writes only to the agent-owned `agent_clarification_states` collection.
Never touches student academic collections or action proposals.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.clarification.state_schemas import PendingClarificationState, sanitize_compact_context
from app.config import Settings, get_settings

_indexes_ensured = False

_ACTIVE_STATUSES = ("pending",)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_id(value: Any) -> str:
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _serialize_state(document: dict[str, Any]) -> PendingClarificationState:
    def _dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return _utc_now()

    return PendingClarificationState(
        clarification_id=str(document.get("clarificationId") or ""),
        conversation_id=_format_id(document.get("conversationId")),
        user_id=_format_id(document.get("userId")) if document.get("userId") else None,
        status=document.get("status") or "pending",
        original_user_message=str(document.get("originalUserMessage") or ""),
        original_plan_id=document.get("originalPlanId"),
        original_intent=document.get("originalIntent"),
        original_workflow_name=document.get("originalWorkflowName"),
        questions=list(document.get("questions") or []),
        needs=list(document.get("needs") or []),
        created_at=_dt(document.get("createdAt")),
        updated_at=_dt(document.get("updatedAt")),
        expires_at=document.get("expiresAt") if document.get("expiresAt") is None else _dt(document.get("expiresAt")),
        max_pending_turns=int(document.get("maxPendingTurns") or 3),
        pending_turn_count=int(document.get("pendingTurnCount") or 0),
        resume_mode=document.get("resumeMode") or "resume_original_request",
        compact_context=sanitize_compact_context(document.get("compactContext") or {}),
        diagnostics=dict(document.get("diagnostics") or {}),
    )


async def ensure_clarification_state_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_clarification_states_collection]
    await collection.create_index(
        [("conversationId", 1), ("status", 1)],
        name="clarification_states_conversation_status",
    )
    await collection.create_index(
        [("clarificationId", 1)],
        name="clarification_states_id_unique",
        unique=True,
    )
    await collection.create_index(
        [("expiresAt", 1)],
        name="clarification_states_expires_at",
        sparse=True,
    )
    _indexes_ensured = True


def reset_clarification_state_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


class ClarificationStateRepository:
    """Agent-owned clarification state persistence."""

    def __init__(self, database: AsyncIOMotorDatabase, *, settings: Settings | None = None) -> None:
        self._database = database
        self._settings = settings or get_settings()

    @property
    def _collection(self):
        return self._database[self._settings.agent_clarification_states_collection]

    async def create_pending(
        self,
        *,
        conversation_id: str,
        user_id: str,
        original_user_message: str,
        questions: list[dict[str, Any]],
        needs: list[dict[str, Any]],
        original_plan_id: str | None = None,
        original_intent: str | None = None,
        original_workflow_name: str | None = None,
        compact_context: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
        max_pending_turns: int = 3,
        ttl_hours: int = 72,
    ) -> PendingClarificationState | None:
        if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
            return None

        existing = await self.get_active_for_conversation(conversation_id)
        if existing is not None:
            return None

        await ensure_clarification_state_indexes(self._database, settings=self._settings)
        now = _utc_now()
        clarification_id = f"clar_{uuid.uuid4().hex[:16]}"
        document = {
            "clarificationId": clarification_id,
            "conversationId": ObjectId(conversation_id),
            "userId": ObjectId(user_id),
            "status": "pending",
            "originalUserMessage": original_user_message[:2000],
            "originalPlanId": original_plan_id,
            "originalIntent": original_intent,
            "originalWorkflowName": original_workflow_name,
            "questions": questions,
            "needs": needs,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": now + timedelta(hours=ttl_hours),
            "maxPendingTurns": max(1, int(max_pending_turns)),
            "pendingTurnCount": 0,
            "resumeMode": "resume_original_request",
            "compactContext": sanitize_compact_context(compact_context or {}),
            "diagnostics": dict(diagnostics or {}),
        }
        await self._collection.insert_one(document)
        return _serialize_state(document)

    async def get_active_for_conversation(self, conversation_id: str) -> PendingClarificationState | None:
        if not ObjectId.is_valid(conversation_id):
            return None
        await ensure_clarification_state_indexes(self._database, settings=self._settings)
        document = await self._collection.find_one(
            {
                "conversationId": ObjectId(conversation_id),
                "status": {"$in": list(_ACTIVE_STATUSES)},
            },
            sort=[("createdAt", -1)],
        )
        if not document:
            return None
        return _serialize_state(document)

    async def increment_pending_turn_count(self, clarification_id: str) -> PendingClarificationState | None:
        now = _utc_now()
        result = await self._collection.find_one_and_update(
            {"clarificationId": clarification_id, "status": "pending"},
            {"$inc": {"pendingTurnCount": 1}, "$set": {"updatedAt": now}},
            return_document=True,
        )
        return _serialize_state(result) if result else None

    async def mark_answered(
        self,
        clarification_id: str,
        *,
        answers: list[dict[str, Any]],
        assumptions_created: list[dict[str, Any]] | None = None,
    ) -> PendingClarificationState | None:
        now = _utc_now()
        result = await self._collection.find_one_and_update(
            {"clarificationId": clarification_id},
            {
                "$set": {
                    "status": "answered",
                    "updatedAt": now,
                    "answers": answers,
                    "assumptionsCreated": list(assumptions_created or []),
                }
            },
            return_document=True,
        )
        return _serialize_state(result) if result else None

    async def mark_assumed(
        self,
        clarification_id: str,
        *,
        answers: list[dict[str, Any]],
        assumptions_created: list[dict[str, Any]] | None = None,
    ) -> PendingClarificationState | None:
        now = _utc_now()
        result = await self._collection.find_one_and_update(
            {"clarificationId": clarification_id},
            {
                "$set": {
                    "status": "assumed",
                    "updatedAt": now,
                    "answers": answers,
                    "assumptionsCreated": list(assumptions_created or []),
                }
            },
            return_document=True,
        )
        return _serialize_state(result) if result else None

    async def mark_expired(self, clarification_id: str) -> PendingClarificationState | None:
        now = _utc_now()
        result = await self._collection.find_one_and_update(
            {"clarificationId": clarification_id},
            {"$set": {"status": "expired", "updatedAt": now}},
            return_document=True,
        )
        return _serialize_state(result) if result else None

    async def cancel_active(self, conversation_id: str) -> PendingClarificationState | None:
        if not ObjectId.is_valid(conversation_id):
            return None
        now = _utc_now()
        result = await self._collection.find_one_and_update(
            {
                "conversationId": ObjectId(conversation_id),
                "status": {"$in": list(_ACTIVE_STATUSES)},
            },
            {"$set": {"status": "cancelled", "updatedAt": now}},
            return_document=True,
        )
        return _serialize_state(result) if result else None
