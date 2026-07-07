"""Unit tests for dynamic agent diagnostics (Phase 15)."""

from __future__ import annotations

from app.agent.dynamic_agents.diagnostics import (
    build_dynamic_agent_run_summary,
    build_dynamic_agents_diagnostics,
    build_dynamic_agents_metadata_from_subtask_summaries,
)
from app.agent.dynamic_agents.schemas import DynamicAgentRunOutput


def test_compact_diagnostics_built() -> None:
    metadata = build_dynamic_agents_diagnostics(
        agent_summaries=[
            {
                "specId": "spec_compare_001",
                "agentName": "semester_plan_comparison_agent",
                "reasoningPattern": "compare_and_synthesize",
                "blockCount": 4,
                "status": "completed",
                "confidence": 0.82,
                "warningCount": 1,
                "missingContextCount": 0,
            }
        ],
        warnings=["one"],
    )
    assert metadata is not None
    assert metadata["agentCount"] == 1


def test_diagnostics_include_spec_id_name_pattern_status() -> None:
    summary = build_dynamic_agent_run_summary(
        DynamicAgentRunOutput(
            status="completed",
            spec_id="spec_compare_001",
            agent_name="semester_plan_comparison_agent",
            decision_summary="done",
            confidence=0.82,
        ),
        reasoning_pattern="compare_and_synthesize",
        block_count=4,
    )
    assert summary["specId"] == "spec_compare_001"
    assert summary["reasoningPattern"] == "compare_and_synthesize"
    assert summary["status"] == "completed"


def test_diagnostics_omit_raw_output() -> None:
    metadata = build_dynamic_agents_metadata_from_subtask_summaries(
        [
            {
                "specId": "s1",
                "agentName": "a1",
                "reasoningPattern": "single_pass",
                "blockCount": 3,
                "status": "completed",
                "confidence": 0.5,
                "warningCount": 0,
                "missingContextCount": 0,
                "result": {"secret": "value"},
            }
        ]
    )
    assert metadata is not None
    assert "result" not in str(metadata)


def test_diagnostics_omit_raw_context() -> None:
    metadata = build_dynamic_agents_diagnostics(
        agent_summaries=[{"specId": "s", "agentName": "a", "reasoningPattern": "single_pass", "blockCount": 1, "status": "completed", "confidence": 0.1, "warningCount": 0, "missingContextCount": 0}],
        warnings=[],
    )
    assert "compiled_context" not in str(metadata)


def test_diagnostics_omit_raw_observations() -> None:
    metadata = build_dynamic_agents_diagnostics(
        agent_summaries=[{"specId": "s", "agentName": "a", "reasoningPattern": "single_pass", "blockCount": 1, "status": "completed", "confidence": 0.1, "warningCount": 0, "missingContextCount": 0}],
        warnings=[],
    )
    assert "deterministic_observations" not in str(metadata)


def test_diagnostics_omit_proposed_action_payloads() -> None:
    metadata = build_dynamic_agents_diagnostics(
        agent_summaries=[{"specId": "s", "agentName": "a", "reasoningPattern": "single_pass", "blockCount": 1, "status": "completed", "confidence": 0.1, "warningCount": 0, "missingContextCount": 0}],
        warnings=[],
    )
    assert "proposed_actions" not in str(metadata)


def test_diagnostics_cap_warnings() -> None:
    metadata = build_dynamic_agents_diagnostics(
        agent_summaries=[{"specId": "s", "agentName": "a", "reasoningPattern": "single_pass", "blockCount": 1, "status": "completed", "confidence": 0.1, "warningCount": 0, "missingContextCount": 0}],
        warnings=[f"w{i}" for i in range(20)],
    )
    assert metadata is not None
    assert len(metadata["warnings"]) <= 8
