"""Unit tests for the Phase 6 `SupervisorBlackboard`."""

from __future__ import annotations

from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult


def _blackboard(**overrides) -> SupervisorBlackboard:
    defaults = dict(
        original_user_message="What am I missing to graduate?",
        task_understanding={"primaryIntent": "graduation_progress_check"},
        planner_output={
            "plan_id": "plan-1",
            "execution_mode": "single_capability",
            "primary_intent": "graduation_progress_check",
            "subtasks": [{"id": "a"}],
        },
        profile_summary={"degreeProgram": "BSc"},
    )
    defaults.update(overrides)
    return SupervisorBlackboard(**defaults)


def test_add_subtask_result_stores_result_and_capability_output() -> None:
    board = _blackboard()
    result = SubtaskResult(
        subtask_id="a",
        capability_name="graduation_progress_workflow",
        status="completed",
        output_summary={"dryRun": True},
    )
    board.add_subtask_result(result)

    assert board.subtask_results["a"].status == "completed"
    assert board.capability_results["graduation_progress_workflow"] == {"dryRun": True}


def test_dependency_outputs_retrieved_correctly() -> None:
    board = _blackboard()
    board.add_subtask_result(
        SubtaskResult(
            subtask_id="a",
            capability_name="cap_a",
            status="completed",
            output_summary={"value": 1},
        )
    )
    board.add_subtask_result(
        SubtaskResult(
            subtask_id="b",
            capability_name="cap_b",
            status="completed",
            output_summary={"value": 2},
        )
    )

    outputs = board.get_dependency_outputs(["a", "b", "does_not_exist"])
    assert outputs == {"a": {"value": 1}, "b": {"value": 2}}


def test_dependency_outputs_empty_for_no_ids() -> None:
    board = _blackboard()
    assert board.get_dependency_outputs([]) == {}


def test_warnings_and_errors_are_summarized() -> None:
    board = _blackboard()
    board.add_subtask_result(
        SubtaskResult(
            subtask_id="a",
            capability_name="cap_a",
            status="failed",
            error="boom",
            warnings=["careful"],
        )
    )
    summary = board.to_summary()
    assert "careful" in summary["warnings"]
    assert "boom" in summary["errors"]


def test_duplicate_warnings_and_errors_are_deduplicated() -> None:
    board = _blackboard()
    board.add_warning("dup")
    board.add_warning("dup")
    board.add_error("dup-error")
    board.add_error("dup-error")

    assert board.warnings.count("dup") == 1
    assert board.errors.count("dup-error") == 1


def test_raw_forbidden_fields_are_not_stored() -> None:
    board = _blackboard()
    board.add_subtask_result(
        SubtaskResult(
            subtask_id="a",
            capability_name="cap_a",
            status="completed",
            output_summary={
                "safe": "value",
                "raw_mongo_document": {"_id": "abc", "field": "should be stripped"},
                "attachment_contents": "base64-blob-should-be-stripped",
                "raw_pdf_bytes": b"%PDF binary blob",
            },
        )
    )

    stored = board.capability_results["cap_a"]
    assert stored["safe"] == "value"
    assert stored["raw_mongo_document"] == "<omitted: forbidden field>"
    assert "attachment_contents" not in str(stored) or stored.get("attachment_contents") != (
        "base64-blob-should-be-stripped"
    )
    # Binary values are never stored raw regardless of key name.
    assert b"%PDF binary blob" not in str(stored).encode(errors="ignore")


def test_summary_is_compact_and_capped() -> None:
    board = _blackboard()
    for i in range(200):
        board.add_warning(f"warning-{i}")

    summary = board.to_summary()
    assert len(summary["warnings"]) <= 50


def test_to_summary_shape() -> None:
    board = _blackboard()
    summary = board.to_summary()
    assert set(summary) == {
        "subtaskResultCount",
        "capabilitiesUsed",
        "warnings",
        "errors",
        "assumptions",
        "sources",
        "proposedActionCount",
        "validationNotes",
    }


def test_planner_output_stored_as_compact_summary_not_full_plan() -> None:
    board = _blackboard(
        planner_output={
            "plan_id": "plan-1",
            "execution_mode": "multi_capability_graph",
            "primary_intent": "graduation_progress_check",
            "subtasks": [{"id": "a"}, {"id": "b"}],
        }
    )
    assert board.planner_output == {
        "planId": "plan-1",
        "executionMode": "multi_capability_graph",
        "primaryIntent": "graduation_progress_check",
        "subtaskCount": 2,
    }
