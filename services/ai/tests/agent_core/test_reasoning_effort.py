"""Tests for `reasoning_effort.build_reasoning_config` (Dynamic Reasoning Effort)."""

from __future__ import annotations

from app.agent_core.reasoning_effort import TurnReasoningConfig, build_reasoning_config


def test_low_tier():
    cfg = build_reasoning_config("low")
    assert cfg.max_planner_invocations == 2
    assert cfg.subagent_thinking_enabled is False
    assert cfg.subagent_reasoning_effort is None
    assert cfg.subagent_timeout == 20.0
    assert cfg.static_subagent_timeout == 20.0


def test_medium_tier():
    cfg = build_reasoning_config("medium")
    assert cfg.max_planner_invocations == 3
    assert cfg.subagent_thinking_enabled is False


def test_high_tier():
    cfg = build_reasoning_config("high")
    assert cfg.max_planner_invocations == 4
    assert cfg.subagent_thinking_enabled is True
    assert cfg.subagent_reasoning_effort == "low"
    assert cfg.subagent_timeout == 45.0
    assert cfg.static_subagent_timeout == 45.0


def test_max_tier():
    cfg = build_reasoning_config("max")
    assert cfg.max_planner_invocations == 5
    assert cfg.subagent_thinking_enabled is True
    assert cfg.subagent_reasoning_effort == "medium"
    assert cfg.subagent_timeout == 45.0
    assert cfg.static_subagent_timeout == 45.0


def test_static_subagent_thinking_follows_the_tier_intent():
    """Measured live (2026-07-15): EVERY realistic question classifies `low` or
    `medium` -- never high/max. Both tiers set
    `subagent_thinking_enabled=False`, i.e. "do not think on this turn".

    But `task_handler.py` dispatches static subagents (Retrieval, Composition)
    with ONLY a timeout, so they fall through to the global default
    (`agent_llm_thinking_enabled: bool = True`). Net effect on the common path:
    thinking is explicitly OFF for the smart subagents and accidentally ON for
    retrieval -- the one that just fetches -- against a 20s ceiling. That is
    exactly backwards, and it is why `llm_call_failed` (httpx.ReadTimeout)
    clustered on retrieval steps.

    The tier's declared intent must reach the static subagents too."""
    for tier in ("low", "medium"):
        cfg = build_reasoning_config(tier)
        assert cfg.static_subagent_thinking_enabled is False, f"{tier}: retrieval must not think"
        assert cfg.static_subagent_thinking_enabled == cfg.subagent_thinking_enabled

    for tier in ("high", "max"):
        cfg = build_reasoning_config(tier)
        assert cfg.static_subagent_thinking_enabled == cfg.subagent_thinking_enabled


def test_static_subagent_timeout_scales_with_the_tier():
    """Retrieval/Composition are dispatched with ONLY a timeout (see
    `task_handler.py`'s static-subagent branch) -- no `thinking_enabled`, so
    they fall back to the global default (`agent_llm_thinking_enabled: bool =
    True` in config.py). A thinking model against a hard 20s read timeout gets
    cut off mid-response on hard turns: `httpx.ReadTimeout` ->
    `LLMAdapterError: llm_call_failed`, observed repeatedly in live evals on
    retrieval steps specifically -- they were the only ones that never got more
    time. Static timeouts must scale with the tier like dynamic ones do."""
    for tier in ("low", "medium"):
        cfg = build_reasoning_config(tier)
        assert cfg.static_subagent_timeout == cfg.subagent_timeout == 20.0

    for tier in ("high", "max"):
        cfg = build_reasoning_config(tier)
        assert cfg.static_subagent_timeout == cfg.subagent_timeout == 45.0, (
            f"{tier}: retrieval/composition must get the same headroom as dynamic subagents"
        )


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
        cfg.subagent_timeout = 999.0  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
