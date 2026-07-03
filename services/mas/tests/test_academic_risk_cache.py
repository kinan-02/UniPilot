"""Unit tests for academic risk preview cache."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_risk_cache import (
    academic_risk_cache_key,
    get_cached_academic_risk,
    preload_academic_risk_cache,
)


def test_academic_risk_cache_key_is_order_invariant() -> None:
    assert academic_risk_cache_key(["b", "a"]) == academic_risk_cache_key(["a", "b"])


@pytest.mark.asyncio
async def test_preload_academic_risk_cache_stores_results() -> None:
    board = Blackboard(
        goal="plan",
        user_context={"user_id": "user-1", "plan_semester_code": "2025-1"},
    )
    proposals = [
        PlanProposal(course_ids=["00940139"], variant="primary"),
        PlanProposal(course_ids=["0940345"], variant="alternate"),
    ]

    async def _fake_fetch(**_kwargs):
        return {"summary": {"highSeverityCount": 0}, "risks": []}

    with patch(
        "app.services.academic_risk_cache.fetch_academic_risk_preview",
        new=AsyncMock(side_effect=_fake_fetch),
    ):
        await preload_academic_risk_cache(board, proposals)

    assert get_cached_academic_risk(board, ["00940139"]) is not None
    assert get_cached_academic_risk(board, ["0940345"]) is not None
