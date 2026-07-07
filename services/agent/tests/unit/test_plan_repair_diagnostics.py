"""Unit tests for plan repair diagnostics (Phase 19)."""

from __future__ import annotations

from app.agent.planner.repair_diagnostics import build_plan_repair_metadata
from app.agent.planner.repair_schemas import PlanExecutionDelta, PlanRepairOutput, PlanRepairRequest


def _output(**kwargs) -> PlanRepairOutput:
    defaults = {
        "status": "repaired",
        "mode_used": "repair",
        "decision_summary": "Repaired plan.",
        "preserved_subtask_ids": ["s1", "s2"],
        "revised_subtask_ids": ["s3"],
        "reason_codes": ["clarification_answered_repair"],
        "safe_to_use": False,
    }
    defaults.update(kwargs)
    return PlanRepairOutput(**defaults)  # type: ignore[arg-type]


def _request() -> PlanRepairRequest:
    return PlanRepairRequest(
        request_id="req-diag",
        user_goal="goal",
        deltas=[
            PlanExecutionDelta(
                delta_id="d1",
                source="clarification",
                kind="clarification_answered",
                summary="answered",
            )
        ],
    )


def test_compact_plan_repair_diagnostics_built() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert metadata["status"] == "repaired"
    assert metadata["modeUsed"] == "repair"


def test_delta_kinds_summarized() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert metadata["deltaKinds"] == ["clarification_answered"]


def test_counts_included() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert metadata["preservedSubtaskCount"] == 2
    assert metadata["revisedSubtaskCount"] == 1


def test_warnings_capped() -> None:
    metadata = build_plan_repair_metadata(
        _output(warnings=[f"w{i}" for i in range(20)]),
        request=_request(),
    )
    assert len(metadata["warnings"]) <= 8


def test_raw_plan_omitted() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert "repairedPlan" not in metadata
    assert "priorPlan" not in metadata


def test_raw_context_omitted() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert "compiled_context" not in str(metadata)


def test_raw_monitor_output_omitted() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    assert "monitorOutput" not in metadata


def test_no_chain_of_thought_fields() -> None:
    metadata = build_plan_repair_metadata(_output(), request=_request())
    dumped = str(metadata)
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in dumped
