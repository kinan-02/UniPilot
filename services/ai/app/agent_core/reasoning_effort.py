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
    # Static subagents (Retrieval, Composition)
    static_subagent_timeout: float


_CONFIGS: dict[str, TurnReasoningConfig] = {
    "low": TurnReasoningConfig(
        max_planner_invocations=2,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=20.0,
        static_subagent_timeout=20.0,
    ),
    "medium": TurnReasoningConfig(
        max_planner_invocations=3,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=20.0,
        static_subagent_timeout=20.0,
    ),
    "high": TurnReasoningConfig(
        max_planner_invocations=4,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="low",
        subagent_timeout=45.0,
        static_subagent_timeout=20.0,
    ),
    "max": TurnReasoningConfig(
        max_planner_invocations=5,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="medium",
        subagent_timeout=45.0,
        static_subagent_timeout=20.0,
    ),
}

_DEFAULT_TIER = "medium"


def build_reasoning_config(cognitive_complexity: str) -> TurnReasoningConfig:
    """Map a cognitive_complexity tier to concrete LLM parameters.

    Invalid or missing tiers default to 'medium'.
    """
    return _CONFIGS.get(cognitive_complexity, _CONFIGS[_DEFAULT_TIER])


__all__ = ["TurnReasoningConfig", "build_reasoning_config"]
