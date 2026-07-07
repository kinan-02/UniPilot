"""Unit tests for synthesis input builder (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.input_builder import build_synthesis_input
from app.config import Settings


def test_builds_input_from_retrieval_metadata() -> None:
    inp = build_synthesis_input(
        user_goal="Graduate",
        normalized_request="What is missing?",
        live_response_summary={"textPreview": "You need 3 credits.", "workflowName": "graduation_progress_workflow"},
        retrieval_metadata={"monitorDiagnostics": {"status": "completed"}},
    )
    assert inp.synthesis_id.startswith("syn-")


def test_includes_workflow_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={"textPreview": "Hello", "blockCount": 2},
        retrieval_metadata={},
    )
    assert inp.workflow_summary["blockCount"] == 2


def test_includes_specialist_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={},
        retrieval_metadata={},
        supervisor_metadata={
            "specialistValidation": {
                "comparisons": [{"specialistAgentName": "graduation_progress_agent", "safeMatch": False}]
            }
        },
    )
    assert inp.specialist_summaries


def test_includes_dynamic_agent_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={},
        retrieval_metadata={},
        supervisor_metadata={"dynamicAgents": {"agents": [{"agentName": "dyn-1", "status": "completed"}]}},
    )
    assert inp.dynamic_agent_summaries


def test_includes_monitor_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={},
        retrieval_metadata={"monitorDiagnostics": {"status": "warning"}},
    )
    assert inp.monitor_summary["status"] == "warning"


def test_includes_clarification_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={},
        retrieval_metadata={"clarificationDiagnostics": {"status": "completed"}},
    )
    assert "clarificationDiagnostics" in inp.clarification_summary


def test_includes_plan_repair_summary() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={},
        retrieval_metadata={"planRepairDiagnostics": {"modeUsed": "repair"}},
    )
    assert inp.plan_repair_summary["modeUsed"] == "repair"


def test_omits_raw_context() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={"textPreview": "ok"},
        retrieval_metadata={"rawContext": {"blocks": [1, 2, 3]}},
    )
    assert "rawContext" not in str(inp.model_dump())


def test_omits_raw_blocks() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary={"textPreview": "ok", "blockTypes": ["table"]},
        retrieval_metadata={},
    )
    assert "blocks" not in inp.workflow_summary


def test_malformed_metadata_never_raises() -> None:
    inp = build_synthesis_input(
        user_goal=None,
        normalized_request=None,
        live_response_summary="bad",  # type: ignore[arg-type]
        retrieval_metadata="bad",  # type: ignore[arg-type]
        settings=Settings(AGENT_SYNTHESIS_MAX_EVIDENCE_ITEMS=2),
    )
    assert inp.synthesis_id
