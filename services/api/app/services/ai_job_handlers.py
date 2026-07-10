"""Job-type handlers executed by the worker (via internal process endpoint)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.schemas.ai_job import AdvisorDeepPlanPayload, SimulationRunPayload, WatchdogScanPayload
from app.services.advisor_service import ask_advisor_for_user
from app.services.simulation_job_runner import run_scenario_from_job
from app.services.watchdog_service import run_watchdog_for_user


async def handle_advisor_deep_plan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    validated = AdvisorDeepPlanPayload.model_validate(payload)
    result = await ask_advisor_for_user(
        database,
        user_id,
        validated.question.strip(),
        conversation_id=validated.conversation_id,
        include_agent_trace=validated.include_agent_trace,
        settings=settings,
    )

    status = result.get("status")
    if status == "conversation_not_found":
        raise ValueError("Advisor conversation not found")
    if status == "unavailable":
        raise RuntimeError(str(result.get("detail") or "Advisor unavailable"))
    if status == "bad_request":
        raise ValueError(str(result.get("detail") or "Invalid advisor request"))
    if status == "error":
        raise RuntimeError(str(result.get("detail") or "Advisor request failed"))
    if status != "ok":
        raise RuntimeError(f"Unexpected advisor status: {status}")

    output: dict[str, Any] = {"advisor": result["advisor"]}
    if result.get("conversation"):
        output["conversation"] = result["conversation"]
    return output


async def handle_simulation_run(
    database: AsyncIOMotorDatabase,
    user_id: str,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    validated = SimulationRunPayload.model_validate(payload)
    return await run_scenario_from_job(
        database,
        user_id,
        validated.scenario_id,
        job_id=job_id,
        settings=settings,
    )


async def handle_watchdog_scan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    from app.repositories.user_repository import find_user_by_id

    validated = WatchdogScanPayload.model_validate(payload)
    user = await find_user_by_id(database, user_id)
    email = user.get("email") if user else None

    return await run_watchdog_for_user(
        database,
        user_id,
        trigger=validated.trigger,
        plan_id=validated.plan_id,
        user_email=str(email) if email else None,
        settings=settings,
    )


JOB_HANDLERS = {
    "advisor_deep_plan": handle_advisor_deep_plan,
    "simulation_run": handle_simulation_run,
    "watchdog_scan": handle_watchdog_scan,
}


async def dispatch_ai_job_handler(
    database: AsyncIOMotorDatabase,
    *,
    job_type: str,
    user_id: str,
    payload: dict[str, Any],
    settings: Settings | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    handler = JOB_HANDLERS.get(job_type)
    if handler is None:
        raise ValueError(f"Unsupported AI job type: {job_type}")
    if job_type == "simulation_run":
        return await handler(database, user_id, payload, settings=settings, job_id=job_id)
    return await handler(database, user_id, payload, settings=settings)
