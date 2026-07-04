"""LLM-backed rolling summaries for advisor conversations (no raw transcript storage)."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.services.advisor_agent import _build_llm, _extract_json_object, _llm_base_url

HEBREW_RE = re.compile(r"[\u0590-\u05FF]")


class ConversationSummaryResult(BaseModel):
    title: str = Field(description="Short conversation title for history list.")
    summary: str = Field(
        description="Rolling summary of student questions and advisor answers so far."
    )


def _fallback_title(user_message: str) -> str:
    cleaned = " ".join(user_message.split())
    if not cleaned:
        return "Advisor chat"
    return cleaned[:72] + ("…" if len(cleaned) > 72 else "")


def _fallback_summary(
    previous_summary: str | None,
    user_message: str,
    advisor_answer: str,
) -> ConversationSummaryResult:
    user_line = " ".join(user_message.split())[:240]
    answer_line = " ".join(advisor_answer.split())[:400]
    if previous_summary and previous_summary.strip():
        summary = (
            f"{previous_summary.strip()}\n\n"
            f"Latest — Student: {user_line}\n"
            f"Advisor: {answer_line}"
        )
    else:
        summary = f"Student: {user_line}\nAdvisor: {answer_line}"
    return ConversationSummaryResult(
        title=_fallback_title(user_message),
        summary=summary[:4000],
    )


def _summary_messages(
    previous_summary: str | None,
    user_message: str,
    advisor_answer: str,
) -> list[Any]:
    language_hint = (
        "Write title and summary in Hebrew."
        if HEBREW_RE.search(user_message) or HEBREW_RE.search(advisor_answer or "")
        else "Write title and summary in English."
    )
    prior = previous_summary.strip() if previous_summary and previous_summary.strip() else ""
    system = SystemMessage(
        content=(
            "You maintain a concise rolling summary of a Technion academic advisor chat.\n"
            "Merge the new exchange into the prior summary.\n"
            "Capture: topics discussed, courses mentioned, eligibility conclusions, and open items.\n"
            "Do NOT invent facts beyond the exchange.\n"
            "Return JSON: {\"title\": string (<=80 chars), \"summary\": string (<=1200 chars)}.\n"
            f"{language_hint}"
        )
    )
    human = HumanMessage(
        content=json.dumps(
            {
                "previous_summary": prior or None,
                "new_exchange": {
                    "student_question": user_message,
                    "advisor_answer": advisor_answer,
                },
            },
            ensure_ascii=False,
        )
    )
    return [system, human]


def summarize_conversation_exchange(
    *,
    previous_summary: str | None,
    user_message: str,
    advisor_answer: str,
) -> ConversationSummaryResult:
    """Update the stored conversation summary after one advisor Q&A turn."""
    try:
        llm = _build_llm()
    except RuntimeError:
        return _fallback_summary(previous_summary, user_message, advisor_answer)

    if _llm_base_url():
        llm = llm.bind(response_format={"type": "json_object"})
        raw = llm.invoke(_summary_messages(previous_summary, user_message, advisor_answer))
        content = raw.content if isinstance(raw.content, str) else str(raw.content)
        data = _extract_json_object(content)
    else:
        structured = llm.with_structured_output(ConversationSummaryResult)
        result = structured.invoke(
            _summary_messages(previous_summary, user_message, advisor_answer)
        )
        if isinstance(result, ConversationSummaryResult):
            return result
        data = result if isinstance(result, dict) else {}

    title = str(data.get("title") or "").strip() or _fallback_title(user_message)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return _fallback_summary(previous_summary, user_message, advisor_answer)

    return ConversationSummaryResult(
        title=title[:80],
        summary=summary[:4000],
    )
