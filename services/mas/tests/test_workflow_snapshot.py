"""Unit tests for workflow snapshot helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.workflow.snapshot import workflow_snapshot


@pytest.mark.asyncio
async def test_workflow_snapshot_skips_without_session_id() -> None:
    board = Blackboard(goal="plan next semester")

    with patch(
        "app.orchestrator.workflow.snapshot.persist_blackboard_snapshot",
        new=AsyncMock(),
    ) as persist_snapshot:
        await workflow_snapshot(board, "goal_analyst")

    persist_snapshot.assert_not_awaited()
