"""Unit tests for planner dynamic spec diagnostics (Phase 20)."""

from __future__ import annotations

from app.agent.planner.dynamic_spec_diagnostics import (
    build_planner_dynamic_agents_metadata,
    merge_planner_dynamic_execution_metadata,
)


def test_compact_planner_dynamic_agents_metadata_built() -> None:
    metadata = build_planner_dynamic_agents_metadata(
        {
            "status": "completed",
            "specsGenerated": 1,
            "specsValidated": 1,
            "specsRejected": 0,
            "agents": [{"specId": "spec_1", "agentName": "a", "status": "validated"}],
        }
    )
    assert metadata is not None
    assert metadata["status"] == "completed"


def test_generated_validated_rejected_counts_included() -> None:
    metadata = build_planner_dynamic_agents_metadata(
        {"status": "completed_with_warnings", "specsGenerated": 2, "specsValidated": 1, "specsRejected": 1}
    )
    assert metadata["specsGenerated"] == 2
    assert metadata["specsValidated"] == 1
    assert metadata["specsRejected"] == 1


def test_rejection_reasons_capped() -> None:
    metadata = build_planner_dynamic_agents_metadata(
        {"status": "rejected", "specsGenerated": 1, "rejectionReasons": [f"reason_{i}" for i in range(20)]}
    )
    assert len(metadata["rejectionReasons"]) <= 8


def test_raw_specs_omitted() -> None:
    metadata = build_planner_dynamic_agents_metadata(
        {
            "status": "completed",
            "specsGenerated": 1,
            "agents": [{"specId": "spec_1", "agentName": "a", "status": "validated"}],
        }
    )
    assert "dynamic_agent_spec" not in str(metadata)


def test_raw_planner_output_omitted() -> None:
    metadata = build_planner_dynamic_agents_metadata({"status": "skipped", "specsGenerated": 0})
    assert metadata is None


def test_raw_dynamic_output_omitted() -> None:
    metadata = merge_planner_dynamic_execution_metadata(
        {"status": "completed", "specsGenerated": 1, "specsValidated": 1, "agents": [{"specId": "spec_1"}]},
        {"status": "completed", "agentCount": 1, "agents": [{"specId": "spec_1", "status": "completed", "confidence": 0.8}]},
    )
    assert metadata is not None
    assert "result" not in str(metadata)


def test_no_chain_of_thought_fields() -> None:
    metadata = build_planner_dynamic_agents_metadata({"status": "completed", "specsGenerated": 1})
    dumped = str(metadata)
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in dumped
