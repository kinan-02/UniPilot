"""Tests for `reasoning_effort.build_reasoning_config` (Dynamic Reasoning Effort)."""

from __future__ import annotations

from app.agent_core.reasoning_effort import TurnReasoningConfig, build_reasoning_config


def test_low_tier():
    cfg = build_reasoning_config("low")
    assert cfg.max_planner_invocations == 2
    assert cfg.subagent_thinking_enabled is False
    assert cfg.subagent_reasoning_effort is None
    assert cfg.subagent_timeout == 45.0
    assert cfg.static_subagent_timeout == 45.0


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


def test_static_subagents_get_the_same_headroom_as_dynamic_ones():
    """Retrieval/Composition must never be the only subagents held to a tighter
    bound than the rest -- historically they were, and they were the only ones
    that timed out.

    This once asserted the static timeout SCALED with the tier (20s on
    low/medium, 45s on high/max), reasoning that only the thinking tiers needed
    headroom -- retrieval was then dispatched without `thinking_enabled`, fell
    back to the global `True`, and a thinking model got cut off by the 20s
    ceiling. Thinking is now passed explicitly (False on low/medium), so that
    premise is gone -- but 20s stayed, and was still wrong: measured live
    (2026-07-16) with thinking OFF, successful retrieval calls ran 1.4s-19.2s.
    The ceiling WAS the p99, so the tail died against it and was retried into
    the same wall (3 x 20s = 63s, then failed anyway).

    The invariant this test has always been about is PARITY: whatever bound a
    dynamic subagent gets, a static one gets too. The tier scales how much
    THINKING a call does, not how long the work is allowed to take."""
    for tier in ("low", "medium", "high", "max"):
        cfg = build_reasoning_config(tier)
        assert cfg.static_subagent_timeout == cfg.subagent_timeout, (
            f"{tier}: retrieval/composition must get the same headroom as dynamic subagents"
        )
        assert cfg.static_subagent_timeout == 45.0


def test_every_tier_bounds_its_own_retries():
    """`None` here does NOT mean "no retries" -- `llm_client.py` omits the kwarg
    entirely and the SDK's own default (2 retries = 3 attempts) applies, so a
    knob left unset silently MULTIPLIES the timeout above. Each tier must state
    its own bound for the same reason it must state `thinking_enabled`: whatever
    this config does not say, a global default says for it.

    Zero, because a retry here can only re-price failure, never avert it: past a
    timeout the second attempt hits the same wall as the first. Measured live --
    3 x 20s = 63s, then 2 x 45s = 91.7s, both failing. Recovery belongs to the
    Monitor's replan, which sees the whole plan; the adapter sees one call."""
    for tier in ("low", "medium", "high", "max"):
        cfg = build_reasoning_config(tier)
        assert cfg.subagent_max_retries == 0
        assert cfg.static_subagent_max_retries == 0


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
