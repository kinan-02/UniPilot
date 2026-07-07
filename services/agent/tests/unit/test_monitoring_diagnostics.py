"""Unit tests for monitoring diagnostics (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.diagnostics import build_monitor_metadata
from app.agent.monitoring.schemas import DivergenceSignal, MonitorOutput, ReplanDecision


def _output(**overrides):
    defaults = dict(
        status="passed_with_warnings",
        plan_id="plan_123",
        signals=[DivergenceSignal(kind="missing_context", severity="warning", message="missing")],
        decision=ReplanDecision(
            action="request_plan_repair",
            reason="missing_epistemic_context",
            repair_scope="remaining_plan",
        ),
        checked_assumption_count=3,
        checked_expectation_count=7,
        warnings=["one"],
    )
    defaults.update(overrides)
    return MonitorOutput(**defaults)


def test_compact_metadata_built() -> None:
    metadata = build_monitor_metadata(_output())
    assert metadata["planId"] == "plan_123"
    assert metadata["checkedAssumptionCount"] == 3


def test_signal_list_capped() -> None:
    signals = [
        DivergenceSignal(kind="missing_context", severity="warning", message=str(i))
        for i in range(20)
    ]
    metadata = build_monitor_metadata(_output(signals=signals))
    assert len(metadata["signals"]) <= 8


def test_warnings_capped() -> None:
    metadata = build_monitor_metadata(_output(warnings=[f"w{i}" for i in range(20)]))
    assert len(metadata["warnings"]) <= 8


def test_raw_supervisor_output_omitted() -> None:
    metadata = build_monitor_metadata(_output())
    assert "supervisor_output" not in str(metadata)


def test_raw_planner_output_omitted() -> None:
    metadata = build_monitor_metadata(_output())
    assert "planner_output" not in str(metadata)


def test_raw_context_omitted() -> None:
    metadata = build_monitor_metadata(_output())
    assert "compiled_context" not in str(metadata)


def test_raw_blocks_omitted() -> None:
    metadata = build_monitor_metadata(_output())
    assert "blocks" not in str(metadata)


def test_proposed_action_payload_omitted() -> None:
    metadata = build_monitor_metadata(_output())
    assert "proposed_actions" not in str(metadata)


def test_no_chain_of_thought_fields() -> None:
    metadata = build_monitor_metadata(_output())
    text = str(metadata)
    assert "chain_of_thought" not in text
    assert "scratchpad" not in text
