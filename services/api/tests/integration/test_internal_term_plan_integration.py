"""Integration test for the internal term-plan route's auth wiring."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_internal_term_plan_requires_token(auth_client, monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    # Valid body, no service token -> the router-level dependency rejects it.
    response = await auth_client.post(
        "/internal/term-plan/users/000000000000000000000000",
        json={"semesterCodes": ["2025-2"], "candidates": [{"courseNumber": "10001"}]},
    )
    assert response.status_code == 401

    get_settings.cache_clear()
