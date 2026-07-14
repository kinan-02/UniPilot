"""Phase 0: the critic palette grows (strategy + domain) but nothing about
what actually RUNS changes yet. These tests pin (a) the two new contracts are
defined and registered, and (b) `_DEFAULT_CRITICS` is unchanged -- so Phase 0
is provably a no-behavior-change scaffolding step. Conditional SELECTION from
the enlarged palette lands in Phase 2.
"""

from __future__ import annotations

from app.agent_core.planning.planner_council import (
    COVERAGE_CRITIC_V1,
    CRITERIA_CRITIC_V1,
    DOMAIN_CRITIC_V1,
    GROUNDING_CRITIC_V1,
    PARSIMONY_CRITIC_V1,
    STRATEGY_CRITIC_V1,
    _DEFAULT_CRITICS,
    build_council_prompt_registry,
)


def test_strategy_and_domain_contracts_are_registered() -> None:
    registry = build_council_prompt_registry()
    assert registry.has(STRATEGY_CRITIC_V1)
    assert registry.has(DOMAIN_CRITIC_V1)


def test_new_contracts_have_narrow_single_job_role_prompts() -> None:
    registry = build_council_prompt_registry()
    strategy = registry.get(STRATEGY_CRITIC_V1)
    domain = registry.get(DOMAIN_CRITIC_V1)
    assert "Strategy Critic" in strategy.role_prompt
    assert "Domain" in domain.role_prompt
    # Both emit the shared critic output schema (a plain issues list).
    assert strategy.output_schema_name == "planner_critic_output_v1"
    assert domain.output_schema_name == "planner_critic_output_v1"


def test_default_critics_unchanged_in_phase_0() -> None:
    # The palette grew, but the DEFAULT set the council runs today has not --
    # this is the guarantee that Phase 0 changes no runtime behavior.
    assert _DEFAULT_CRITICS == (
        COVERAGE_CRITIC_V1,
        GROUNDING_CRITIC_V1,
        CRITERIA_CRITIC_V1,
        PARSIMONY_CRITIC_V1,
    )
    assert STRATEGY_CRITIC_V1 not in _DEFAULT_CRITICS
    assert DOMAIN_CRITIC_V1 not in _DEFAULT_CRITICS
