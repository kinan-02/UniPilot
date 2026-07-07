"""Aggregate metrics for offline eval runs (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult, EvalRunSummary


def compute_eval_run_summary(results: list[EvalCaseResult], *, cases: list[EvalCase] | None = None) -> EvalRunSummary:
    case_by_id = {case.id: case for case in (cases or [])}
    total = len(results)
    passed = sum(1 for item in results if item.status == "passed")
    failed = sum(1 for item in results if item.status == "failed")
    errored = sum(1 for item in results if item.status == "error")
    executed = max(1, passed + failed)
    pass_rate = passed / executed if executed else 0.0

    intent_checks = [item for item in results if case_by_id.get(item.case_id) and case_by_id[item.case_id].expected.expected_intent]
    workflow_checks = [item for item in results if case_by_id.get(item.case_id) and case_by_id[item.case_id].expected.expected_workflow]

    intent_accuracy = None
    if intent_checks:
        intent_accuracy = sum(1 for item in intent_checks if "expected_intent_mismatch" not in item.failures) / len(intent_checks)

    workflow_accuracy = None
    if workflow_checks:
        workflow_accuracy = sum(1 for item in workflow_checks if "expected_workflow_mismatch" not in item.failures) / len(workflow_checks)

    dynamic_expected = sum(
        1 for case in (cases or []) if case.expected.expected_dynamic_spec_count is not None
    )
    dynamic_validated = sum(
        1
        for item in results
        if item.actual_synthesis_status in {"candidate_ready", "candidate_ready_with_warnings"}
        or any(g.name == "expected_dynamic_spec_count" and g.status == "passed" for g in item.gates)
    )
    dynamic_rejected = sum(1 for item in results if "dynamic_spec_status_mismatch" in item.failures)

    clar_expected = sum(1 for case in (cases or []) if case.expected.expected_clarification_action)
    clar_correct = sum(1 for item in results if "clarification_action_mismatch" not in item.failures and item.actual_clarification_action)

    repair_expected = sum(1 for case in (cases or []) if case.expected.expected_plan_repair_mode)
    repair_correct = sum(1 for item in results if "plan_repair_mode_mismatch" not in item.failures and item.actual_plan_repair_mode)

    synthesis_candidates = sum(
        1 for item in results if item.actual_synthesis_status in {"candidate_ready", "candidate_ready_with_warnings", "unsafe"}
    )
    synthesis_promotions = sum(1 for item in results if item.actual_synthesis_promotion == "promoted")
    synthesis_blocks = sum(1 for item in results if item.actual_synthesis_promotion == "blocked")

    unsafe_blocked = sum(
        1
        for item in results
        if item.actual_synthesis_status == "unsafe" or item.actual_synthesis_promotion == "blocked"
    )

    return EvalRunSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        errored_cases=errored,
        pass_rate=round(pass_rate, 4),
        intent_accuracy=round(intent_accuracy, 4) if intent_accuracy is not None else None,
        workflow_accuracy=round(workflow_accuracy, 4) if workflow_accuracy is not None else None,
        dynamic_specs_expected=dynamic_expected,
        dynamic_specs_validated=dynamic_validated,
        dynamic_specs_rejected=dynamic_rejected,
        clarification_questions_expected=clar_expected,
        clarification_questions_correct=clar_correct,
        plan_repair_expected=repair_expected,
        plan_repair_correct=repair_correct,
        synthesis_candidates=synthesis_candidates,
        synthesis_promotions=synthesis_promotions,
        synthesis_blocks=synthesis_blocks,
        unsafe_cases_blocked=unsafe_blocked,
        proposed_action_failures=sum(1 for item in results if "proposed_actions_present" in item.safety_failures),
        student_write_failures=sum(1 for item in results if "student_write_marker" in item.safety_failures),
        raw_payload_leak_failures=sum(1 for item in results if "raw_payload_leak" in item.safety_failures),
    )
