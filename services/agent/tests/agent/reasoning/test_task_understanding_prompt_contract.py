"""Unit tests for the `task_understanding_v1` prompt contract (Phase 3)."""

from __future__ import annotations

from typing import get_args

from app.agent.reasoning.prompt_registry import (
    TASK_UNDERSTANDING_V1,
    build_default_prompt_registry,
)
from app.agent.reasoning.task_schemas import TASK_UNDERSTANDING_OUTPUT_SCHEMA
from app.agent.schemas import AgentIntent


def _full_prompt_text(contract) -> str:
    return " ".join([contract.role_prompt, *contract.instructions, *contract.safety_rules]).lower()


def test_prompt_registry_contains_task_understanding_v1():
    registry = build_default_prompt_registry()
    assert registry.has(TASK_UNDERSTANDING_V1)


def test_task_understanding_contract_has_expected_defaults():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)

    assert contract.default_risk_level == "medium"
    assert contract.default_min_iterations == 3
    assert contract.default_max_iterations == 3
    assert contract.output_schema_name == "task_understanding_output_v1"


def test_task_understanding_contract_declares_allowed_context_fields():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)

    expected = {
        "user_message",
        "conversation_summary",
        "recent_messages",
        "existing_entities",
        "existing_assumptions",
        "deterministic_intent",
        "deterministic_intent_confidence",
        "deterministic_entities",
        "user_profile_summary",
        "attachment_metadata",
        "supported_intents",
        "supported_workflows",
        "locale_hint",
    }
    assert contract.allowed_context_fields is not None
    assert set(contract.allowed_context_fields) == expected


def test_task_understanding_contract_has_no_chain_of_thought_instruction():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)
    text = _full_prompt_text(contract)

    assert "chain-of-thought" in text


def test_task_understanding_contract_forbids_inventing_academic_facts():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)
    text = _full_prompt_text(contract)

    for forbidden in (
        "invent academic requirements",
        "invent course facts",
        "invent transcript data",
        "invent completed courses",
    ):
        assert forbidden in text, f"missing forbidden-behavior instruction: {forbidden}"


def test_task_understanding_contract_forbids_running_tools_or_answering_directly():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)
    text = _full_prompt_text(contract)

    assert "run tools" in text
    assert "answer the user directly" in text
    assert "claim that a write action has happened" in text
    assert "choose unsupported intent values" in text


def test_task_understanding_contract_requires_valid_json_and_preserves_language():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)
    text = _full_prompt_text(contract)

    assert "valid json" in text
    assert "preserve the user's language" in text


def test_task_understanding_contract_mentions_only_supported_intents():
    registry = build_default_prompt_registry()
    contract = registry.get(TASK_UNDERSTANDING_V1)
    text = _full_prompt_text(contract)

    for intent in get_args(AgentIntent):
        assert intent in text


def test_task_understanding_output_schema_matches_taskunderstandingoutput_shape():
    from app.agent.task_understanding.schemas import TaskUnderstandingOutput

    schema_properties = set(TASK_UNDERSTANDING_OUTPUT_SCHEMA["properties"])
    model_fields = set(TaskUnderstandingOutput.model_fields)

    # `source` is Python-controlled (never produced by the LLM), so it is
    # intentionally absent from the schema the LLM must satisfy.
    assert schema_properties == model_fields - {"source"}


def test_task_understanding_output_schema_forbids_additional_properties():
    assert TASK_UNDERSTANDING_OUTPUT_SCHEMA["additionalProperties"] is False


def test_task_understanding_output_schema_leaves_intent_fields_unconstrained():
    """Intent values are validated in Python (normalizer), not via JSON-schema enum,
    so an unsupported LLM intent can be caught and reconciled rather than
    triggering a generic schema-repair retry."""
    properties = TASK_UNDERSTANDING_OUTPUT_SCHEMA["properties"]
    assert "enum" not in properties["primary_intent"]
    assert properties["primary_intent"]["type"] == "string"
