"""Tests for `reasoning_effort.build_reasoning_config` (Dynamic Reasoning Effort)."""

from __future__ import annotations

from app.agent_core.reasoning_effort import TurnReasoningConfig, build_reasoning_config


def test_low_tier():
    cfg = build_reasoning_config("low")
    assert cfg.planner_thinking_enabled is False
    assert cfg.planner_reasoning_effort is None
    assert cfg.planner_timeout == 30.0
    assert cfg.max_planner_invocations == 2
    assert cfg.subagent_thinking_enabled is False
    assert cfg.subagent_reasoning_effort is None
    assert cfg.subagent_timeout == 20.0
    assert cfg.static_subagent_timeout == 20.0


def test_medium_tier():
    cfg = build_reasoning_config("medium")
    assert cfg.planner_thinking_enabled is True
    assert cfg.planner_reasoning_effort == "low"
    assert cfg.planner_timeout == 60.0
    assert cfg.max_planner_invocations == 3
    assert cfg.subagent_thinking_enabled is False


def test_high_tier():
    cfg = build_reasoning_config("high")
    assert cfg.planner_thinking_enabled is True
    assert cfg.planner_reasoning_effort == "medium"
    assert cfg.max_planner_invocations == 4
    assert cfg.subagent_thinking_enabled is True
    assert cfg.subagent_reasoning_effort == "low"
    assert cfg.subagent_timeout == 45.0


def test_max_tier():
    cfg = build_reasoning_config("max")
    assert cfg.planner_thinking_enabled is True
    assert cfg.planner_reasoning_effort == "high"
    assert cfg.planner_timeout == 90.0
    assert cfg.max_planner_invocations == 5
    assert cfg.subagent_thinking_enabled is True
    assert cfg.subagent_reasoning_effort == "medium"
    assert cfg.subagent_timeout == 45.0


def test_invalid_tier_defaults_to_medium():
    cfg = build_reasoning_config("banana")
    medium = build_reasoning_config("medium")
    assert cfg == medium


def test_empty_string_defaults_to_medium():
    cfg = build_reasoning_config("")
    medium = build_reasoning_config("medium")
    assert cfg == medium


def test_config_is_frozen():
    cfg = build_reasoning_config("low")
    try:
        cfg.planner_timeout = 999.0  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
