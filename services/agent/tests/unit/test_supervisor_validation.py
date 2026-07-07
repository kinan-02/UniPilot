"""Unit tests for the Phase 8 deterministic validation layer (`supervisor/validation.py`)."""

from __future__ import annotations

from app.agent.supervisor.schemas import SubtaskExecutionRecord, SupervisorRunOutput
from app.agent.supervisor.validation import validate_shadow_run
from app.agent.supervisor.validation_schemas import ShadowComparisonSummary


def _matching_comparison(**overrides) -> ShadowComparisonSummary:
    defaults = dict(
        live_workflow_name="graduation_progress_workflow",
        shadow_plan_id="plan-1",
        shadow_status="completed",
        live_block_types=["RequirementSummaryBlock"],
        shadow_block_types=["RequirementSummaryBlock"],
        live_block_count=1,
        shadow_block_count=1,
        live_warning_count=0,
        shadow_warning_count=0,
        live_proposed_action_count=0,
        shadow_proposed_action_count=0,
    )
    defaults.update(overrides)
    return ShadowComparisonSummary(**defaults)


def _shadow_output(**overrides) -> SupervisorRunOutput:
    defaults = dict(status="completed", plan_id="plan-1", execution_mode="single_capability")
    defaults.update(overrides)
    return SupervisorRunOutput(**defaults)


# ---------------------------------------------------------------------------
# 1. Validation passes when live/shadow structural summaries match.
# ---------------------------------------------------------------------------


def test_validation_passes_on_matching_comparison() -> None:
    result = validate_shadow_run(comparison=_matching_comparison())

    assert result.status == "passed"
    assert result.issues == []
    assert result.comparison is not None
    assert result.comparison.safe_match is True


# ---------------------------------------------------------------------------
# 2. Validation warns on block type mismatch.
# ---------------------------------------------------------------------------


def test_validation_warns_on_block_type_mismatch() -> None:
    comparison = _matching_comparison(shadow_block_types=["SomeOtherBlock"])

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed_with_warnings"
    codes = [issue.code for issue in result.issues]
    assert "shadow_block_type_mismatch" in codes
    assert all(issue.severity != "error" for issue in result.issues)


def test_validation_passes_when_both_sides_have_no_blocks() -> None:
    comparison = _matching_comparison(live_block_types=[], shadow_block_types=[], live_block_count=0, shadow_block_count=0)

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed"


def test_validation_warns_on_drastic_block_count_difference_with_matching_types() -> None:
    comparison = _matching_comparison(
        live_block_types=["RequirementSummaryBlock"],
        shadow_block_types=["RequirementSummaryBlock"],
        live_block_count=1,
        shadow_block_count=6,
    )

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed_with_warnings"
    assert any(issue.code == "shadow_block_type_mismatch" for issue in result.issues)


# ---------------------------------------------------------------------------
# 3. Validation warns on warning-count mismatch.
# ---------------------------------------------------------------------------


def test_validation_warns_on_warning_count_mismatch() -> None:
    comparison = _matching_comparison(live_warning_count=2, shadow_warning_count=0)

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed_with_warnings"
    codes = [issue.code for issue in result.issues]
    assert "warning_count_mismatch" in codes
    issue = next(issue for issue in result.issues if issue.code == "warning_count_mismatch")
    assert issue.severity == "warning"


# ---------------------------------------------------------------------------
# 4. Validation fails on proposed-action count mismatch.
# ---------------------------------------------------------------------------


def test_validation_fails_on_proposed_action_count_mismatch() -> None:
    comparison = _matching_comparison(live_proposed_action_count=1, shadow_proposed_action_count=0)

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "proposed_action_count_mismatch" in codes
    issue = next(issue for issue in result.issues if issue.code == "proposed_action_count_mismatch")
    assert issue.severity == "error"


# ---------------------------------------------------------------------------
# 5. Validation fails if shadow proposed actions are detected.
# ---------------------------------------------------------------------------


def test_validation_fails_when_shadow_proposed_actions_detected() -> None:
    comparison = _matching_comparison(
        live_proposed_action_count=1, shadow_proposed_action_count=1
    )

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "shadow_proposed_actions_detected" in codes
    # Counts matched (1 == 1) so the count-mismatch rule must not also fire.
    assert "proposed_action_count_mismatch" not in codes


# ---------------------------------------------------------------------------
# 6. Validation fails if unsafe capability execution is detected.
# ---------------------------------------------------------------------------


def test_validation_fails_when_unsafe_capability_execution_detected() -> None:
    comparison = _matching_comparison(unsafe_capabilities_attempted=["semester_planning_workflow"])

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "unsafe_capability_shadow_execution_detected" in codes


