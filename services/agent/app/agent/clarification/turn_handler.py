"""Cross-turn clarification turn handling (Phase 18)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.clarification.answer_resolver import resolve_clarification_answer
from app.agent.clarification.diagnostics import build_clarification_state_metadata
from app.agent.clarification.question_selection import select_clarification_questions
from app.agent.clarification.resume import build_effective_context_text, resume_assumption_statements
from app.agent.clarification.schemas import ClarificationCapabilityOutput, ClarificationQuestion
from app.agent.clarification.state_machine import build_expired_resolution, should_expire_pending_state
from app.agent.clarification.state_schemas import PendingClarificationState, ResolvedClarificationState
from app.agent.clarification.user_facing import format_user_facing_clarification_text
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentResponse, IntentClassification, TaskPlan
from app.config import Settings
from app.repositories.clarification_state_repository import ClarificationStateRepository


@dataclass(frozen=True)
class TurnStartClarificationResult:
    effective_user_message: str
    resume_assumptions: list[str] = field(default_factory=list)
    state_metadata: dict[str, Any] | None = None
    early_response: AgentResponse | None = None
    skip_user_facing_offer: bool = False
    confirmed_clarification_answers: list[dict[str, Any]] = field(default_factory=list)
    clarification_assumptions_created: list[dict[str, Any]] = field(default_factory=list)
    original_user_message_for_resume: str | None = None


@dataclass(frozen=True)
class UserFacingClarificationOffer:
    response: AgentResponse | None = None
    state_metadata: dict[str, Any] | None = None


async def process_turn_start_clarification(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    user_message: str,
    run_id: str,
    settings: Settings,
) -> TurnStartClarificationResult:
    try:
        return await _process_turn_start_clarification(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=user_message,
            run_id=run_id,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 — must never break a live turn
        return TurnStartClarificationResult(
            effective_user_message=user_message,
            state_metadata={"status": "failed", "warnings": ["clarification_turn_start_error"]},
        )


async def _process_turn_start_clarification(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    user_message: str,
    run_id: str,
    settings: Settings,
) -> TurnStartClarificationResult:
    if not settings.is_agent_clarification_state_enabled():
        return TurnStartClarificationResult(effective_user_message=user_message)

    repo = ClarificationStateRepository(database, settings=settings)
    pending = await repo.get_active_for_conversation(conversation_id)
    if pending is None:
        return TurnStartClarificationResult(effective_user_message=user_message)

    pending = await repo.increment_pending_turn_count(pending.clarification_id) or pending

    if should_expire_pending_state(pending):
        expired = build_expired_resolution(pending)
        await _persist_resolution(repo, pending, expired)
        metadata = build_clarification_state_metadata(resolved=expired, pending=pending, expired=True)
        if expired.status == "assumed" and expired.resume_payload:
            assumptions = resume_assumption_statements(
                confirmed_answers=expired.answers,
                assumptions_created=expired.assumptions_created,
            )
            return TurnStartClarificationResult(
                effective_user_message=pending.original_user_message,
                resume_assumptions=assumptions,
                state_metadata=metadata,
                skip_user_facing_offer=True,
            )
        return TurnStartClarificationResult(
            effective_user_message=user_message,
            state_metadata=metadata,
            skip_user_facing_offer=True,
        )

    resolved = resolve_clarification_answer(pending_state=pending, user_message=user_message)
    if resolved is None:
        reminder = _build_reminder_response(
            pending=pending,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        metadata = build_clarification_state_metadata(
            pending=pending,
            warnings=["clarification_answer_unresolved"],
        )
        return TurnStartClarificationResult(
            effective_user_message=user_message,
            state_metadata=metadata,
            early_response=reminder,
            skip_user_facing_offer=True,
        )

    await _persist_resolution(repo, pending, resolved)
    metadata = build_clarification_state_metadata(resolved=resolved, pending=pending)

    if resolved.status == "cancelled":
        return TurnStartClarificationResult(
            effective_user_message=user_message,
            state_metadata=metadata,
            skip_user_facing_offer=True,
        )

    assumptions = resume_assumption_statements(
        confirmed_answers=resolved.answers,
        assumptions_created=resolved.assumptions_created,
    )
    return TurnStartClarificationResult(
        effective_user_message=pending.original_user_message,
        resume_assumptions=assumptions,
        state_metadata=metadata,
        skip_user_facing_offer=True,
        confirmed_clarification_answers=list(resolved.answers),
        clarification_assumptions_created=list(resolved.assumptions_created or []),
        original_user_message_for_resume=pending.original_user_message,
    )


async def offer_user_facing_clarification(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    run_id: str,
    original_user_message: str,
    clarification_output: ClarificationCapabilityOutput | None,
    live_response: AgentResponse,
    promoted_response: AgentResponse | None,
    task_plan: TaskPlan,
    classification: IntentClassification,
    planner_output: Any,
    settings: Settings,
) -> UserFacingClarificationOffer:
    if not _user_facing_enabled(settings):
        return UserFacingClarificationOffer()

    if clarification_output is None or clarification_output.status != "question_ready":
        return UserFacingClarificationOffer()

    if promoted_response is not None:
        return UserFacingClarificationOffer()

    if live_response.proposed_actions:
        return UserFacingClarificationOffer()

    questions = clarification_output.questions
    if not questions:
        return UserFacingClarificationOffer()

    if not _questions_eligible_for_user_facing(questions):
        return UserFacingClarificationOffer()

    selection = select_clarification_questions(
        questions,
        batching_enabled=settings.is_agent_clarification_batching_enabled(),
        max_questions_per_turn=settings.resolved_agent_clarification_max_questions_per_turn(),
    )
    selected_questions = selection.selected_questions
    selected_needs = _needs_for_questions(_needs_from_output(clarification_output), selected_questions)

    repo = ClarificationStateRepository(database, settings=settings)
    if await repo.get_active_for_conversation(conversation_id) is not None:
        return UserFacingClarificationOffer()

    if not settings.is_agent_clarification_state_enabled():
        text = format_user_facing_clarification_text(selected_questions)
        response = compose_response(
            conversation_id=conversation_id,
            message_id="",
            run_id=run_id,
            text=text,
            assumptions=[],
            used_sources=[],
        )
        metadata = build_clarification_state_metadata(
            pending=None,
            warnings=["clarification_state_disabled_no_persistence"],
            question_count=len(selected_questions),
            status="question_ready",
            deferred_question_count=selection.deferred_question_count,
            batching_enabled=selection.batching_enabled,
        )
        return UserFacingClarificationOffer(response=response, state_metadata=metadata)

    plan_id = None
    if planner_output is not None:
        plan_id = getattr(planner_output, "plan_id", None) or (
            planner_output.get("plan_id") if isinstance(planner_output, dict) else None
        )

    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message=original_user_message,
        questions=[_compact_question(question) for question in selected_questions],
        needs=selected_needs,
        original_plan_id=str(plan_id) if plan_id else None,
        original_intent=classification.intent,
        original_workflow_name=task_plan.workflow,
        compact_context={"questionCount": len(selected_questions)},
        diagnostics={"status": clarification_output.status},
        max_pending_turns=max(1, int(settings.agent_clarification_max_pending_turns)),
    )
    if pending is None:
        return UserFacingClarificationOffer()

    text = format_user_facing_clarification_text(selected_questions)
    response = compose_response(
        conversation_id=conversation_id,
        message_id="",
        run_id=run_id,
        text=text,
        assumptions=[],
        used_sources=[],
    )
    metadata = build_clarification_state_metadata(
        pending=pending,
        question_count=len(selected_questions),
        status="pending",
        deferred_question_count=selection.deferred_question_count,
        batching_enabled=selection.batching_enabled,
    )
    return UserFacingClarificationOffer(response=response, state_metadata=metadata)


def build_internal_clarification_context(
    *,
    original_user_message: str,
    confirmed_answers: list[dict[str, Any]],
    question_topics: dict[str, str] | None = None,
) -> str:
    return build_effective_context_text(
        original_user_message=original_user_message,
        confirmed_answers=confirmed_answers,
        question_topics=question_topics,
    )


async def _persist_resolution(
    repo: ClarificationStateRepository,
    pending: PendingClarificationState,
    resolved: ResolvedClarificationState,
) -> None:
    if resolved.status == "answered":
        await repo.mark_answered(
            pending.clarification_id,
            answers=resolved.answers,
            assumptions_created=resolved.assumptions_created,
        )
    elif resolved.status == "assumed":
        await repo.mark_assumed(
            pending.clarification_id,
            answers=resolved.answers,
            assumptions_created=resolved.assumptions_created,
        )
    elif resolved.status == "cancelled":
        await repo.cancel_active(pending.conversation_id)
    elif resolved.status == "expired":
        await repo.mark_expired(pending.clarification_id)


def _build_reminder_response(
    *,
    pending: PendingClarificationState,
    conversation_id: str,
    run_id: str,
) -> AgentResponse:
    prompt_lines: list[str] = []
    for item in pending.questions:
        if isinstance(item, dict):
            prompt = str(item.get("prompt") or "").strip()
            if prompt:
                prompt_lines.append(prompt)
    if not prompt_lines:
        try:
            questions = [ClarificationQuestion.model_validate(item) for item in pending.questions]
            prompt_lines = [question.prompt for question in questions]
        except Exception:  # noqa: BLE001
            prompt_lines = ["Please clarify your preference."]

    text = "I still need your clarification before I can continue.\n\n" + "\n\n".join(prompt_lines)
    return compose_response(
        conversation_id=conversation_id,
        message_id="",
        run_id=run_id,
        text=text,
        assumptions=[],
        used_sources=[],
    )


def _user_facing_enabled(settings: Settings) -> bool:
    return settings.is_agent_clarification_enabled() and settings.is_agent_clarification_user_facing_enabled()


def _questions_eligible_for_user_facing(questions: list[ClarificationQuestion]) -> bool:
    return any(
        question.ambiguity_type in {"preference", "mixed"} and question.consequence in {"medium", "high"}
        for question in questions
    )


def _compact_question(question: ClarificationQuestion) -> dict[str, Any]:
    return {
        "id": question.id,
        "need_id": question.need_id,
        "prompt": question.prompt,
        "options": list(question.options),
        "allow_free_text": question.allow_free_text,
        "consequence": question.consequence,
        "ambiguity_type": question.ambiguity_type,
    }


def _compact_need(need_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": need_dict.get("id"),
        "question_topic": need_dict.get("question_topic") or need_dict.get("questionTopic"),
        "default_assumption": need_dict.get("default_assumption") or need_dict.get("defaultAssumption"),
        "ambiguity_type": need_dict.get("ambiguity_type") or need_dict.get("ambiguityType"),
        "consequence": need_dict.get("consequence"),
        "source": need_dict.get("source"),
        "reason": need_dict.get("reason"),
    }


def _needs_for_questions(
    needs: list[dict[str, Any]],
    questions: list[ClarificationQuestion],
) -> list[dict[str, Any]]:
    selected_ids = {question.need_id for question in questions}
    matched = [_compact_need(need) for need in needs if str(need.get("id")) in selected_ids]
    if matched:
        return matched
    return [_compact_need(need) for need in needs[: len(questions)]]


def _needs_from_output(output: ClarificationCapabilityOutput) -> list[dict[str, Any]]:
    raw = output.diagnostics.get("needs")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []
