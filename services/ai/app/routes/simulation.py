"""Simulation council routes (AGT-3)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.responses import success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.simulation import NarrateSimulationRequest
from app.services.impact_narrator import narrate_simulation_impact

router = APIRouter(tags=["simulation"])


@router.post("/simulate/narrate", dependencies=[Depends(require_internal_service_token)])
async def narrate_simulation_route(body: NarrateSimulationRequest) -> dict:
    try:
        narrative = narrate_simulation_impact(
            scenario_name=body.scenario_name.strip(),
            operations=body.operations,
            before_snapshot=body.before_snapshot,
            after_snapshot=body.after_snapshot,
            deltas=body.deltas,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return success_response({"narrative": narrative})
