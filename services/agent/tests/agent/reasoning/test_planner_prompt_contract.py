"""Unit tests for the Phase 5 `planner_agent_v1` prompt contract."""

from __future__ import annotations

from app.agent.reasoning.prompt_registry import (
    PLANNER_AGENT_V1,
    build_default_prompt_registry,
)
from app.agent.reasoning.task_schemas import PLANNER_OUTPUT_SCHEMA


def _contract():
    return build_default_prompt_registry().get(PLANNER_AGENT_V1)


def test_planner_agent_v1_exists_in_default_registry() -> None:
    registry = build_default_prompt_registry()
    assert registry.has(PLANNER_AGENT_V1)


def test_planner_agent_v1_risk_is_high() -> None:
    assert _contract().default_risk_level == "high"


def test_planner_agent_v1_min_and_max_reasoning_iterations_are_three() -> None:
    contract = _contract()
    assert contract.default_min_iterations == 3
    assert contract.default_max_iterations == 3


def test_planner_agent_v1_references_planner_output_schema() -> None:
    contract = _contract()
    assert contract.output_schema_name == "planner_output_v1"
    # The schema itself must be a well-formed object schema for that output
    # name -- guards against the schema and contract silently drifting apart.
    assert PLANNER_OUTPUT_SCHEMA["type"] == "object"
    assert "subtasks" in PLANNER_OUTPUT_SCHEMA["properties"]


def test_planner_agent_v1_includes_no_chain_of_thought_instruction() -> None:
    contract = _contract()
    combined = " ".join(contract.instructions).lower()
    assert "do not reveal chain-of-thought" in combined
    assert any("expose chain-of-thought" in item.lower() for item in contract.instructions)


def test_planner_agent_v1_forbids_invented_academic_facts() -> None:
    contract = _contract()
    combined = " ".join(contract.instructions).lower()
    assert "invent academic requirements" in combined
    assert "invent course facts" in combined
    assert "invent transcript data" in combined
    assert "invent completed courses" in combined


def test_planner_agent_v1_forbids_invented_capabilities_and_tools() -> None:
    contract = _contract()
    combined = " ".join(contract.instructions).lower()
    assert "invent capabilities" in combined
    assert "invent tools" in combined


def test_planner_agent_v1_forbids_executing_workflows_or_tools() -> None:
    contract = _contract()
    combined = " ".join(contract.instructions).lower()
    assert "execute tools" in combined
    assert "execute workflows" in combined
    assert "create action proposals" in combined
    assert "answer the user directly" in combined


def test_planner_agent_v1_says_return_only_valid_json() -> None:
    contract = _contract()
    combined = " ".join(contract.instructions).lower()
    assert "return only valid json" in combined


def test_planner_agent_v1_allowed_context_fields_match_planner_input() -> None:
    contract = _contract()
    assert contract.allowed_context_fields is not None
    expected = {
        "user_message",
        "task_understanding",
        "deterministic_intent",
        "deterministic_entities",
        "conversation_entities",
        "conversation_assumptions",
        "capability_registry_summary",
        "legacy_workflow_plan",
        "profile_summary",
    }
    assert set(contract.allowed_context_fields) == expected
