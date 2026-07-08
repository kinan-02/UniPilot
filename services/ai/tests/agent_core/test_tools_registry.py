"""Unit tests for `app.agent_core.tools` (docs/agent/AGENT_VISION.md §5, §5.1)."""

from __future__ import annotations

import pytest

from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolDescriptor, ToolNotFoundError, ToolRegistry

_ALL_TOOL_NAMES = {
    "get_entity",
    "search_knowledge",
    "traverse_relationship",
    "interpret_text",
    "extract_temporal_pattern",
    "apply_deterministic_rule",
    "mutate_state",
    "search_over_state",
    "compose_answer",
    "propose_action",
}


def test_default_registry_has_all_ten_primitives():
    registry = build_default_tool_registry()
    assert set(registry.names()) == _ALL_TOOL_NAMES


@pytest.mark.parametrize("tool_name", sorted(_ALL_TOOL_NAMES))
async def test_every_stub_returns_not_implemented(tool_name):
    registry = build_default_tool_registry()
    descriptor = registry.get(tool_name)
    # Build a minimally-valid input for whichever schema this tool declares.
    input_instance = descriptor.input_model.model_construct()
    envelope = await descriptor.callable(input_instance)
    assert envelope.ok is False
    assert envelope.error == f"not_implemented: {tool_name}"
    assert envelope.data is None


def test_get_unknown_tool_raises():
    registry = build_default_tool_registry()
    with pytest.raises(ToolNotFoundError):
        registry.get("does_not_exist")


def test_only_propose_action_may_declare_propose_side_effect():
    registry = ToolRegistry()

    async def _stub(payload):  # pragma: no cover -- never invoked
        raise AssertionError

    from pydantic import BaseModel

    class _Input(BaseModel):
        pass

    from app.agent_core.tools.envelope import ToolOutputEnvelope

    with pytest.raises(ValueError):
        registry.register(
            ToolDescriptor(
                name="not_propose_action",
                description="test",
                input_model=_Input,
                output_model=ToolOutputEnvelope,
                side_effect="propose",
                callable=_stub,
            )
        )


def test_duplicate_registration_without_overwrite_raises():
    registry = build_default_tool_registry()
    descriptor = registry.get("get_entity")
    with pytest.raises(ValueError):
        registry.register(descriptor)
    # overwrite=True is allowed
    registry.register(descriptor, overwrite=True)
