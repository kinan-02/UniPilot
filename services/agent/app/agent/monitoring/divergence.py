"""Deterministic divergence detection (Phase 16)."""

from __future__ import annotations

from typing import Any

from app.agent.monitoring.schemas import DivergenceSignal, MonitorInput, PlanAssumption, SubtaskExpectation

_PREFERENCE_AMBIGUITY_TAGS = frozenset(
    {
        "preference",
        "ambiguous",
        "clarification",
        "user_choice",
        "user_preference",
    }
)

_RETRIEVABLE_CONTEXT_TAGS = frozenset(
    {
        "catalog",
        "transcript",
        "profile",
        "requirement",
        "offering",
        "context",
        "retrieval",
    }
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _subtask_by_id(planner_output: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for raw in planner_output.get("subtasks") or []:
        if isinstance(raw, dict) and raw.get("id"):
            mapping[str(raw["id"])] = raw
    return mapping


def _record_for_subtask(records: list[dict[str, Any]], subtask_id: str) -> dict[str, Any] | None:
    for record in records:
        if str(record.get("subtask_id") or record.get("subtaskId") or "") == subtask_id:
            return record
    return None


def _has_proposed_actions(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    summary = record.get("result_summary") or record.get("output_summary") or {}
    if isinstance(summary, dict) and summary.get("hasProposedActions"):
        return True
    if isinstance(summary, dict) and summary.get("proposedActionCount", 0):
        return int(summary.get("proposedActionCount") or 0) > 0
    return False


def _confidence(record: dict[str, Any] | None) -> float:
    if not isinstance(record, dict):
        return 0.0
    summary = record.get("result_summary") or record.get("output_summary") or {}
    if isinstance(summary, dict) and summary.get("confidence") is not None:
        try:
            return float(summary.get("confidence"))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def detect_goal_drift(input: MonitorInput) -> DivergenceSignal | None:
    planner_goal = _normalize_text(input.user_goal or input.planner_output.get("user_goal"))
    latest = _normalize_text(input.latest_user_message)
    if not planner_goal or not latest:
        return None

    tu = input.task_understanding if isinstance(input.task_understanding, dict) else {}
    tu_goal = _normalize_text(tu.get("normalized_request") or tu.get("user_goal"))
    primary_intent = _normalize_text(input.planner_output.get("primary_intent"))
    tu_intent = _normalize_text(tu.get("primary_intent"))

    drift_evidence: dict[str, Any] = {}
    if latest and planner_goal and latest not in planner_goal and planner_goal not in latest:
        if len(latest.split()) >= 3 and len(planner_goal.split()) >= 3:
            drift_evidence["latestDiffersFromPlanGoal"] = True
    if tu_goal and planner_goal and tu_goal != planner_goal:
        drift_evidence["taskUnderstandingDiffersFromPlanGoal"] = True
    if tu_intent and primary_intent and tu_intent != primary_intent:
        drift_evidence["intentMismatch"] = True

    if not drift_evidence:
        return None

    return DivergenceSignal(
        kind="goal_drift",
        severity="error",
        message="Observed user goal or intent differs from the plan goal.",
        evidence=drift_evidence,
    )


def detect_assumption_violations(
    input: MonitorInput,
    assumptions: list[PlanAssumption],
) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    validation = input.validation_metadata if isinstance(input.validation_metadata, dict) else {}
    supervisor = input.supervisor_output if isinstance(input.supervisor_output, dict) else {}

    for assumption in assumptions:
        violated = False
        evidence: dict[str, Any] = {"assumptionId": assumption.id}

        if assumption.kind == "context_availability" and assumption.provenance in {"assumed", "inferred"}:
            missing = input.planner_output.get("missing_context") or []
            if missing and supervisor.get("status") == "completed":
                violated = True
                evidence["missingContextStillPresent"] = True

        if assumption.kind == "safety_constraint" and "unsafe_output" in assumption.invalidation_signals:
            if validation.get("liveProposedActionCount", 0) or validation.get("shadowProposedActionCount", 0):
                violated = True
                evidence["proposedActionsDetected"] = True

        if assumption.kind == "workflow_precondition" and assumption.provenance == "assumed":
            if supervisor.get("failed_subtasks") and assumption.consequence_if_wrong == "high":
                violated = True
                evidence["failedSubtasks"] = list(supervisor.get("failed_subtasks") or [])[:5]

        if violated:
            severity = "error" if assumption.consequence_if_wrong == "high" else "warning"
            signals.append(
                DivergenceSignal(
                    kind="assumption_violation",
                    severity=severity,
                    message=f"Assumption may no longer hold: {assumption.statement[:120]}",
                    related_assumption_ids=[assumption.id],
                    evidence=evidence,
                )
            )

    return signals


def detect_expectation_failures(
    input: MonitorInput,
    expectations: list[SubtaskExpectation],
) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    records = input.subtask_records if isinstance(input.subtask_records, list) else []
    subtasks = _subtask_by_id(input.planner_output)

    for expectation in expectations:
        if expectation.subtask_id == "*":
            if expectation.kind == "no_proposed_actions":
                if any(_has_proposed_actions(record) for record in records):
                    signals.append(
                        DivergenceSignal(
                            kind="unsafe_output",
                            severity="error",
                            message="Plan-level proposed actions detected.",
                            evidence={"expectationId": expectation.id},
                        )
                    )
            continue

        record = _record_for_subtask(records, expectation.subtask_id)
        if record is None:
            continue

        status = str(record.get("status") or "").strip().lower()
        summary = record.get("result_summary") or record.get("output_summary") or {}

        if expectation.kind == "status":
            allowed = (expectation.expected_value or {}).get("allowed") if isinstance(expectation.expected_value, dict) else None
            if allowed and status not in allowed and status == "failed":
                signals.append(
                    DivergenceSignal(
                        kind="local_execution_failure",
                        severity=expectation.severity_if_failed,
                        message=f"Subtask {expectation.subtask_id} failed.",
                        related_subtask_ids=[expectation.subtask_id],
                        evidence={"status": status, "expectationId": expectation.id},
                    )
                )

        if expectation.kind == "no_proposed_actions" and _has_proposed_actions(record):
            signals.append(
                DivergenceSignal(
                    kind="unsafe_output",
                    severity="error",
                    message=f"Subtask {expectation.subtask_id} reported proposed actions.",
                    related_subtask_ids=[expectation.subtask_id],
                    evidence={"expectationId": expectation.id},
                )
            )

        if expectation.kind == "confidence_threshold":
            threshold = float(expectation.expected_value or 0.0)
            if status == "completed" and _confidence(record) < threshold:
                signals.append(
                    DivergenceSignal(
                        kind="validation_failure",
                        severity=expectation.severity_if_failed,
                        message=f"Subtask {expectation.subtask_id} confidence below threshold.",
                        related_subtask_ids=[expectation.subtask_id],
                        evidence={"confidence": _confidence(record), "threshold": threshold},
                    )
                )

        if expectation.kind == "missing_context_absent":
            missing_count = 0
            if isinstance(summary, dict):
                missing_count = int(summary.get("missingContextCount") or 0)
            if missing_count > 0:
                signals.append(
                    DivergenceSignal(
                        kind="missing_context",
                        severity=expectation.severity_if_failed,
                        message=f"Subtask {expectation.subtask_id} still missing context.",
                        related_subtask_ids=[expectation.subtask_id],
                        evidence={"missingContextCount": missing_count},
                    )
                )

        subtask = subtasks.get(expectation.subtask_id, {})
        if status == "failed" and subtask.get("depends_on"):
            signals.append(
                DivergenceSignal(
                    kind="local_execution_failure",
                    severity="warning",
                    message=f"Dependent subtask {expectation.subtask_id} failed.",
                    related_subtask_ids=[expectation.subtask_id, *list(subtask.get("depends_on") or [])[:3]],
                    evidence={"failedDependencyChain": True},
                )
            )

    return signals


def detect_supervisor_divergence(input: MonitorInput) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    supervisor = input.supervisor_output if isinstance(input.supervisor_output, dict) else {}
    validation = input.validation_metadata if isinstance(input.validation_metadata, dict) else {}
    promotion = input.promotion_metadata if isinstance(input.promotion_metadata, dict) else {}

    status = str(supervisor.get("status") or "").strip().lower()
    if status == "budget_exceeded":
        signals.append(
            DivergenceSignal(
                kind="budget_exceeded",
                severity="error",
                message="Supervisor shadow run exceeded its execution budget.",
                evidence={"supervisorStatus": status},
            )
        )

    failed = list(supervisor.get("failed_subtasks") or supervisor.get("failedSubtasks") or [])
    if failed:
        signals.append(
            DivergenceSignal(
                kind="local_execution_failure",
                severity="warning",
                message="One or more shadow subtasks failed.",
                related_subtask_ids=[str(item) for item in failed[:8]],
                evidence={"failedSubtaskCount": len(failed)},
            )
        )

    if validation.get("status") == "failed" or validation.get("safeMatch") is False:
        signals.append(
            DivergenceSignal(
                kind="validation_failure",
                severity="warning",
                message="Shadow validation did not pass cleanly.",
                evidence={
                    "validationStatus": validation.get("status"),
                    "safeMatch": validation.get("safeMatch"),
                    "issueCount": len(validation.get("issues") or []),
                },
            )
        )

    if promotion.get("promoted") is False and promotion.get("status") not in {None, "skipped"}:
        issue_count = len(promotion.get("reasons") or promotion.get("issues") or [])
        severity = "info" if issue_count <= 1 else "warning"
        signals.append(
            DivergenceSignal(
                kind="promotion_blocked",
                severity=severity,
                message="Workflow promotion was blocked by existing safety gates.",
                evidence={"promotionStatus": promotion.get("status"), "issueCount": issue_count},
            )
        )

    specialist = input.specialist_validation_metadata if isinstance(input.specialist_validation_metadata, dict) else {}
    if specialist.get("status") == "failed" or specialist.get("safeToConsider") is False:
        signals.append(
            DivergenceSignal(
                kind="validation_failure",
                severity="warning",
                message="Specialist validation reported issues.",
                evidence={"specialistValidationStatus": specialist.get("status")},
            )
        )

    dynamic = input.dynamic_agent_metadata if isinstance(input.dynamic_agent_metadata, dict) else {}
    if dynamic.get("status") == "failed":
        signals.append(
            DivergenceSignal(
                kind="local_execution_failure",
                severity="warning",
                message="Dynamic agent diagnostics reported failure.",
                evidence={"dynamicAgentStatus": dynamic.get("status")},
            )
        )

    issues = validation.get("issues") or []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "").lower()
        severity = str(issue.get("severity") or "warning").lower()
        if "proposed_action" in code or "write" in code or "unsafe" in code:
            signals.append(
                DivergenceSignal(
                    kind="unsafe_output",
                    severity="error",
                    message="Validation reported unsafe output indicators.",
                    evidence={"issueCode": issue.get("code")},
                )
            )
        elif severity == "error":
            signals.append(
                DivergenceSignal(
                    kind="validation_failure",
                    severity="error",
                    message="Validation reported a critical issue.",
                    evidence={"issueCode": issue.get("code")},
                )
            )

    live_actions = int(validation.get("liveProposedActionCount") or 0)
    shadow_actions = int(validation.get("shadowProposedActionCount") or 0)
    if live_actions or shadow_actions:
        signals.append(
            DivergenceSignal(
                kind="unsafe_output",
                severity="error",
                message="Proposed action counts detected in validation metadata.",
                evidence={"liveProposedActionCount": live_actions, "shadowProposedActionCount": shadow_actions},
            )
        )

    return signals


def detect_missing_context(input: MonitorInput) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    missing_items = list(input.planner_output.get("missing_context") or [])
    clarification_questions = list(input.planner_output.get("clarification_questions") or [])

    for item in missing_items:
        text = str(item or "").strip().lower()
        if not text:
            continue
        tags = {token for token in text.replace("-", " ").split() if token}
        ambiguous = bool(tags & _PREFERENCE_AMBIGUITY_TAGS) or "which" in text or "prefer" in text
        signals.append(
            DivergenceSignal(
                kind="missing_context",
                severity="warning",
                message="Plan still has missing context.",
                evidence={
                    "missingContextItem": text[:80],
                    "preferenceAmbiguity": ambiguous,
                    "retrievableEpistemic": bool(tags & _RETRIEVABLE_CONTEXT_TAGS),
                },
            )
        )

    if clarification_questions:
        signals.append(
            DivergenceSignal(
                kind="missing_context",
                severity="info",
                message="Planner emitted clarification questions.",
                evidence={"clarificationQuestionCount": len(clarification_questions)},
            )
        )

    return signals


def detect_exhausted_path(input: MonitorInput, prior_signals: list[DivergenceSignal]) -> DivergenceSignal | None:
    validation = input.validation_metadata if isinstance(input.validation_metadata, dict) else {}
    supervisor = input.supervisor_output if isinstance(input.supervisor_output, dict) else {}

    validation_failures = [signal for signal in prior_signals if signal.kind == "validation_failure"]
    if supervisor.get("status") == "completed" and validation.get("safeMatch") is False and len(validation_failures) >= 2:
        return DivergenceSignal(
            kind="exhausted_path",
            severity="warning",
            message="Shadow execution completed but repeated validation failures suggest an exhausted path.",
            evidence={"validationFailureCount": len(validation_failures)},
        )
    return None


def detect_divergence(
    input: MonitorInput,
    assumptions: list[PlanAssumption],
    expectations: list[SubtaskExpectation],
) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []

    goal_drift = detect_goal_drift(input)
    if goal_drift is not None:
        signals.append(goal_drift)

    signals.extend(detect_assumption_violations(input, assumptions))
    signals.extend(detect_expectation_failures(input, expectations))
    signals.extend(detect_supervisor_divergence(input))
    signals.extend(detect_missing_context(input))

    exhausted = detect_exhausted_path(input, signals)
    if exhausted is not None:
        signals.append(exhausted)

    if not signals:
        signals.append(
            DivergenceSignal(
                kind="none",
                severity="info",
                message="No material divergence detected.",
            )
        )

    return _dedupe_signals(signals)


def _dedupe_signals(signals: list[DivergenceSignal]) -> list[DivergenceSignal]:
    seen: set[tuple[str, str]] = set()
    unique: list[DivergenceSignal] = []
    for signal in signals:
        key = (signal.kind, signal.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique
