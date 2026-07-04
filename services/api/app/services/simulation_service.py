"""Simulation council orchestration (AGT-3)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.simulation_result_repository import (
    create_simulation_result,
    find_simulation_result_by_id_and_user_id,
    find_simulation_results_by_scenario_id,
)
from app.repositories.simulation_scenario_repository import (
    create_simulation_scenario,
    find_simulation_scenario_by_id_and_user_id,
    find_simulation_scenarios_by_user_id,
)
from app.schemas.simulation import (
    CreateSimulationFromTextRequest,
    CreateSimulationScenarioRequest,
    operations_to_storage,
    validate_operations_payload,
)
from app.services.simulation_runner import run_deterministic_simulation
from app.services.simulation_scenario_parser import parse_simulation_text

ExecutionMode = Literal["auto", "sync", "async"]


def should_enqueue_simulation_run(operations: list[dict[str, Any]], execution_mode: ExecutionMode) -> bool:
    if execution_mode == "sync":
        return False
    if execution_mode == "async":
        return True
    if len(operations) >= 3:
        return True
    return any(operation.get("type") == "change_track" for operation in operations)


async def create_scenario_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    request: CreateSimulationScenarioRequest,
) -> dict[str, Any]:
    stored = await create_simulation_scenario(
        database,
        user_id,
        {
            "name": request.name.strip(),
            "description": request.description,
            "operations": operations_to_storage(request.operations),
            "semesterCode": request.semesterCode,
            "planId": request.planId,
            "naturalLanguagePrompt": request.naturalLanguagePrompt,
            "status": "draft",
        },
    )
    return {"status": "ok", "scenario": stored}


async def create_scenario_from_text_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    request: CreateSimulationFromTextRequest,
) -> dict[str, Any]:
    operations = parse_simulation_text(request.text)
    if not operations:
        return {
            "status": "parse_failed",
            "detail": "Could not parse scenario operations from the provided text",
        }

    validated = validate_operations_payload(operations)
    name = (request.name or request.text.strip()[:80] or "What-if scenario").strip()
    stored = await create_simulation_scenario(
        database,
        user_id,
        {
            "name": name,
            "description": request.text.strip(),
            "operations": validated,
            "semesterCode": request.semesterCode,
            "planId": request.planId,
            "naturalLanguagePrompt": request.text.strip(),
            "status": "draft",
        },
    )
    return {"status": "ok", "scenario": stored, "parsedOperations": validated}


async def list_scenarios_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 30,
) -> dict[str, Any]:
    return await find_simulation_scenarios_by_user_id(
        database,
        user_id,
        page=page,
        limit=limit,
    )


async def get_scenario_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
) -> dict[str, Any]:
    scenario = await find_simulation_scenario_by_id_and_user_id(database, scenario_id, user_id)
    if not scenario:
        return {"status": "not_found"}
    return {"status": "ok", "scenario": scenario}


async def _persist_simulation_result(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
    run_output: dict[str, Any],
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    stored = await create_simulation_result(
        database,
        user_id,
        {
            "scenarioId": scenario_id,
            "beforeSnapshot": run_output["beforeSnapshot"],
            "afterSnapshot": run_output["afterSnapshot"],
            "deltas": run_output["deltas"],
            "summary": run_output["summary"],
            "narrative": run_output.get("narrative"),
            "warnings": run_output.get("warnings") or [],
            "jobId": job_id,
        },
    )
    return stored


async def run_scenario_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
    *,
    execution_mode: ExecutionMode = "auto",
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    scenario_lookup = await get_scenario_for_user(database, user_id, scenario_id)
    if scenario_lookup["status"] == "not_found":
        return {"status": "not_found"}

    scenario = scenario_lookup["scenario"]
    operations = scenario.get("operations") or []
    if should_enqueue_simulation_run(operations, execution_mode):
        from app.schemas.ai_job import CreateAiJobRequest
        from app.services.ai_job_service import create_job_for_user

        request = CreateAiJobRequest(
            type="simulation_run",
            payload={"scenario_id": scenario_id},
        )
        queued = await create_job_for_user(database, user_id, request, settings=settings)
        return {
            "status": "queued",
            "job": queued["job"],
            "asyncAccepted": True,
        }

    run_output = await run_deterministic_simulation(database, user_id, scenario)
    if run_output.get("status") != "ok":
        return run_output

    narrative = await _maybe_narrate_simulation(run_output, scenario, settings=settings)
    if narrative:
        run_output["narrative"] = narrative

    result = await _persist_simulation_result(
        database,
        user_id,
        scenario_id,
        run_output,
    )
    return {"status": "ok", "result": result, "asyncAccepted": False}


async def _maybe_narrate_simulation(
    run_output: dict[str, Any],
    scenario: dict[str, Any],
    *,
    settings: Settings,
) -> str | None:
    try:
        from app.clients.ai_simulation_client import narrate_simulation_impact

        return await narrate_simulation_impact(
            scenario_name=str(scenario.get("name") or "Simulation"),
            operations=scenario.get("operations") or [],
            before_snapshot=run_output["beforeSnapshot"],
            after_snapshot=run_output["afterSnapshot"],
            deltas=run_output["deltas"],
            settings=settings,
        )
    except Exception:
        return None


async def get_result_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    result_id: str,
) -> dict[str, Any]:
    result = await find_simulation_result_by_id_and_user_id(database, result_id, user_id)
    if not result:
        return {"status": "not_found"}
    return {"status": "ok", "result": result}


async def list_results_for_scenario(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    scenario_lookup = await get_scenario_for_user(database, user_id, scenario_id)
    if scenario_lookup["status"] == "not_found":
        return {"status": "not_found"}
    listed = await find_simulation_results_by_scenario_id(
        database,
        user_id,
        scenario_id,
        page=page,
        limit=limit,
    )
    return {"status": "ok", **listed}
