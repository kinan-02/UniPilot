"""Unit tests for dynamic agent safety (Phase 15)."""

from __future__ import annotations

from pathlib import Path

from app.agent.dynamic_agents.runtime import sanitize_reasoning_result
from app.agent.dynamic_agents.safety import scan_dynamic_agents_package_for_forbidden_tokens
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentRunOutput


def test_static_scan_finds_no_forbidden_tokens() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "dynamic_agents"
    violations = scan_dynamic_agents_package_for_forbidden_tokens(package_root=root)
    assert violations == []


def test_runtime_sanitize_strips_proposed_actions() -> None:
    sanitized, warnings = sanitize_reasoning_result(
        {"status": "completed", "proposed_actions": [{"type": "write"}], "decision_summary": "x", "confidence": 0.5}
    )
    assert sanitized["proposed_actions"] == []
    assert "dynamic_agent_proposed_actions_blocked" in warnings


def test_runtime_sanitize_strips_chain_of_thought_fields() -> None:
    sanitized, warnings = sanitize_reasoning_result(
        {"status": "completed", "chain_of_thought": "secret", "decision_summary": "x", "confidence": 0.5}
    )
    assert "chain_of_thought" not in sanitized
    assert any("forbidden_field_stripped" in warning for warning in warnings)


def test_dynamic_agent_output_forces_empty_proposed_actions() -> None:
    output = DynamicAgentRunOutput(
        status="completed",
        spec_id="s1",
        agent_name="a",
        decision_summary="done",
        confidence=0.5,
        proposed_actions=[{"type": "write"}],
    )
    assert output.proposed_actions == []


def test_agent_spec_shadow_only_default_true() -> None:
    spec = AgentSpec(
        spec_id="s",
        agent_name="a",
        role="r",
        objective="o",
        reasoning_pattern="single_pass",
        expected_output_schema_name="dynamic_agent_output_v1",
    )
    assert spec.shadow_only is True