def test_validation_passes_when_unsafe_workflow_was_correctly_skipped() -> None:
    """Correctly skipping an unsafe capability (not attempting it) is safe."""
    comparison = _matching_comparison(
        shadow_status="completed_with_warnings",
        shadow_skipped_subtasks=["check_progress"],
        unsafe_capabilities_attempted=[],
    )

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed"


# ---------------------------------------------------------------------------
# 7 & 8. Validation fails if a forbidden raw/chain-of-thought key appears.
# ---------------------------------------------------------------------------


def test_validation_fails_on_forbidden_raw_context_key() -> None:
    result = validate_shadow_run(
        comparison=_matching_comparison(),
        diagnostics={"raw_context": {"secret": "value"}},
    )

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "forbidden_diagnostic_payload_detected" in codes


def test_validation_fails_on_forbidden_scratchpad_key_nested() -> None:
    result = validate_shadow_run(
        comparison=_matching_comparison(),
        diagnostics={"subtaskResultSummaries": {"s1": {"scratchpad": "hmm"}}},
    )

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "forbidden_diagnostic_payload_detected" in codes


def test_validation_fails_on_forbidden_chain_of_thought_key() -> None:
    result = validate_shadow_run(
        comparison=_matching_comparison(),
        diagnostics={"chain_of_thought": "step 1..."},
    )

    assert result.status == "failed"


def test_validation_passes_when_diagnostics_have_no_forbidden_keys() -> None:
    result = validate_shadow_run(
        comparison=_matching_comparison(),
        diagnostics={"budget": {"maxSubtasks": 20}, "blackboardSummary": {"warnings": []}},
    )

    assert result.status == "passed"


# ---------------------------------------------------------------------------
# 9. safe_to_promote is false for failed validation.
# ---------------------------------------------------------------------------


def test_safe_to_promote_false_when_validation_failed() -> None:
    comparison = _matching_comparison(live_proposed_action_count=1, shadow_proposed_action_count=0)

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "failed"
    assert result.safe_to_promote is False


def test_safe_to_promote_false_when_passed_with_warnings() -> None:
    comparison = _matching_comparison(shadow_block_types=["SomeOtherBlock"])

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed_with_warnings"
    assert result.safe_to_promote is False


def test_safe_to_promote_true_only_when_fully_passed_and_read_only() -> None:
    result = validate_shadow_run(comparison=_matching_comparison())

    assert result.status == "passed"
    assert result.safe_to_promote is True


def test_safe_to_promote_false_when_shadow_status_not_completed() -> None:
    comparison = _matching_comparison(shadow_status="cancelled")

    result = validate_shadow_run(comparison=comparison)

    # No issues fired (cancelled isn't failed/budget_exceeded), but
    # `safe_to_promote` still requires an actually-completed shadow run.
    assert result.status == "passed"
    assert result.safe_to_promote is False


# ---------------------------------------------------------------------------
# 10. safe_to_promote remains diagnostic and does not affect runtime behavior.
# ---------------------------------------------------------------------------


def test_safe_to_promote_is_a_plain_bool_field_not_wired_to_anything() -> None:
    result = validate_shadow_run(comparison=_matching_comparison())

    # It's just a field on a Pydantic model returned to the caller -- no
    # side effects, no global state, nothing else reads or reacts to it.
    assert isinstance(result.safe_to_promote, bool)
    dumped = result.model_dump()
    assert dumped["safe_to_promote"] == result.safe_to_promote


# ---------------------------------------------------------------------------
# Shadow execution failure rule.
# ---------------------------------------------------------------------------


def test_validation_fails_when_shadow_status_failed() -> None:
    comparison = _matching_comparison(shadow_status="failed", shadow_failed_subtasks=["check_progress"])

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "failed"
    codes = [issue.code for issue in result.issues]
    assert "shadow_execution_failed" in codes


def test_validation_warns_when_shadow_status_budget_exceeded() -> None:
    comparison = _matching_comparison(shadow_status="budget_exceeded")

    result = validate_shadow_run(comparison=comparison)

    assert result.status == "passed_with_warnings"
    issue = next(issue for issue in result.issues if issue.code == "shadow_execution_failed")
    assert issue.severity == "warning"


# ---------------------------------------------------------------------------
# Validation-disabled behavior.
# ---------------------------------------------------------------------------


def test_validation_disabled_returns_skipped_status_without_running_validators() -> None:
    comparison = _matching_comparison(live_proposed_action_count=1, shadow_proposed_action_count=5)

    result = validate_shadow_run(comparison=comparison, validation_enabled=False)

    assert result.status == "skipped"
    assert result.safe_to_promote is False
    assert result.issues == []
    assert result.comparison is comparison
