"""Deterministic clarification answer resolution (Phase 18)."""

from __future__ import annotations

import re

from app.agent.clarification.fallbacks import build_assumption_record
from app.agent.clarification.resume import build_resume_payload
from app.agent.clarification.schemas import ClarificationAnswer
from app.agent.clarification.state_schemas import PendingClarificationState, ResolvedClarificationState

_CANCEL_PHRASES = (
    "cancel",
    "never mind",
    "nevermind",
    "skip",
    "stop",
    "forget it",
)

_NUMBER_WORDS = {
    "1": 0,
    "one": 0,
    "first": 0,
    "2": 1,
    "two": 1,
    "second": 1,
    "3": 2,
    "three": 2,
    "third": 2,
}


def resolve_clarification_answer(
    *,
    pending_state: PendingClarificationState,
    user_message: str,
) -> ResolvedClarificationState | None:
    """Resolve a user message against a pending clarification. Never raises."""
    try:
        return _resolve(pending_state=pending_state, user_message=user_message)
    except Exception:  # noqa: BLE001
        return None


def _resolve(
    *,
    pending_state: PendingClarificationState,
    user_message: str,
) -> ResolvedClarificationState | None:
    message = str(user_message or "").strip()
    if not message:
        return None

    lowered = message.lower()
    if any(phrase in lowered for phrase in _CANCEL_PHRASES):
        return ResolvedClarificationState(
            clarification_id=pending_state.clarification_id,
            conversation_id=pending_state.conversation_id,
            status="cancelled",
            warnings=["user_cancelled_clarification"],
        )

    questions = pending_state.questions
    if not questions:
        return None

    if len(questions) > 1:
        resolved = _resolve_multi_question(questions, message)
        if resolved is None:
            return None
        answers, warnings = resolved
    else:
        answer = _resolve_single_question(questions[0], message)
        if answer is None:
            return None
        answers = [answer]
        warnings = []

    assumptions = []
    for answer_dict in answers:
        need_id = str(answer_dict.get("need_id") or "")
        matching_need = next((need for need in pending_state.needs if str(need.get("id")) == need_id), None)
        if matching_need:
            answer = ClarificationAnswer.model_validate(answer_dict)
            from app.agent.clarification.schemas import ClarificationNeed

            need = ClarificationNeed.model_validate(matching_need)
            assumptions.append(build_assumption_record(need, answer))

    resume_payload = build_resume_payload(
        pending_state=pending_state,
        answers=answers,
        assumptions_created=assumptions,
    )

    return ResolvedClarificationState(
        clarification_id=pending_state.clarification_id,
        conversation_id=pending_state.conversation_id,
        status="answered",
        answers=answers,
        assumptions_created=assumptions,
        resume_payload=resume_payload,
        warnings=warnings,
    )


def _resolve_single_question(question: dict, message: str) -> dict | None:
    options = [str(item) for item in (question.get("options") or []) if str(item).strip()]
    need_id = str(question.get("need_id") or question.get("needId") or "")

    matched = _match_option(message, options)
    if matched is not None:
        return _confirmed_answer(need_id, matched)

    if question.get("allow_free_text", True) and not _looks_like_unrelated_question(message):
        if not options or len(options) <= 1:
            return _confirmed_answer(need_id, message)
        # Single-question turns may accept concise free-text answers even when options exist.
        if len(message.split()) <= 8:
            return _confirmed_answer(need_id, message)

    if options and _looks_like_unrelated_question(message):
        return None

    if options:
        return None

    if _looks_like_unrelated_question(message):
        return None

    return _confirmed_answer(need_id, message)


def _resolve_multi_question(
    questions: list[dict],
    message: str,
) -> tuple[list[dict], list[str]] | None:
    parts = [part.strip() for part in re.split(r"[;\n]+", message) if part.strip()]
    if len(parts) < len(questions):
        return None

    answers: list[dict] = []
    for question, part in zip(questions, parts, strict=False):
        answer = _resolve_single_question(question, part)
        if answer is None:
            return None
        answers.append(answer)
    return answers, ["multi_question_answered"]


def _match_option(message: str, options: list[str]) -> str | None:
    normalized = _normalize(message)
    if not normalized:
        return None

    if normalized in _NUMBER_WORDS and _NUMBER_WORDS[normalized] < len(options):
        return options[_NUMBER_WORDS[normalized]]

    exact_matches = [option for option in options if _normalize(option) == normalized]
    if len(exact_matches) == 1:
        return exact_matches[0]

    substring_matches = [option for option in options if _normalize(option) in normalized or normalized in _normalize(option)]
    if len(substring_matches) == 1:
        return substring_matches[0]

    return None


def _confirmed_answer(need_id: str, value: str) -> dict:
    answer = ClarificationAnswer(
        need_id=need_id or "unknown",
        value=value.strip(),
        provenance="confirmed",
        source="user",
        confidence=1.0,
    )
    return answer.model_dump()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _looks_like_unrelated_question(message: str) -> bool:
    lowered = message.lower().strip()
    return lowered.endswith("?") and not any(token in lowered for token in ("prefer", "prioritize", "choose", "option"))
