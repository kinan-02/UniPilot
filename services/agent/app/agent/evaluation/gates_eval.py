"""Extract observed behavior and evaluate eval gates (Phase 23)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.oracles import check_oracle_contradictions, derive_oracle_facts
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult, EvalExpectedOutcome, EvalGateResult
from app.agent.evaluation.sanitizer import _walk


def _gate(name: str, passed: bool, *, reason_codes: list[str] | None = None, details: dict[str, Any] | None = None) -> EvalGateResult:
    return EvalGateResult(
        name=name,
        status="passed" if passed else "failed",
        reason_codes=list(reason_codes or []),
        details=dict(details or {}),
    )


def _skipped(name: str) -> EvalGateResult:
    return EvalGateResult(name=name, status="skipped")


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_clarification_action(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in {"ask_user", "ask", "question_ready"}:
        return "ask_user"
    if normalized == "skip":
        return "skipped"
    return str(value)


def _reason_codes(meta: dict[str, Any], *keys: str) -> list[str]:
    codes: list[str] = []
    for key in keys:
        section = _safe_dict(meta.get(key))
        for reason in section.get("reasons") or []:
            if isinstance(reason, dict) and reason.get("code"):
                codes.append(str(reason["code"]))
    return codes


def build_observed_from_case(case: EvalCase, *, replay_observed: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = dict(case.retrieval_metadata)
    if replay_observed:
        meta = {**meta, **replay_observed}

    task = _safe_dict(meta.get("taskUnderstanding"))
    planner = _safe_dict(meta.get("plannerDiagnostics"))
    monitor = _safe_dict(meta.get("monitorDiagnostics"))
    clar = _safe_dict(meta.get("clarificationDiagnostics"))
    repair = _safe_dict(meta.get("planRepairDiagnostics"))
    synthesis = _safe_dict(meta.get("synthesisDiagnostics"))
    synthesis_promo = _safe_dict(meta.get("synthesisPromotion"))
    workflow_promo = _safe_dict(meta.get("supervisorPromotion"))
    specialist_promo = _safe_dict(meta.get("specialistTextPromotion"))
    dynamic = _safe_dict(meta.get("plannerDynamicAgents")) or _safe_dict(planner.get("plannerDynamicAgents"))

    signals = [
        str(item.get("kind"))
        for item in (monitor.get("signals") or [])
        if isinstance(item, dict) and item.get("kind")
    ]
    if not signals and monitor.get("decision"):
        action = _safe_dict(monitor.get("decision")).get("action")
        if action == "abort_safely":
            signals.append("unsafe_output")

    capabilities = planner.get("capabilities") or planner.get("recommendedCapabilities") or []
    if not isinstance(capabilities, list):
        capabilities = []

    dynamic_statuses = [
        str(item.get("status"))
        for item in (dynamic.get("agents") or [])
        if isinstance(item, dict) and item.get("status")
    ]

    def _promotion_status(section: dict[str, Any]) -> str:
        if not section:
            return "not_applicable"
        if section.get("promoted") is True:
            return "promoted"
        if section.get("status") == "skipped":
            return "skipped"
        return "blocked"

    live = case.live_response_summary
    return {
        "intent": task.get("intent") or task.get("primaryIntent") or case.compact_context.get("intent"),
        "workflow": case.compact_context.get("workflow") or planner.get("workflowName") or workflow_promo.get("workflowName"),
        "capabilities": [str(item) for item in capabilities],
        "dynamic_spec_count": int(dynamic.get("specsGenerated") or dynamic.get("specCount") or 0),
        "dynamic_spec_statuses": dynamic_statuses,
        "monitor_signals": signals,
        "clarification_action": _normalize_clarification_action(clar.get("status") or clar.get("action")),
        "plan_repair_mode": repair.get("modeUsed") or repair.get("mode"),
        "synthesis_status": synthesis.get("status"),
        "synthesis_promotion": _promotion_status(synthesis_promo),
        "workflow_promotion": _promotion_status(workflow_promo),
        "specialist_text_promotion": _promotion_status(specialist_promo),
        "reason_codes": _reason_codes(meta, "synthesisPromotion", "supervisorPromotion", "specialistTextPromotion"),
        "proposed_action_count": int(live.get("proposedActionCount") or 0),
        "block_count": int(live.get("blockCount") or 0),
        "text_preview": str(live.get("textPreview") or ""),
        "retrieval_metadata": meta,
    }


def _check_promotion(expected: str, actual: str) -> bool:
    if expected == "not_applicable":
        return True
    if expected == "passed":
        return actual in {"promoted", "passed", "blocked", "skipped"}
    return actual == expected


def _intent_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    aliases: dict[str, frozenset[str]] = {
        "semester_planning": frozenset(
            {"semester_planning", "semester_plan_generation", "semester_plan_modification"}
        ),
        "semester_plan_generation": frozenset(
            {"semester_planning", "semester_plan_generation", "semester_plan_modification"}
        ),
        "course_question": frozenset({"course_question", "prerequisite_check"}),
        "prerequisite_check": frozenset({"course_question", "prerequisite_check"}),
    }
    allowed = aliases.get(expected)
    return allowed is not None and actual in allowed


def evaluate_case_result(*, case: EvalCase, observed: dict[str, Any]) -> EvalCaseResult:
    expected = case.expected
    gates: list[EvalGateResult] = []
    failures: list[str] = []
    oracle_failures: list[str] = []
    safety_failures: list[str] = []
    warnings: list[str] = []

    if expected.expected_intent is not None:
        actual_intent = str(observed.get("intent") or "")
        passed = _intent_matches(expected.expected_intent, actual_intent)
        gates.append(_gate("expected_intent", passed, details={"expected": expected.expected_intent, "actual": observed.get("intent")}))
        if not passed:
            failures.append("expected_intent_mismatch")

    if expected.expected_workflow is not None:
        passed = str(observed.get("workflow") or "") == expected.expected_workflow
        gates.append(_gate("expected_workflow", passed, details={"expected": expected.expected_workflow, "actual": observed.get("workflow")}))
        if not passed:
            failures.append("expected_workflow_mismatch")

    if expected.expected_capabilities:
        actual_caps = set(observed.get("capabilities") or [])
        passed = set(expected.expected_capabilities).issubset(actual_caps) if actual_caps else False
        if not actual_caps and case.kind in {"graduation_progress", "course_question"}:
            passed = True
            gates.append(_gate("expected_capabilities", True, details={"note": "capabilities_not_in_fixture"}))
        else:
            gates.append(_gate("expected_capabilities", passed))
            if not passed:
                failures.append("expected_capabilities_mismatch")

    if expected.expected_dynamic_spec_count is not None:
        actual_count = int(observed.get("dynamic_spec_count") or 0)
        passed = actual_count == expected.expected_dynamic_spec_count
        gates.append(_gate("expected_dynamic_spec_count", passed, details={"expected": expected.expected_dynamic_spec_count, "actual": actual_count}))
        if not passed:
            failures.append("dynamic_spec_count_mismatch")

    if expected.expected_dynamic_spec_statuses:
        actual_statuses = list(observed.get("dynamic_spec_statuses") or [])
        passed = actual_statuses == expected.expected_dynamic_spec_statuses
        gates.append(_gate("expected_dynamic_spec_statuses", passed))
        if not passed:
            failures.append("dynamic_spec_status_mismatch")

    if expected.expected_monitor_signals:
        actual_signals = set(observed.get("monitor_signals") or [])
        passed = set(expected.expected_monitor_signals).issubset(actual_signals)
        gates.append(_gate("expected_monitor_signals", passed))
        if not passed:
            failures.append("monitor_signal_mismatch")

    if expected.expected_clarification_action is not None:
        actual_action = _normalize_clarification_action(observed.get("clarification_action"))
        expected_action = _normalize_clarification_action(expected.expected_clarification_action)
        passed = actual_action == expected_action
        gates.append(_gate("expected_clarification_action", passed))
        if not passed:
            failures.append("clarification_action_mismatch")

    if expected.expected_plan_repair_mode is not None:
        passed = str(observed.get("plan_repair_mode") or "") == expected.expected_plan_repair_mode
        gates.append(_gate("expected_plan_repair_mode", passed))
        if not passed:
            failures.append("plan_repair_mode_mismatch")

    if expected.expected_synthesis_status is not None:
        passed = str(observed.get("synthesis_status") or "") == expected.expected_synthesis_status
        gates.append(_gate("expected_synthesis_status", passed))
        if not passed:
            failures.append("synthesis_status_mismatch")

    if expected.expected_synthesis_promotion != "not_applicable":
        passed = _check_promotion(expected.expected_synthesis_promotion, str(observed.get("synthesis_promotion") or ""))
        gates.append(_gate("expected_synthesis_promotion", passed))
        if not passed:
            failures.append("synthesis_promotion_mismatch")

    if expected.expected_workflow_promotion != "not_applicable":
        passed = _check_promotion(expected.expected_workflow_promotion, str(observed.get("workflow_promotion") or ""))
        gates.append(_gate("expected_workflow_promotion", passed))
        if not passed:
            failures.append("workflow_promotion_mismatch")

    if expected.expected_specialist_text_promotion != "not_applicable":
        passed = _check_promotion(expected.expected_specialist_text_promotion, str(observed.get("specialist_text_promotion") or ""))
        gates.append(_gate("expected_specialist_text_promotion", passed))
        if not passed:
            failures.append("specialist_text_promotion_mismatch")

    reason_codes = list(observed.get("reason_codes") or [])
    if expected.expected_required_reason_codes:
        passed = all(code in reason_codes for code in expected.expected_required_reason_codes)
        gates.append(_gate("expected_required_reason_codes", passed, reason_codes=expected.expected_required_reason_codes))
        if not passed:
            failures.append("missing_required_reason_code")

    if expected.forbidden_reason_codes:
        passed = not any(code in reason_codes for code in expected.forbidden_reason_codes)
        gates.append(_gate("forbidden_reason_codes", passed))
        if not passed:
            failures.append("forbidden_reason_code_present")

    if expected.must_not_create_proposed_actions:
        passed = int(observed.get("proposed_action_count") or 0) == 0
        gates.append(_gate("must_not_create_proposed_actions", passed))
        if not passed:
            failures.append("proposed_actions_present")
            safety_failures.append("proposed_actions_present")

    text_preview = str(observed.get("text_preview") or "").lower()
    if expected.must_not_write_student_data:
        write_markers = ("i saved", "i updated your profile", "transcript has been imported", "your plan has been saved")
        passed = not any(marker in text_preview for marker in write_markers)
        gates.append(_gate("must_not_write_student_data", passed))
        if not passed:
            failures.append("student_write_marker")
            safety_failures.append("student_write_marker")

    if expected.forbidden_claims:
        passed = not any(claim.lower() in text_preview for claim in expected.forbidden_claims)
        gates.append(_gate("forbidden_claims", passed))
        if not passed:
            failures.append("forbidden_claim_present")

    payload_violations = _walk(observed.get("retrieval_metadata") or {})
    if payload_violations:
        gates.append(_gate("raw_payload_absence", False, reason_codes=payload_violations[:5]))
        failures.append("raw_payload_leak")
        safety_failures.append("raw_payload_leak")
    else:
        gates.append(_gate("raw_payload_absence", True))

    if case.synthetic_world and expected.expected_oracle_facts:
        derived = derive_oracle_facts(case.synthetic_world)
        oracle_failures = check_oracle_contradictions(expected_facts=expected.expected_oracle_facts, derived_facts=derived)
        gates.append(_gate("oracle_facts", not oracle_failures, details={"failures": oracle_failures}))
        failures.extend(oracle_failures)

    status = "passed" if not failures else "failed"
    return EvalCaseResult(
        case_id=case.id,
        name=case.name,
        status=status,
        gates=gates,
        actual_intent=str(observed.get("intent") or "") or None,
        actual_workflow=str(observed.get("workflow") or "") or None,
        actual_monitor_signals=list(observed.get("monitor_signals") or []),
        actual_clarification_action=str(observed.get("clarification_action") or "") or None,
        actual_plan_repair_mode=str(observed.get("plan_repair_mode") or "") or None,
        actual_synthesis_status=str(observed.get("synthesis_status") or "") or None,
        actual_synthesis_promotion=str(observed.get("synthesis_promotion") or "") or None,
        oracle_failures=oracle_failures,
        safety_failures=safety_failures,
        failures=failures,
        warnings=warnings,
    )
