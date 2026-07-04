"""What-if simulation routes (AGT-3 / DEC-2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.repositories.simulation_result_repository import (
    ensure_simulation_result_indexes,
    to_public_simulation_result,
)
from app.repositories.simulation_scenario_repository import (
    ensure_simulation_scenario_indexes,
    to_public_simulation_scenario,
)
from app.schemas.semester_plan import OBJECT_ID_PATTERN
from app.schemas.simulation import (
    CreateSimulationFromTextRequest,
    CreateSimulationScenarioRequest,
    RunSimulationRequest,
)
from app.services.simulation_service import (
    create_scenario_for_user,
    create_scenario_from_text_for_user,
    get_result_for_user,
    get_scenario_for_user,
    list_results_for_scenario,
    list_scenarios_for_user,
    run_scenario_for_user,
)

router = APIRouter(prefix="/simulations", tags=["simulations"])

_indexes_ready = False


def reset_simulation_indexes_state() -> None:
    global _indexes_ready
    _indexes_ready = False


async def _ensure_indexes_once() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    database = await get_database()
    await ensure_simulation_scenario_indexes(database)
    await ensure_simulation_result_indexes(database)
    _indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _validate_object_id(value: str, *, label: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


def _handle_context_error(result: dict[str, Any]) -> None:
    status = result.get("status")
    if status == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if status == "degree_not_selected":
        raise HTTPException(status_code=400, detail="A degree must be selected on the student profile")
    if status == "degree_not_found":
        raise HTTPException(status_code=400, detail="Referenced degree was not found in the catalog")


@router.post("/scenarios", status_code=201)
async def create_simulation_scenario_route(
    request: Request,
    payload: CreateSimulationScenarioRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_indexes_once()
    database = await get_database()
    result = await create_scenario_for_user(database, auth.user_id, payload)
    return success_response(
        {"simulationScenario": to_public_simulation_scenario(result["scenario"])}
    )


@router.post("/scenarios/from-text", status_code=201)
async def create_simulation_from_text_route(
    request: Request,
    payload: CreateSimulationFromTextRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_indexes_once()
    database = await get_database()
    result = await create_scenario_from_text_for_user(database, auth.user_id, payload)
    if result.get("status") == "parse_failed":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return success_response(
        {
            "simulationScenario": to_public_simulation_scenario(result["scenario"]),
            "parsedOperations": result.get("parsedOperations") or [],
        }
    )


@router.get("/scenarios")
async def list_simulation_scenarios_route(
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=50),
) -> dict[str, Any]:
    await _ensure_indexes_once()
    database = await get_database()
    listed = await list_scenarios_for_user(database, auth.user_id, page=page, limit=limit)
    return success_response(
        {
            "simulationScenarios": [
                item
                for scenario in listed["scenarios"]
                if (item := to_public_simulation_scenario(scenario)) is not None
            ],
            "pagination": {
                "total": listed["total"],
                "page": listed["page"],
                "limit": listed["limit"],
            },
        }
    )


@router.get("/scenarios/{scenario_id}")
async def get_simulation_scenario_route(
    scenario_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    scenario_id = _validate_object_id(scenario_id, label="scenario id")
    await _ensure_indexes_once()
    database = await get_database()
    result = await get_scenario_for_user(database, auth.user_id, scenario_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Simulation scenario not found")
    return success_response(
        {"simulationScenario": to_public_simulation_scenario(result["scenario"])}
    )


@router.post("/scenarios/{scenario_id}/run", response_model=None)
async def run_simulation_scenario_route(
    request: Request,
    scenario_id: str,
    payload: RunSimulationRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any] | JSONResponse:
    scenario_id = _validate_object_id(scenario_id, label="scenario id")
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_indexes_once()
    database = await get_database()
    result = await run_scenario_for_user(
        database,
        auth.user_id,
        scenario_id,
        execution_mode=payload.executionMode,
    )

    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Simulation scenario not found")
    if result.get("status") == "queued":
        return JSONResponse(
            status_code=202,
            content=success_response(
                {
                    "asyncAccepted": True,
                    "job": result["job"],
                }
            ),
        )

    _handle_context_error(result)
    return success_response(
        {
            "asyncAccepted": False,
            "simulationResult": to_public_simulation_result(result["result"]),
        }
    )


@router.get("/results/{result_id}")
async def get_simulation_result_route(
    result_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    result_id = _validate_object_id(result_id, label="result id")
    await _ensure_indexes_once()
    database = await get_database()
    result = await get_result_for_user(database, auth.user_id, result_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Simulation result not found")
    return success_response(
        {"simulationResult": to_public_simulation_result(result["result"])}
    )


@router.get("/scenarios/{scenario_id}/results")
async def list_simulation_results_route(
    scenario_id: str,
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    scenario_id = _validate_object_id(scenario_id, label="scenario id")
    await _ensure_indexes_once()
    database = await get_database()
    result = await list_results_for_scenario(
        database,
        auth.user_id,
        scenario_id,
        page=page,
        limit=limit,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Simulation scenario not found")
    return success_response(
        {
            "simulationResults": [
                item
                for document in result["results"]
                if (item := to_public_simulation_result(document)) is not None
            ],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
            },
        }
    )
