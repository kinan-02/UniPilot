"""Unit tests for `_record_tool_call`'s failure handling in orchestrator.py."""

from __future__ import annotations

import logging

import pytest

from app.agent import orchestrator
from app.config import Settings


@pytest.mark.asyncio
async def test_record_tool_call_logs_and_returns_none_on_failure(monkeypatch, caplog) -> None:
    async def _raising_create_agent_tool_call(*_args, **_kwargs):
        raise RuntimeError("mongo_write_failed")

    monkeypatch.setattr(orchestrator, "create_agent_tool_call", _raising_create_agent_tool_call)

    with caplog.at_level(logging.ERROR, logger="app.agent.orchestrator"):
        result = await orchestrator._record_tool_call(
            object(),
            run_id="run-1",
            user_id="user-1",
            conversation_id="conv-1",
            tool_name="context_builder",
            input_summary=None,
            settings=Settings(),
        )

    assert result is None
    assert any("agent_tool_call_record_failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_record_tool_call_returns_value_on_success(monkeypatch) -> None:
    async def _fake_create_agent_tool_call(*_args, **_kwargs):
        return {"id": "tool-call-1"}

    monkeypatch.setattr(orchestrator, "create_agent_tool_call", _fake_create_agent_tool_call)

    result = await orchestrator._record_tool_call(
        object(),
        run_id="run-1",
        user_id="user-1",
        conversation_id="conv-1",
        tool_name="context_builder",
        input_summary=None,
        settings=Settings(),
    )

    assert result == {"id": "tool-call-1"}
