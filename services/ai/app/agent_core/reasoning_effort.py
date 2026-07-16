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
    # MUST be passed explicitly, for the same reason `thinking_enabled` must
    # (see below). `task_handler.py` set a timeout but left max_retries None,
    # which does NOT mean "no retries" -- `llm_client.py` simply omits the kwarg
    # and the SDK's own default (2 retries = 3 attempts) applies. So every
    # timeout was silently tripled.
    #
    # Measured live (2026-07-16): a retrieval call against the 20s ceiling below
    # burned 3 x 20s = 63s and then failed anyway -- 38% of that case's entire
    # 167s, spent producing nothing. Retrying a call that timed out because it
    # needs longer than the ceiling just fails again, more expensively.
    subagent_max_retries: int
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
    static_subagent_max_retries: int


# A subagent call's own time budget. 20.0 was measured (2026-07-16) to sit ON
# the tail rather than past it: successful retrieval calls that run ranged
# 1.4s-19.2s, so the slowest legitimate work was finishing with ~0.8s to spare
# and anything slower was killed mid-flight -- then retried into the same wall.
# A ceiling has to clear the work it is bounding; this one is the p99 itself.
# 45.0 is what the `high`/`max` tiers already allowed, so it is a bound this
# system is known to tolerate, not a new guess.
_SUBAGENT_TIMEOUT = 45.0

# No adapter-level retry. NOT "no recovery": a failed step goes to the Monitor,
# which replans with the whole plan in view -- real recovery lives there, one
# level up, and always has.
#
# The SDK's silent default of 2 (3 attempts) was measured (2026-07-16) turning a
# 20s ceiling into a 63s failure. Dropping to 1 and raising the ceiling to 45s
# did not fix it, it re-priced it: the next run spent 91.7s on a
# simulation_planning call that failed anyway (2 x 45s), where three doomed 20s
# attempts had cost 60s. Retrying past a timeout cannot work -- the second
# attempt hits the same wall as the first -- so every retry here is a doubling
# of the cost of failing, bought with nothing.
#
# A transient provider error (429/5xx) is the one case a retry would help; it
# costs a failed step and one Monitor replan instead, which is the path the
# orchestrator is built around and which carries context an adapter retry never
# has. That is the trade, made deliberately.
_SUBAGENT_MAX_RETRIES = 0

_CONFIGS: dict[str, TurnReasoningConfig] = {
    "low": TurnReasoningConfig(
        max_planner_invocations=2,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=_SUBAGENT_TIMEOUT,
        subagent_max_retries=_SUBAGENT_MAX_RETRIES,
        static_subagent_thinking_enabled=False,
        static_subagent_reasoning_effort=None,
        static_subagent_timeout=_SUBAGENT_TIMEOUT,
        static_subagent_max_retries=_SUBAGENT_MAX_RETRIES,
    ),
    "medium": TurnReasoningConfig(
        max_planner_invocations=3,
        subagent_thinking_enabled=False,
        subagent_reasoning_effort=None,
        subagent_timeout=_SUBAGENT_TIMEOUT,
        subagent_max_retries=_SUBAGENT_MAX_RETRIES,
        static_subagent_thinking_enabled=False,
        static_subagent_reasoning_effort=None,
        static_subagent_timeout=_SUBAGENT_TIMEOUT,
        static_subagent_max_retries=_SUBAGENT_MAX_RETRIES,
    ),
    "high": TurnReasoningConfig(
        max_planner_invocations=4,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="low",
        subagent_timeout=_SUBAGENT_TIMEOUT,
        subagent_max_retries=_SUBAGENT_MAX_RETRIES,
        static_subagent_thinking_enabled=True,
        static_subagent_reasoning_effort="low",
        static_subagent_timeout=_SUBAGENT_TIMEOUT,
        static_subagent_max_retries=_SUBAGENT_MAX_RETRIES,
    ),
    "max": TurnReasoningConfig(
        max_planner_invocations=5,
        subagent_thinking_enabled=True,
        subagent_reasoning_effort="medium",
        subagent_timeout=_SUBAGENT_TIMEOUT,
        subagent_max_retries=_SUBAGENT_MAX_RETRIES,
        static_subagent_thinking_enabled=True,
        static_subagent_reasoning_effort="medium",
        static_subagent_timeout=_SUBAGENT_TIMEOUT,
        static_subagent_max_retries=_SUBAGENT_MAX_RETRIES,
    ),
}

_DEFAULT_TIER = "medium"


def build_reasoning_config(cognitive_complexity: str) -> TurnReasoningConfig:
    """Map a cognitive_complexity tier to concrete LLM parameters.

    Invalid or missing tiers default to 'medium'.
    """
    return _CONFIGS.get(cognitive_complexity, _CONFIGS[_DEFAULT_TIER])


__all__ = ["TurnReasoningConfig", "build_reasoning_config"]
