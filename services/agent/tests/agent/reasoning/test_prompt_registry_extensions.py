"""Unit tests for the Phase 2 role-specific prompt contracts."""

from __future__ import annotations

from app.agent.reasoning.prompt_registry import (
    ANSWER_VALIDATOR_V1,
    GENERIC_REASONING_BLOCK_V1,
    INTENT_CLASSIFIER_V1,
    PREFERENCE_EXTRACTOR_V1,
    RESPONSE_COMPOSER_V1,
    SCHEMA_REPAIR_V1,
    PromptContract,
    build_default_prompt_registry,
)

_PHASE_2_CONTRACT_NAMES = (
    INTENT_CLASSIFIER_V1,
    PREFERENCE_EXTRACTOR_V1,
    ANSWER_VALIDATOR_V1,
    RESPONSE_COMPOSER_V1,
)

# Every prompt contract must include rules equivalent to these (Phase 2 spec
# "Prompt safety requirements"). Checked case-insensitively as substrings of
# the concatenated role_prompt + instructions text.
_REQUIRED_SAFETY_SUBSTRINGS = (
    "chain-of-thought",
    "valid json",
    "supplied context",
    "do not invent",
    "write action",
    "missing",
    "language",
)


def _full_prompt_text(contract: PromptContract) -> str:
    return " ".join([contract.role_prompt, *contract.instructions, *contract.safety_rules]).lower()


def test_all_four_phase_2_contracts_are_registered():
    registry = build_default_prompt_registry()
    for name in _PHASE_2_CONTRACT_NAMES:
        assert registry.has(name), f"missing Phase 2 contract: {name}"


def test_phase_1_contracts_still_present_alongside_phase_2():
    registry = build_default_prompt_registry()
    assert registry.has(GENERIC_REASONING_BLOCK_V1)
    assert registry.has(SCHEMA_REPAIR_V1)


def test_each_phase_2_contract_declares_an_output_schema_name():
    registry = build_default_prompt_registry()
    for name in _PHASE_2_CONTRACT_NAMES:
        contract = registry.get(name)
        assert contract.output_schema_name
        assert contract.output_schema_name.endswith("_v1")


# ---------------------------------------------------------------------------
# Per-pass role differentiation (`pass_role_instructions`) — opt-in, additive
# ---------------------------------------------------------------------------


def test_no_shipped_contract_opts_into_pass_role_instructions():
    """Every contract shipped today must leave this unset — the mechanism is
    additive/opt-in, not something any existing contract has adopted yet."""
    registry = build_default_prompt_registry()
    for name in registry.names():
        assert registry.get(name).pass_role_instructions is None, name


def test_build_system_prompt_is_identical_across_passes_when_unset():
    from app.agent.reasoning.reasoning_block import _build_system_prompt
    from app.agent.reasoning.schemas import ReasoningBlockInput

    registry = build_default_prompt_registry()
    dummy_input = ReasoningBlockInput(
        block_id="blk-1",
        agent_name="test_agent",
        objective="test objective",
        output_schema_name="test_output_v1",
        output_schema={"type": "object"},
    )
    for name in registry.names():
        contract = registry.get(name)
        prompts = {
            _build_system_prompt(contract, dummy_input, pass_label=label)
            for label in ("understand", "draft", "final", None)
        }
        assert len(prompts) == 1, f"{name} should produce one identical prompt regardless of pass"


def test_build_system_prompt_differs_only_for_the_labeled_pass():
    from app.agent.reasoning.reasoning_block import _build_system_prompt
    from app.agent.reasoning.schemas import ReasoningBlockInput

    contract = PromptContract(
        name="test_contract_v1",
        version="1.0.0",
        role_prompt="You are a test agent.",
        output_schema_name="test_output_v1",
        pass_role_instructions={"draft": ["Check the previous pass for errors."]},
    )
    dummy_input = ReasoningBlockInput(
        block_id="blk-1",
        agent_name="test_agent",
        objective="test objective",
        output_schema_name="test_output_v1",
        output_schema={"type": "object"},
    )
    draft_prompt = _build_system_prompt(contract, dummy_input, pass_label="draft")
    understand_prompt = _build_system_prompt(contract, dummy_input, pass_label="understand")
    final_prompt = _build_system_prompt(contract, dummy_input, pass_label="final")

    assert "Check the previous pass for errors." in draft_prompt
    assert "Check the previous pass for errors." not in understand_prompt
    assert "Check the previous pass for errors." not in final_prompt


def test_each_phase_2_contract_includes_no_chain_of_thought_safety_rule():
    registry = build_default_prompt_registry()
    for name in _PHASE_2_CONTRACT_NAMES:
        contract = registry.get(name)
        text = _full_prompt_text(contract)
        assert "chain-of-thought" in text, f"{name} missing chain-of-thought safety rule"


def test_each_phase_2_contract_includes_all_required_safety_language():
    registry = build_default_prompt_registry()
    for name in _PHASE_2_CONTRACT_NAMES:
        contract = registry.get(name)
        text = _full_prompt_text(contract)
        missing = [s for s in _REQUIRED_SAFETY_SUBSTRINGS if s not in text]
        assert not missing, f"{name} missing required safety language: {missing}"


def test_intent_classifier_contract_matches_existing_intent_enum():
    from typing import get_args

    from app.agent.schemas import AgentIntent

    registry = build_default_prompt_registry()
    contract = registry.get(INTENT_CLASSIFIER_V1)
    for intent in get_args(AgentIntent):
        assert intent in contract.role_prompt


def test_response_composer_contract_forbids_mutating_deterministic_payload():
    registry = build_default_prompt_registry()
    contract = registry.get(RESPONSE_COMPOSER_V1)
    text = _full_prompt_text(contract)
    for forbidden in (
        "structured",
        "proposed actions",
        "numeric credit",
        "requirement statuses",
        "prerequisite statuses",
        "offering statuses",
        "transcript rows",
        "saved plan ids",
        "action ids",
    ):
        assert forbidden in text, f"response_composer_v1 missing constraint text: {forbidden}"


def test_preference_extractor_and_answer_validator_use_low_and_medium_risk_respectively():
    registry = build_default_prompt_registry()
    assert registry.get(PREFERENCE_EXTRACTOR_V1).default_risk_level == "low"
    assert registry.get(ANSWER_VALIDATOR_V1).default_risk_level == "medium"
    assert registry.get(INTENT_CLASSIFIER_V1).default_risk_level == "medium"
    assert registry.get(RESPONSE_COMPOSER_V1).default_risk_level == "low"


def test_entity_extractor_contract_is_registered_single_pass_low_risk():
    from app.agent.reasoning.prompt_registry import ENTITY_EXTRACTOR_V1

    registry = build_default_prompt_registry()
    assert registry.has(ENTITY_EXTRACTOR_V1)
    contract = registry.get(ENTITY_EXTRACTOR_V1)
    assert contract.output_schema_name == "entity_extractor_output_v1"
    assert contract.default_risk_level == "low"
    assert contract.default_min_iterations == 1
    assert contract.default_max_iterations == 1
