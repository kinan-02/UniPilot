"""HTTP client for simulation council AI endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings
from app.clients.ai_advisor_client import AiAdvisorClientError


async def narrate_simulation_impact(
    *,
    scenario_name: str,
    operations: list[dict[str, Any]],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    deltas: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    url = f"{settings.resolved_ai_service_url()}/simulate/narrate"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(min(settings.ai_advisor_timeout_seconds, 90))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers=headers,
            json={
                "scenario_name": scenario_name,
                "operations": operations,
                "before_snapshot": before_snapshot,
                "after_snapshot": after_snapshot,
                "deltas": deltas,
            },
        )

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") if isinstance(payload, dict) else None
        if not detail and isinstance(payload, dict):
            detail = payload.get("detail")
        if not detail:
            detail = "Simulation narration request failed"
        raise AiAdvisorClientError(status_code=response.status_code, detail=str(detail))

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise AiAdvisorClientError(
            status_code=502,
            detail="Simulation narrator returned an invalid response",
        )

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("narrative"), str):
        raise AiAdvisorClientError(
            status_code=502,
            detail="Simulation narrator response missing narrative",
        )

    return data["narrative"].strip()
