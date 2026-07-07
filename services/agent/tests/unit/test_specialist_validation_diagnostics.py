"""Unit tests for Phase 11 diagnostics building (`specialists/diagnostics.py`)."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.specialists.diagnostics import (
    build_specialist_compare_diagnostics,
    build_specialist_validation_metadata,
)
from app.agent.specialists.validation_schemas import (
    SpecialistCompareDiagnostics,
    SpecialistOutputValidationResult,
    SpecialistValidationIssue,
    WorkflowSpecialistComparison,
)
from app.agent.supervisor.schemas import SubtaskExecutionRecord, SupervisorRunOutput


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="conv-1",
        message_id="",
        run_id="run-1",
        text="You still need 12 credits.",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={})],
        warnings=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _specialist_summary(**overrides) -> dict:
    defaults = dict(
        agentName="graduation_progress_agent",
        status="completed",
        confidence=0.9,
        keyFindingCount=1,
        warningCount=0,
        sourceCount=1,
        missingContextCount=0,
        hasProposedActions=False,
        resultKeys=["creditsRemaining"],
        decisionSummaryPreview="You still need 40 credits.",
    )
    defaults.update(overrides)
    return defaults


def _record(**overrides) -> SubtaskExecutionRecord:
    defaults = dict(
        subtask_id="ask_specialist",
        capability_name="graduation_progress_agent",
        status="completed",
        result_summary=_specialist_summary(),
    )
    defaults.update(overrides)
    return SubtaskExecutionRecord(**defaults)


def _shadow_output(*records: SubtaskExecutionRecord, **overrides) -> SupervisorRunOutput:
    defaults = dict(
        status="completed",
        plan_id="plan-1",
        execution_mode="single_capability",
        subtask_records=list(records),
        completed_subtasks=[r.subtask_id for r in records if r.status == "completed"],
    )
    defaults.update(overrides)
    return SupervisorRunOutput(**defaults)


# ---------------------------------------------------------------------------
# build_specialist_compare_diagnostics — basic behavior.
# ---------------------------------------------------------------------------


def test_returns_none_when_no_shadow_output() -> None:
    assert build_specialist_compare_diagnostics(shadow_run_output=None) is None


def test_returns_none_when_no_specialist_subtasks_present() -> None:
    shadow_output = _shadow_output(
        SubtaskExecutionRecord(
            subtask_id="s1", capability_name="graduation_progress_workflow", status="completed",
            result_summary={"dryRun": True},
        )
    )
    assert build_specialist_compare_diagnostics(shadow_run_output=shadow_output) is None


def test_builds_diagnostics_when_specialist_subtask_present() -> None:
    shadow_output = _shadow_output(_record())

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output,
        live_workflow_name="graduation_progress_workflow",
        live_response=_response(),
        validation_enabled=True,
        compare_enabled=True,
    )

    assert diagnostics is not None
    assert len(diagnostics.validation_results) == 1
    assert len(diagnostics.comparisons) == 1
    assert diagnostics.status == "passed"
    assert diagnostics.safe_to_consider is True


def test_compare_disabled_produces_no_comparisons() -> None:
    shadow_output = _shadow_output(_record())

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output,
        live_workflow_name="graduation_progress_workflow",
        live_response=_response(),
        validation_enabled=True,
        compare_enabled=False,
    )

    assert diagnostics is not None
    assert diagnostics.comparisons == []
    assert len(diagnostics.validation_results) == 1


def test_validation_disabled_gives_skipped_status() -> None:
    shadow_output = _shadow_output(_record())

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output, validation_enabled=False, compare_enabled=False
    )

    assert diagnostics is not None
    assert diagnostics.status == "skipped"
    assert diagnostics.safe_to_consider is False


# ---------------------------------------------------------------------------
# 1. Builds compact metadata.
# ---------------------------------------------------------------------------


def test_builds_compact_metadata_shape() -> None:
    diagnostics = SpecialistCompareDiagnostics(
        status="passed_with_warnings",
        safe_to_consider=False,
        validation_results=[
            SpecialistOutputValidationResult(
                status="passed_with_warnings",
                safe_to_consider=False,
                agent_name="graduation_progress_agent",
                subtask_id="s1",
                issues=[SpecialistValidationIssue(code="low_specialist_confidence", severity="warning", message="low")],
            )
        ],
        comparisons=[
            WorkflowSpecialistComparison(
                workflow_name="graduation_progress_workflow",
                specialist_agent_name="graduation_progress_agent",
                comparable=True,
                safe_match=True,
                live_block_types=["RequirementSummaryBlock"],
                specialist_result_keys=["creditsRemaining"],
                live_warning_count=0,
                specialist_warning_count=0,
            )
        ],
    )

    metadata = build_specialist_validation_metadata(diagnostics)

    assert metadata["status"] == "passed_with_warnings"
    assert metadata["safeToConsider"] is False
    assert metadata["validationCount"] == 1
    assert metadata["comparisonCount"] == 1
    assert metadata["issues"] == [{"code": "low_specialist_confidence", "severity": "warning"}]
    assert metadata["agents"] == ["graduation_progress_agent"]
    assert metadata["comparisons"] == [
        {
            "workflowName": "graduation_progress_workflow",
            "specialistAgentName": "graduation_progress_agent",
            "comparable": True,
            "safeMatch": True,
            "liveBlockTypes": ["RequirementSummaryBlock"],
            "specialistResultKeys": ["creditsRemaining"],
            "liveWarningCount": 0,
            "specialistWarningCount": 0,
        }
    ]


# ---------------------------------------------------------------------------
# 2. Caps issues if many exist.
# ---------------------------------------------------------------------------


def test_caps_issues_list() -> None:
    issues = [
        SpecialistValidationIssue(code=f"code-{i}", severity="warning", message="m") for i in range(30)
    ]
    diagnostics = SpecialistCompareDiagnostics(
        status="passed_with_warnings",
        validation_results=[
            SpecialistOutputValidationResult(
                status="passed_with_warnings", agent_name="graduation_progress_agent", issues=issues
            )
        ],
    )

    metadata = build_specialist_validation_metadata(diagnostics)

    assert len(metadata["issues"]) == 20


# ---------------------------------------------------------------------------
# 3. Includes agent names.
# ---------------------------------------------------------------------------


def test_includes_all_agent_names_sorted() -> None:
    diagnostics = SpecialistCompareDiagnostics(
        status="passed",
        validation_results=[
            SpecialistOutputValidationResult(status="passed", agent_name="requirement_explanation_agent"),
            SpecialistOutputValidationResult(status="passed", agent_name="course_catalog_agent"),
        ],
    )

    metadata = build_specialist_validation_metadata(diagnostics)

    assert metadata["agents"] == ["course_catalog_agent", "requirement_explanation_agent"]


# ---------------------------------------------------------------------------
# 4. Includes comparison summaries.
# ---------------------------------------------------------------------------


def test_includes_comparison_summaries_even_when_not_comparable() -> None:
    diagnostics = SpecialistCompareDiagnostics(
        status="passed",
        comparisons=[
            WorkflowSpecialistComparison(workflow_name="unknown_workflow", comparable=False, safe_match=False)
        ],
    )

    metadata = build_specialist_validation_metadata(diagnostics)

    assert metadata["comparisons"][0]["comparable"] is False


# ---------------------------------------------------------------------------
# 5, 6, 7. Omits raw result / raw context / raw response text.
# ---------------------------------------------------------------------------


def test_metadata_omits_raw_result_and_context_and_text() -> None:
    shadow_output = _shadow_output(_record(result_summary=_specialist_summary(decisionSummaryPreview="x" * 300)))

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output,
        live_workflow_name="graduation_progress_workflow",
        live_response=_response(text="y" * 5000),
        validation_enabled=True,
        compare_enabled=True,
    )
    assert diagnostics is not None
    metadata = build_specialist_validation_metadata(diagnostics)

    metadata_text = str(metadata)
    assert "y" * 5000 not in metadata_text
    assert "x" * 300 not in metadata_text
    for forbidden in ("raw_context", "compiled_context", "chain_of_thought", "scratchpad"):
        assert forbidden not in metadata_text


# ---------------------------------------------------------------------------
# 8. Forbidden payload scan catches bad diagnostics.
# ---------------------------------------------------------------------------


def test_forbidden_payload_in_specialist_summary_surfaces_as_issue() -> None:
    bad_summary = {**_specialist_summary(), "raw_context": {"secret": "value"}}
    shadow_output = _shadow_output(_record(result_summary=bad_summary))

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output, validation_enabled=True, compare_enabled=False
    )

    assert diagnostics is not None
    codes = [issue.code for result in diagnostics.validation_results for issue in result.issues]
    assert "forbidden_specialist_payload_detected" in codes
    assert diagnostics.status == "failed"
