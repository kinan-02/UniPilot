"""Tests for API-backed graduation progress projection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.graduation_progress_projection import resolve_projected_graduation_progress


class _StubEngine:
    _built = True
    course_catalog = {"00140008": {"general": {"נקודות": "3.5"}}}

    def __init__(self) -> None:
        import networkx as nx

        self.graph = nx.DiGraph()
        self.graph.add_node("00140008", credits="3.5")


@pytest.mark.asyncio
async def test_resolve_projected_graduation_progress_uses_api_when_available() -> None:
    baseline = {
        "completedCredits": 0.0,
        "totalRequiredCredits": 155.0,
        "creditsRemaining": 155.0,
        "remainingMandatoryCourses": [{"courseNumber": "00140008"}],
    }
    api_preview = {
        **baseline,
        "completedCredits": 3.5,
        "creditsRemaining": 151.5,
        "previewMeta": {"source": "api_recompute"},
    }

    with patch(
        "app.services.graduation_progress_projection.get_effector_gateway",
    ) as gateway_factory:
        gateway = AsyncMock()
        gateway.preview_graduation_progress = AsyncMock(return_value=api_preview)
        gateway_factory.return_value = gateway
        projected, source = await resolve_projected_graduation_progress(
            user_context={
                "user_id": "user-1",
                "graduation_progress": baseline,
                "completed_courses": [],
            },
            course_ids=["00140008"],
            engine=_StubEngine(),  # type: ignore[arg-type]
        )

    assert source == "api_recompute"
    assert projected is not None
    assert projected["completedCredits"] == 3.5


@pytest.mark.asyncio
async def test_resolve_projected_graduation_progress_falls_back_locally() -> None:
    baseline = {
        "completedCredits": 40.0,
        "totalRequiredCredits": 155.0,
        "creditsRemaining": 115.0,
        "remainingMandatoryCourses": [{"courseNumber": "00140008"}],
    }

    with patch(
        "app.services.graduation_progress_projection.get_effector_gateway",
    ) as gateway_factory:
        gateway = AsyncMock()
        gateway.preview_graduation_progress = AsyncMock(return_value=None)
        gateway_factory.return_value = gateway
        projected, source = await resolve_projected_graduation_progress(
            user_context={
                "user_id": "user-1",
                "graduation_progress": baseline,
                "completed_courses": [],
            },
            course_ids=["00140008"],
            engine=_StubEngine(),  # type: ignore[arg-type]
        )

    assert source == "local_projection"
    assert projected is not None
    assert projected["projectionMeta"]["source"] == "mas_variant_projection"
