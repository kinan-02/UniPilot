"""Worker entrypoint for simulation_run jobs (avoids ai_job import cycles)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.simulation_result_repository import create_simulation_result
from app.services.simulation_runner import run_deterministic_simulation
from app.services.simulation_service import get_scenario_for_user


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


async def run_scenario_from_job(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
    *,
    job_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    scenario_lookup = await get_scenario_for_user(database, user_id, scenario_id)
    if scenario_lookup["status"] == "not_found":
        raise ValueError("Simulation scenario not found")

    scenario = scenario_lookup["scenario"]
    run_output = await run_deterministic_simulation(database, user_id, scenario)
    if run_output.get("status") != "ok":
        raise RuntimeError(str(run_output.get("detail") or run_output.get("status")))

    narrative = await _maybe_narrate_simulation(run_output, scenario, settings=settings)
    if narrative:
        run_output["narrative"] = narrative

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
    return {"simulationResult": stored}
