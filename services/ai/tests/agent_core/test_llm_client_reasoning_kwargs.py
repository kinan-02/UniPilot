"""Unit tests for `llm_client._apply_reasoning_kwargs` -- the one place that
translates the abstract `thinking_enabled`/`reasoning_effort` intent every
reasoning-block caller expresses into a specific provider's wire format.
"""

from __future__ import annotations

from app.agent_core.reasoning.llm_client import _apply_reasoning_kwargs


def test_deepseek_thinking_disabled_sends_deepseek_specific_opt_out():
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="deepseek", thinking_enabled=False, reasoning_effort=None)
    assert kwargs == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_deepseek_thinking_enabled_sends_reasoning_effort_directly():
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="deepseek", thinking_enabled=True, reasoning_effort="medium")
    assert kwargs == {"reasoning_effort": "medium"}


def test_openai_thinking_disabled_sends_explicit_none_not_deepseek_field():
    # OpenAI doesn't recognize DeepSeek's opt-out shape -- must never receive
    # it. "Off" is expressed the OpenAI way, as reasoning_effort="none", sent
    # EXPLICITLY so the flag is not a silent no-op that leans on the provider
    # default (which for OpenAI is already "none", making an unset flag look
    # configurable while doing nothing).
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="openai", thinking_enabled=False, reasoning_effort=None)
    assert kwargs == {"reasoning_effort": "none"}


def test_openai_thinking_disabled_overrides_a_stray_effort():
    # thinking_enabled is the master switch: a leftover reasoning_effort must
    # not silently re-enable reasoning on a path the operator turned off.
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="openai", thinking_enabled=False, reasoning_effort="medium")
    assert kwargs == {"reasoning_effort": "none"}


def test_openai_thinking_enabled_sends_reasoning_effort_directly():
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="openai", thinking_enabled=True, reasoning_effort="medium")
    assert kwargs == {"reasoning_effort": "medium"}


def test_no_reasoning_effort_and_thinking_enabled_adds_nothing():
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="deepseek", thinking_enabled=True, reasoning_effort=None)
    assert kwargs == {}


def test_unknown_provider_falls_back_to_reasoning_effort_passthrough_only():
    # A provider not yet given its own branch still gets the portable
    # reasoning_effort mechanism -- never silently dropped, never crashes.
    kwargs: dict = {}
    _apply_reasoning_kwargs(kwargs, provider="some_future_provider", thinking_enabled=True, reasoning_effort="low")
    assert kwargs == {"reasoning_effort": "low"}
