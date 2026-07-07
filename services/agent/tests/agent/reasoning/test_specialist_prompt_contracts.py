"""Unit tests for the Phase 10 specialist-agent prompt contracts."""

from __future__ import annotations

import pytest

from app.agent.reasoning.prompt_registry import (
    SPECIALIST_COURSE_CATALOG_V1,
    SPECIALIST_GRADUATION_PROGRESS_V1,
    SPECIALIST_REQUIREMENT_EXPLANATION_V1,
    build_default_prompt_registry,
)
from app.agent.reasoning.task_schemas import (
    SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA,
    SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA,
    SPECIALIST_REQUIREMENT_EXPLANATION_OUTPUT_SCHEMA,
)

_ALL_CONTRACT_NAMES = (
    SPECIALIST_GRADUATION_PROGRESS_V1,
    SPECIALIST_COURSE_CATALOG_V1,
    SPECIALIST_REQUIREMENT_EXPLANATION_V1,
)

_SCHEMA_BY_CONTRACT_NAME = {
    SPECIALIST_GRADUATION_PROGRESS_V1: SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA,
    SPECIALIST_COURSE_CATALOG_V1: SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA,
    SPECIALIST_REQUIREMENT_EXPLANATION_V1: SPECIALIST_REQUIREMENT_EXPLANATION_OUTPUT_SCHEMA,
}

_EXPECTED_ALLOWED_CONTEXT_FIELDS = {
    "objective",
    "user_message",
    "compiled_context",
    "dependency_outputs",
    "deterministic_observations",
    "success_criteria",
    "validation_requirements",
}


def _contract(name: str):
    return build_default_prompt_registry().get(name)


# ---------------------------------------------------------------------------
# 1, 2, 3. Each contract exists in the default registry.
# ---------------------------------------------------------------------------


def test_specialist_graduation_progress_v1_exists() -> None:
    registry = build_default_prompt_registry()
    assert registry.has(SPECIALIST_GRADUATION_PROGRESS_V1)


def test_specialist_course_catalog_v1_exists() -> None:
    registry = build_default_prompt_registry()
    assert registry.has(SPECIALIST_COURSE_CATALOG_V1)


def test_specialist_requirement_explanation_v1_exists() -> None:
    registry = build_default_prompt_registry()
    assert registry.has(SPECIALIST_REQUIREMENT_EXPLANATION_V1)


# ---------------------------------------------------------------------------
# 4. Each contract uses a `ReasoningBlock` output schema (well-formed +
# matches the contract's declared output_schema_name).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_references_a_well_formed_output_schema(contract_name: str) -> None:
    contract = _contract(contract_name)
    schema = _SCHEMA_BY_CONTRACT_NAME[contract_name]

    assert schema["type"] == "object"
    assert "status" in schema["properties"]
    assert "decision_summary" in schema["properties"]
    assert "confidence" in schema["properties"]
    assert schema["additionalProperties"] is False
    assert contract.output_schema_name.startswith("specialist_")


# ---------------------------------------------------------------------------
# 5. Each contract forbids invented academic facts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_forbids_invented_academic_facts(contract_name: str) -> None:
    contract = _contract(contract_name)
    combined = " ".join(contract.instructions).lower()
    assert "invent academic rules" in combined
    assert "catalog facts" in combined
    assert "prerequisites" in combined
    assert "completed courses" in combined
    assert "degree requirements" in combined


# ---------------------------------------------------------------------------
# 6. Each contract forbids writes/proposed actions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_forbids_writes_and_proposed_actions(contract_name: str) -> None:
    contract = _contract(contract_name)
    combined = " ".join(contract.instructions).lower()
    assert "perform writes" in combined
    assert "create proposed actions" in combined
    assert "create action proposals" in combined
    assert "claim that a write happened" in combined


# ---------------------------------------------------------------------------
# 7. Each contract includes the no-chain-of-thought instruction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_includes_no_chain_of_thought_instruction(contract_name: str) -> None:
    contract = _contract(contract_name)
    combined = " ".join(contract.instructions).lower()
    assert "do not reveal chain-of-thought" in combined
    assert "expose chain-of-thought" in combined
    combined_safety = " ".join(contract.safety_rules).lower()
    assert "chain-of-thought" in combined_safety


# ---------------------------------------------------------------------------
# 8. Each contract requires valid JSON only.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_requires_valid_json_only(contract_name: str) -> None:
    contract = _contract(contract_name)
    combined = " ".join(contract.instructions).lower()
    assert "return only valid json matching the specialist output schema" in combined
    assert "return unstructured prose" in combined


# ---------------------------------------------------------------------------
# Extra: role prompt identifies the agent as a UniPilot specialist academic
# agent (per the Phase 10 spec's exact prompt requirement), scope, risk
# levels, and iteration counts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_role_prompt_identifies_specialist_academic_agent(contract_name: str) -> None:
    contract = _contract(contract_name)
    assert "You are a UniPilot specialist academic agent." in contract.role_prompt


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_forbids_scope_creep_and_invented_capabilities(contract_name: str) -> None:
    contract = _contract(contract_name)
    combined = " ".join(contract.instructions).lower()
    assert "solve only the assigned subtask" in combined
    assert "answer outside your assigned scope" in combined
    assert "invent capabilities" in combined
    assert "call unavailable tools" in combined


@pytest.mark.parametrize("contract_name", _ALL_CONTRACT_NAMES)
def test_each_contract_allowed_context_fields_match_specialist_input(contract_name: str) -> None:
    contract = _contract(contract_name)
    assert contract.allowed_context_fields is not None
    assert set(contract.allowed_context_fields) == _EXPECTED_ALLOWED_CONTEXT_FIELDS


def test_graduation_progress_risk_level_and_iterations() -> None:
    contract = _contract(SPECIALIST_GRADUATION_PROGRESS_V1)
    assert contract.default_risk_level == "high"
    assert contract.default_min_iterations == 3
    assert contract.default_max_iterations == 3


def test_course_catalog_risk_level_and_iterations() -> None:
    contract = _contract(SPECIALIST_COURSE_CATALOG_V1)
    assert contract.default_risk_level == "medium"
    assert contract.default_min_iterations == 3
    assert contract.default_max_iterations == 3


def test_requirement_explanation_risk_level_and_iterations() -> None:
    contract = _contract(SPECIALIST_REQUIREMENT_EXPLANATION_V1)
    assert contract.default_risk_level == "medium"
    assert contract.default_min_iterations == 3
    assert contract.default_max_iterations == 3
