"""Unit tests for the Phase 15 dynamic agent prompt contract."""

from __future__ import annotations

from app.agent.reasoning.prompt_registry import DYNAMIC_AGENT_V1, build_default_prompt_registry
from app.agent.reasoning.task_schemas import DYNAMIC_AGENT_OUTPUT_SCHEMA


def _contract():
    return build_default_prompt_registry().get(DYNAMIC_AGENT_V1)


def test_dynamic_agent_v1_exists() -> None:
    assert build_default_prompt_registry().has(DYNAMIC_AGENT_V1)


def test_uses_dynamic_agent_output_schema() -> None:
    contract = _contract()
    assert contract.output_schema_name == "dynamic_agent_output_v1"
    assert DYNAMIC_AGENT_OUTPUT_SCHEMA["type"] == "object"
    assert "status" in DYNAMIC_AGENT_OUTPUT_SCHEMA["properties"]


def test_forbids_invented_academic_facts() -> None:
    joined = " ".join(_contract().instructions)
    assert "must not invent academic rules" in joined.lower() or "do not invent academic" in joined.lower()


def test_forbids_writes_and_proposed_actions() -> None:
    joined = " ".join(_contract().instructions).lower()
    assert "must not perform writes" in joined or "do not perform writes" in joined
    assert "proposed actions" in joined


def test_forbids_arbitrary_tools() -> None:
    joined = " ".join(_contract().instructions).lower()
    assert "arbitrary tools" in joined


def test_forbids_chain_of_thought_exposure() -> None:
    joined = " ".join([*_contract().instructions, *_contract().safety_rules]).lower()
    assert "chain-of-thought" in joined or "chain of thought" in joined


def test_requires_valid_json_only() -> None:
    joined = " ".join(_contract().instructions).lower()
    assert "valid json" in joined


def test_min_max_reasoning_iterations_are_appropriate() -> None:
    contract = _contract()
    assert contract.default_min_iterations == 2
    assert contract.default_max_iterations == 3
    assert contract.default_risk_level == "medium"
