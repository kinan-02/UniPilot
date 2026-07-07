"""Unit tests for Phase 11 specialist output validation (`specialists/validation.py`).

Exercises both a real `SpecialistAgentOutput` and its compact summary dict
shape (`specialists.output_summarizer.summarize_specialist_output`'s output
— what `SupervisorRunOutput.subtask_records[].result_summary` actually
holds).
"""

from __future__ import annotations

from app.agent.specialists.schemas import SpecialistAgentOutput
from app.agent.specialists.validation import validate_specialist_output


def _output(**overrides) -> SpecialistAgentOutput:
    defaults = dict(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="s1",
        result={"creditsRemaining": 40.0},
        decision_summary="You still need 40 credits.",
        confidence=0.9,
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


def _summary(**overrides) -> dict:
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


# ---------------------------------------------------------------------------
# 1. Valid completed specialist output passes.
# ---------------------------------------------------------------------------


def test_valid_completed_output_passes() -> None:
    result = validate_specialist_output(_output())

    assert result.status == "passed"
    assert result.safe_to_consider is True
    assert result.issues == []
    assert result.agent_name == "graduation_progress_agent"
    assert result.subtask_id == "s1"


def test_valid_completed_summary_passes() -> None:
    result = validate_specialist_output(_summary())

    assert result.status == "passed"
    assert result.safe_to_consider is True


# ---------------------------------------------------------------------------
# 2. Proposed actions fail validation.
# ---------------------------------------------------------------------------


def test_proposed_actions_fail_validation() -> None:
    # SpecialistAgentOutput itself always forces proposed_actions=[] (a
    # Pydantic field validator), so exercise the summary-shape path where a
    # caller could still set `hasProposedActions=True`.
    result = validate_specialist_output(_summary(hasProposedActions=True))

    assert result.status == "failed"
    assert result.safe_to_consider is False
    codes = [issue.code for issue in result.issues]
    assert "specialist_proposed_actions_detected" in codes


# ---------------------------------------------------------------------------
# 3. Forbidden raw context key fails validation.
# ---------------------------------------------------------------------------


def test_forbidden_raw_context_key_fails_validation() -> None:
    output = _output(result={"raw_context": {"secret": "value"}})

    result = validate_specialist_output(output)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "forbidden_specialist_payload_detected" in codes


def test_forbidden_key_in_diagnostics_fails_validation() -> None:
    result = validate_specialist_output(_output(), diagnostics={"compiled_context": {"x": 1}})

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "forbidden_specialist_payload_detected" in codes


# ---------------------------------------------------------------------------
# 4. Forbidden chain-of-thought key fails validation.
# ---------------------------------------------------------------------------


def test_forbidden_chain_of_thought_key_fails_validation() -> None:
    output = _output(result={"chain_of_thought": "step 1..."})

    result = validate_specialist_output(output)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "forbidden_specialist_payload_detected" in codes


def test_forbidden_scratchpad_key_fails_validation() -> None:
    output = _output(result={"scratchpad": "notes"})

    result = validate_specialist_output(output)

    assert result.status == "failed"


# ---------------------------------------------------------------------------
# 5. Low confidence gives warning and safe_to_consider=false.
# ---------------------------------------------------------------------------


def test_low_confidence_gives_warning() -> None:
    result = validate_specialist_output(_output(confidence=0.3))

    assert result.status == "passed_with_warnings"
    assert result.safe_to_consider is False
    codes = [issue.code for issue in result.issues]
    assert "low_specialist_confidence" in codes
    issue = next(i for i in result.issues if i.code == "low_specialist_confidence")
    assert issue.severity == "warning"


def test_confidence_out_of_range_fails() -> None:
    result = validate_specialist_output(_summary(confidence=1.5))

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "invalid_specialist_confidence" in codes


def test_missing_confidence_fails() -> None:
    result = validate_specialist_output(_summary(confidence=None))

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "invalid_specialist_confidence" in codes


# ---------------------------------------------------------------------------
# 6. Failed status does not raise and is not safe_to_consider.
# ---------------------------------------------------------------------------


def test_failed_status_does_not_raise_and_is_not_safe() -> None:
    output = _output(status="failed", confidence=0.0, result={}, decision_summary="unavailable")

    result = validate_specialist_output(output)

    assert result.status in ("passed_with_warnings", "failed", "skipped")
    assert result.safe_to_consider is False
    codes = [issue.code for issue in result.issues]
    assert "specialist_status_reported_failed" in codes


# ---------------------------------------------------------------------------
# 7. Missing context gives warning and safe_to_consider=false.
# ---------------------------------------------------------------------------


def test_missing_context_gives_warning() -> None:
    output = _output(missing_context=["completed_courses"])

    result = validate_specialist_output(output)

    assert result.status == "passed_with_warnings"
    assert result.safe_to_consider is False
    codes = [issue.code for issue in result.issues]
    assert "specialist_missing_context" in codes


# ---------------------------------------------------------------------------
# 8. Completed with empty result gives warning.
# ---------------------------------------------------------------------------


def test_completed_with_empty_result_gives_warning() -> None:
    output = _output(result={})

    result = validate_specialist_output(output)

    assert result.status == "passed_with_warnings"
    codes = [issue.code for issue in result.issues]
    assert "specialist_empty_result" in codes


# ---------------------------------------------------------------------------
# 9. Scope violation is detected conservatively.
# ---------------------------------------------------------------------------


def test_graduation_progress_agent_scope_violation_detected() -> None:
    output = _output(agent_name="graduation_progress_agent", result={"transcript_rows": []})

    result = validate_specialist_output(output)

    codes = [issue.code for issue in result.issues]
    assert "specialist_scope_violation_suspected" in codes


def test_course_catalog_agent_scope_violation_detected() -> None:
    output = _output(agent_name="course_catalog_agent", result={"saved_plan_id": "p1"})

    result = validate_specialist_output(output)

    codes = [issue.code for issue in result.issues]
    assert "specialist_scope_violation_suspected" in codes


def test_requirement_explanation_agent_scope_violation_detected() -> None:
    output = _output(agent_name="requirement_explanation_agent", result={"proposed_action": {}})

    result = validate_specialist_output(output)

    codes = [issue.code for issue in result.issues]
    assert "specialist_scope_violation_suspected" in codes


def test_no_scope_violation_for_normal_result_keys() -> None:
    output = _output(agent_name="graduation_progress_agent", result={"creditsRemaining": 40.0, "requirementProgress": []})

    result = validate_specialist_output(output)

    codes = [issue.code for issue in result.issues]
    assert "specialist_scope_violation_suspected" not in codes


# ---------------------------------------------------------------------------
# 10. Malformed output fails safely.
# ---------------------------------------------------------------------------


def test_malformed_output_fails_safely() -> None:
    result = validate_specialist_output("not a valid output")  # type: ignore[arg-type]

    assert result.status == "failed"
    assert result.safe_to_consider is False
    codes = [issue.code for issue in result.issues]
    assert "specialist_output_malformed" in codes


def test_none_output_fails_safely() -> None:
    result = validate_specialist_output(None)

    assert result.status == "failed"
    assert result.safe_to_consider is False


# ---------------------------------------------------------------------------
# 11. Validation never raises on unexpected input.
# ---------------------------------------------------------------------------


def test_never_raises_on_unexpected_input_types() -> None:
    for bad_input in (123, [1, 2, 3], object(), {"resultKeys": "not-a-list"}, {"confidence": "not-a-number"}):
        result = validate_specialist_output(bad_input)  # type: ignore[arg-type]
        assert result.status in ("failed", "passed", "passed_with_warnings", "skipped")
        assert result.safe_to_consider in (True, False)


def test_validation_disabled_returns_skipped() -> None:
    result = validate_specialist_output(_output(), validation_enabled=False)

    assert result.status == "skipped"
    assert result.safe_to_consider is False
    assert "specialist_validation_disabled" in result.warnings


def test_validation_result_never_contains_raw_payloads() -> None:
    long_text = "sensitive text " * 200
    output = _output(decision_summary=long_text, result={"creditsRemaining": 40.0})

    result = validate_specialist_output(output)

    result_text = str(result.model_dump())
    assert long_text not in result_text
