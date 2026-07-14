"""The critic palette: six narrowly-specialized critics, of which the selector
activates a subset per invocation (selection itself is tested in
`test_critic_selector.py`). These tests pin that all six contracts are defined
and registered and that the palette lists them all.
"""

from __future__ import annotations

from app.agent_core.planning.critic_selector import CRITIC_PALETTE
from app.agent_core.planning.planner_council import (
    COVERAGE_CRITIC_V1,
    CRITERIA_CRITIC_V1,
    DOMAIN_CRITIC_V1,
    GROUNDING_CRITIC_V1,
    PARSIMONY_CRITIC_V1,
    STRATEGY_CRITIC_V1,
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


def test_palette_lists_all_six_critics() -> None:
    assert set(CRITIC_PALETTE) == {
        COVERAGE_CRITIC_V1,
        GROUNDING_CRITIC_V1,
        CRITERIA_CRITIC_V1,
        PARSIMONY_CRITIC_V1,
        STRATEGY_CRITIC_V1,
        DOMAIN_CRITIC_V1,
    }
