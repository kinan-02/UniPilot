"""Main clarification capability runner (Phase 17)."""

from __future__ import annotations

from typing import Any

from app.agent.clarification.detector import dedupe_clarification_needs
from app.agent.clarification.fallbacks import build_assumed_answer, build_assumption_record
from app.agent.clarification.policy import decide_clarification_action
from app.agent.clarification.question_builder import batch_clarification_questions, build_clarification_question
from app.agent.clarification.schemas import (
    ClarificationCapabilityOutput,
    ClarificationNeed,
    ClarificationQuestion,
)


def run_clarification_capability(
    *,
    needs: list[ClarificationNeed],
    allow_user_questions: bool,
    max_questions: int = 3,
) -> ClarificationCapabilityOutput:
    """Process clarification needs deterministically. Never raises."""
    try:
        return _run(needs=needs, allow_user_questions=allow_user_questions, max_questions=max_questions)
    except Exception as exc:  # noqa: BLE001
        return ClarificationCapabilityOutput(
            status="failed",
            warnings=[f"clarification_capability_error:{type(exc).__name__}"],
            diagnostics={"errorType": type(exc).__name__},
        )


def run_clarification_from_shadow_context(
    *,
    monitor_metadata: dict[str, Any] | None,
    planner_output: dict[str, Any] | None,
    allow_user_questions: bool,
    max_questions: int,
) -> ClarificationCapabilityOutput:
    """Collect needs from monitor/planner diagnostics and run the capability."""
    from app.agent.clarification.detector import needs_from_missing_context, needs_from_monitor_output

    collected: list[ClarificationNeed] = []
    if monitor_metadata:
        collected.extend(needs_from_monitor_output(monitor_metadata))

    planner = planner_output if isinstance(planner_output, dict) else {}
    missing = planner.get("missing_context")
    if isinstance(missing, list):
        plan_id = planner.get("plan_id") or planner.get("planId")
        subtask_ids = [
            str(item.get("id"))
            for item in (planner.get("subtasks") or [])
            if isinstance(item, dict) and item.get("id")
        ]
        collected.extend(
            needs_from_missing_context(
                missing_context=[str(item) for item in missing],
                source="planner",
                affected_subtask_ids=subtask_ids,
                affected_plan_id=str(plan_id) if plan_id else None,
            )
        )

    return run_clarification_capability(
        needs=collected,
        allow_user_questions=allow_user_questions,
        max_questions=max_questions,
    )


def _run(
    *,
    needs: list[ClarificationNeed],
    allow_user_questions: bool,
    max_questions: int,
) -> ClarificationCapabilityOutput:
    safe_needs = [need for need in needs if isinstance(need, ClarificationNeed)]
    deduped = dedupe_clarification_needs(safe_needs)

    questions: list[ClarificationQuestion] = []
    answers = []
    assumptions: list[dict[str, Any]] = []
    warnings: list[str] = []
    resolved_count = 0
    assumed_count = 0
    skipped_count = 0

    for need in deduped:
        decision = decide_clarification_action(need)
        action = decision.action

        if action == "ask_user":
            if allow_user_questions:
                question = build_clarification_question(need, decision)
                if question is not None:
                    questions.append(question)
                else:
                    skipped_count += 1
            else:
                assumed = build_assumed_answer(need)
                if assumed is not None:
                    answers.append(assumed)
                    assumptions.append(build_assumption_record(need, assumed))
                    assumed_count += 1
                else:
                    skipped_count += 1
            continue

        if action == "assume_default":
            assumed = build_assumed_answer(need)
            if assumed is None and decision.selected_default:
                from app.agent.clarification.schemas import ClarificationAnswer

                assumed = ClarificationAnswer(
                    need_id=need.id,
                    value=decision.selected_default,
                    provenance="assumed",
                    source="fallback",
                    confidence=0.45,
                )
            if assumed is not None:
                answers.append(assumed)
                assumptions.append(build_assumption_record(need, assumed))
                assumed_count += 1
            else:
                skipped_count += 1
            continue

        if action == "resolve_epistemically":
            if bool(need.evidence.get("retrievableEpistemic")):
                resolved_count += 1
            else:
                assumed = build_assumed_answer(need)
                if assumed is not None:
                    answers.append(assumed)
                    assumptions.append(build_assumption_record(need, assumed))
                    assumed_count += 1
                else:
                    skipped_count += 1
            continue

        skipped_count += 1

    batched_questions, batch_warnings = batch_clarification_questions(
        questions,
        max_questions=max_questions,
    )
    warnings.extend(batch_warnings)

    status = _derive_status(
        question_count=len(batched_questions),
        assumed_count=assumed_count,
        resolved_count=resolved_count,
        skipped_count=skipped_count,
        total_needs=len(deduped),
    )

    return ClarificationCapabilityOutput(
        status=status,
        questions=batched_questions,
        answers=answers,
        assumptions_created=assumptions,
        warnings=warnings,
        diagnostics={
            "needCount": len(deduped),
            "questionCount": len(batched_questions),
            "assumedAnswerCount": assumed_count,
            "resolvedEpistemicCount": resolved_count,
            "skippedCount": skipped_count,
            "needs": [_compact_need_for_diagnostics(need) for need in deduped],
        },
    )


def _compact_need_for_diagnostics(need: ClarificationNeed) -> dict[str, Any]:
    return {
        "id": need.id,
        "source": need.source,
        "ambiguity_type": need.ambiguity_type,
        "consequence": need.consequence,
        "question_topic": need.question_topic,
        "reason": need.reason[:120],
        "options": list(need.options[:5]),
        "default_assumption": need.default_assumption,
    }


def _derive_status(
    *,
    question_count: int,
    assumed_count: int,
    resolved_count: int,
    skipped_count: int,
    total_needs: int,
) -> str:
    if question_count > 0:
        return "question_ready"
    if assumed_count > 0:
        return "assumed_default"
    if resolved_count > 0 and skipped_count == 0:
        return "resolved_epistemically"
    if total_needs == 0 or skipped_count == total_needs:
        return "skipped"
    if resolved_count > 0:
        return "resolved_epistemically"
    return "skipped"
