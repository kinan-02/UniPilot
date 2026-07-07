"""Unit tests for planner dynamic spec prompt contract (Phase 20)."""

from __future__ import annotations

from app.agent.reasoning.prompt_registry import PLANNER_AGENT_V1, build_default_prompt_registry
from app.agent.reasoning.task_schemas import PLANNER_DYNAMIC_AGENT_SPEC_SCHEMA, PLANNER_SUBTASK_SCHEMA


def _contract():
    return build_default_prompt_registry().get(PLANNER_AGENT_V1)


def test_planner_agent_v1_mentions_dynamic_agent_spec() -> None:
    instructions = " ".join(_contract().instructions)
    assert "dynamic_agent_spec" in instructions


def test_prompt_forbids_writes() -> None:
    instructions = " ".join(_contract().instructions).lower()
    assert "write" in instructions
    assert "save" in instructions or "import" in instructions


def test_prompt_forbids_proposed_actions() -> None:
    instructions = " ".join(_contract().instructions)
    assert "action proposals" in instructions or "action proposal" in instructions


def test_prompt_requires_shadow_only_true() -> None:
    instructions = " ".join(_contract().instructions)
    assert "shadow_only=true" in instructions


def test_prompt_forbids_generated_code() -> None:
    instructions = " ".join(_contract().instructions).lower()
    assert "generate code" in instructions or "executable" in instructions


def test_planner_subtask_schema_allows_optional_dynamic_agent_spec() -> None:
    assert "dynamic_agent_spec" in PLANNER_SUBTASK_SCHEMA["properties"]


def test_dynamic_spec_schema_matches_phase15_agent_spec_fields() -> None:
    required = set(PLANNER_DYNAMIC_AGENT_SPEC_SCHEMA["required"])
    assert {"spec_id", "agent_name", "role", "objective", "reasoning_pattern", "expected_output_schema_name", "shadow_only"} <= required
