"""Turn-scoped reasoning effort configuration.

Maps the cognitive_complexity tier from the ComplexityClassifier into
concrete LLM parameters for each component in the agent pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnReasoningConfig:
    """Pre-computed reasoning parameters for the current turn.

    The Planner no longer takes per-tier thinking/effort/timeout knobs: it runs
    through the fixed-fast Planner Council (see planner_council.py), which sets
    each member's own params. Only its per-tier invocation budget survives here.
    """

    # Planner
    max_planner_invocations: int
    # Dynamic subagents (Interpretation, Calculation, Simulation)
    subagent_thinking_enabled: bool
    subagent_reasoning_effort: str | None
    subagent_timeout: float
    # Static subagents (Retrieval, Composition).
    #
    # These MUST be passed explicitly. `task_handler.py` used to dispatch them
    # with only a timeout, so `thinking_enabled` fell back to the global
    # `agent_llm_thinking_enabled` (True). Measured live (2026-07-15): every
    # realistic question classifies `low` or `medium`, and both tiers set
    # `subagent_thinking_enabled=False` -- so thinking was explicitly OFF for
    # the smart subagents and accidentally ON for retrieval, the one that only
    # fetches, against a 20s ceiling. Retrieval was the sole component doing
    # extended reasoning on the common path, and the sole one timing out
    # (httpx.ReadTimeout -> `llm_call_failed`). Exactly backwards.
    static_subagent_thinking_enabled: bool
    static_subagent_reasoning_effort: str | None
    static_subagent_timeout: float


_CONFIGS: dict[str, TurnReasoningConfig] = {
    "low": TurnReasoningConfig(
        max_planner_invocations=2,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=20.0,
        static_subagent_thinking_enabled=False,
        static_subagent_reasoning_effort=None,
        static_subagent_timeout=20.0,
    ),
    "medium": TurnReasoningConfig(
        max_planner_invocations=3,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=20.0,
        static_subagent_thinking_enabled=False,
        static_subagent_reasoning_effort=None,
        static_subagent_timeout=20.0,
    ),
    "high": TurnReasoningConfig(
        max_planner_invocations=4,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="low",
        subagent_timeout=45.0,
        static_subagent_thinking_enabled=True,
        static_subagent_reasoning_effort="low",
        static_subagent_timeout=45.0,
    ),
    "max": TurnReasoningConfig(
        max_planner_invocations=5,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="medium",
        subagent_timeout=45.0,
        static_subagent_thinking_enabled=True,
        static_subagent_reasoning_effort="medium",
        static_subagent_timeout=45.0,
    ),
}

_DEFAULT_TIER = "medium"


def build_reasoning_config(cognitive_complexity: str) -> TurnReasoningConfig:
    """Map a cognitive_complexity tier to concrete LLM parameters.

    Invalid or missing tiers default to 'medium'.
    """
    return _CONFIGS.get(cognitive_complexity, _CONFIGS[_DEFAULT_TIER])


__all__ = ["TurnReasoningConfig", "build_reasoning_config"]
