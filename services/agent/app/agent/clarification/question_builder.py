"""Compact user-facing clarification question builder (Phase 17)."""

from __future__ import annotations

import re
import uuid

from app.agent.clarification.schemas import (
    ClarificationDecision,
    ClarificationNeed,
    ClarificationQuestion,
)

_FORBIDDEN_PROMPT_MARKERS = (
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
)

_ID_PATTERN = re.compile(r"\b[a-f0-9]{8,}\b", re.IGNORECASE)


def build_clarification_question(
    need: ClarificationNeed,
    decision: ClarificationDecision,
) -> ClarificationQuestion | None:
    """Build a concise user-facing question when policy selects ask_user."""
    if decision.action != "ask_user":
        return None

    try:
        prompt = _build_prompt(need)
        if not prompt:
            return None

        return ClarificationQuestion(
            id=f"q_{uuid.uuid4().hex[:12]}",
            need_id=need.id,
            prompt=prompt,
            options=list(need.options),
            allow_free_text=True,
            consequence=need.consequence,
            ambiguity_type=need.ambiguity_type,
        )
    except Exception:  # noqa: BLE001
        return None


def batch_clarification_questions(
    questions: list[ClarificationQuestion],
    *,
    max_questions: int = 3,
) -> tuple[list[ClarificationQuestion], list[str]]:
    """Cap, prioritize, and deduplicate clarification questions."""
    warnings: list[str] = []
    if not questions:
        return [], warnings

    consequence_rank = {"high": 2, "medium": 1, "low": 0}
    deduped: dict[str, ClarificationQuestion] = {}
    for question in sorted(
        questions,
        key=lambda item: (-consequence_rank[item.consequence], item.id),
    ):
        topic_key = _topic_key(question.prompt)
        if topic_key not in deduped:
            deduped[topic_key] = question

    ordered = sorted(
        deduped.values(),
        key=lambda item: (-consequence_rank[item.consequence], item.id),
    )

    if len(ordered) > max_questions:
        warnings.append("clarification_questions_capped")

    return ordered[:max_questions], warnings


def _build_prompt(need: ClarificationNeed) -> str:
    topic = _sanitize_text(need.question_topic)
    if need.ambiguity_type == "preference":
        if need.options:
            option_text = " or ".join(_sanitize_text(option) for option in need.options[:3])
            return (
                f"To plan this correctly, I need one preference from you: "
                f"should I {option_text}?"
            )
        return f"To plan this correctly, I need one preference from you: {topic}?"

    if need.options:
        option_text = " / ".join(_sanitize_text(option) for option in need.options[:3])
        return f"Could you clarify {topic}? Options: {option_text}."

    return f"Could you clarify {topic}?"


def _sanitize_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = _ID_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:")
    for marker in _FORBIDDEN_PROMPT_MARKERS:
        cleaned = cleaned.replace(marker, "")
    return cleaned


def _topic_key(prompt: str) -> str:
    return _sanitize_text(prompt).lower()
