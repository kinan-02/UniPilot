"""Execute user-confirmed agent actions (spec §28)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_action_proposal_repository import (
    find_agent_action_proposal_for_user,
    update_agent_action_proposal_status,
)
from app.schemas.transcript_import import CommitTranscriptImportRequest
from app.services.semester_planning_service import save_semester_plan_option
from app.services.transcript_import_service import commit_transcript_import


class AgentActionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def confirm_agent_action(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    action_id: str,
) -> dict[str, Any]:
    proposal = await find_agent_action_proposal_for_user(
        database,
        proposal_id=action_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if proposal is None:
        raise AgentActionError("Action proposal not found", status_code=404)
    if proposal.get("status") != "pending":
        raise AgentActionError(f"Action is already {proposal.get('status')}", status_code=409)

    confirmed = await update_agent_action_proposal_status(
        database,
        proposal_id=action_id,
        user_id=user_id,
        status="confirmed",
    )
    if confirmed is None:
        raise AgentActionError("Action could not be confirmed", status_code=409)

    action_type = str(proposal.get("type") or "")
    try:
        if action_type == "import_completed_courses":
            result = await _execute_import_completed_courses(
                database,
                user_id=user_id,
                payload=proposal.get("payload") or {},
            )
        elif action_type == "save_semester_plan":
            result = await _execute_save_semester_plan(
                database,
                user_id=user_id,
                payload=proposal.get("payload") or {},
            )
        else:
            raise AgentActionError(f"Unsupported action type: {action_type}", status_code=400)

        executed = await update_agent_action_proposal_status(
            database,
            proposal_id=action_id,
            user_id=user_id,
            status="executed",
            from_status="confirmed",
        )
        return {
            "proposal": executed or confirmed,
            "result": result,
        }
    except AgentActionError:
        await update_agent_action_proposal_status(
            database,
            proposal_id=action_id,
            user_id=user_id,
            status="failed",
            from_status="confirmed",
            error="Action execution failed",
        )
        raise
    except Exception as exc:  # noqa: BLE001
        await update_agent_action_proposal_status(
            database,
            proposal_id=action_id,
            user_id=user_id,
            status="failed",
            from_status="confirmed",
            error=str(exc),
        )
        raise AgentActionError("Action execution failed", status_code=500) from exc


async def reject_agent_action(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    action_id: str,
) -> dict[str, Any]:
    proposal = await find_agent_action_proposal_for_user(
        database,
        proposal_id=action_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if proposal is None:
        raise AgentActionError("Action proposal not found", status_code=404)
    if proposal.get("status") != "pending":
        raise AgentActionError(f"Action is already {proposal.get('status')}", status_code=409)

    rejected = await update_agent_action_proposal_status(
        database,
        proposal_id=action_id,
        user_id=user_id,
        status="rejected",
    )
    if rejected is None:
        raise AgentActionError("Action could not be rejected", status_code=409)
    return {"proposal": rejected}


async def _execute_import_completed_courses(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    courses = list(payload.get("courses") or [])
    if not courses:
        raise AgentActionError("No courses selected for import", status_code=400)

    request = CommitTranscriptImportRequest.model_validate(
        {
            "courses": courses,
            "skipDuplicates": bool(payload.get("skipDuplicates", True)),
            "replaceExisting": bool(payload.get("replaceExisting", False)),
        }
    )
    return await commit_transcript_import(database, user_id, request)


async def _execute_save_semester_plan(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = await save_semester_plan_option(database, user_id=user_id, option=payload)
    if result.get("status") != "ok":
        errors = list(result.get("errors") or [result.get("status") or "save_failed"])
        raise AgentActionError(errors[0], status_code=400)
    return result


def build_plan_saved_text(*, plan_name: str | None, semester_code: str | None) -> str:
    label = plan_name or "Semester plan"
    semester = semester_code or "your semester"
    return f'Saved "{label}" as a draft plan for {semester}. You can refine groups and schedule in the planner.'


def build_import_success_text(*, created_count: int, skipped_count: int) -> str:
    parts = [f"Imported {created_count} completed course(s)."]
    if skipped_count:
        parts.append(f"Skipped {skipped_count} duplicate(s).")
    parts.append("You can ask me to recalculate your graduation progress.")
    return " ".join(parts)


def proposal_to_agent_action(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": proposal.get("id"),
        "action_type": proposal.get("type"),
        "label": proposal.get("title") or "Confirm action",
        "title": proposal.get("title") or "Confirm action",
        "description": proposal.get("description"),
        "preview": proposal.get("preview"),
        "requires_confirmation": True,
        "payload": proposal.get("payload") or {},
        "status": proposal.get("status") or "pending",
    }
