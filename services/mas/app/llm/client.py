"""MAS-owned LLM client (independent from the ai service)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


def build_mas_llm(settings: Settings | None = None) -> ChatOpenAI:
    cfg = settings or get_settings()
    api_key = cfg.resolved_mas_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "MAS_OPENAI_API_KEY or OPENAI_API_KEY is required for LLM agent turns"
        )

    kwargs: dict[str, Any] = {
        "model": cfg.resolved_mas_openai_chat_model(),
        "temperature": 0,
        "api_key": api_key,
    }
    base_url = cfg.resolved_mas_openai_base_url()
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


async def propose_course_plan(
    *,
    goal: str,
    completed_courses: list[str],
    semester_label: str,
    candidate_courses: list[str],
    settings: Settings | None = None,
) -> list[str]:
    """Ask the planner LLM to pick course codes from the active semester catalog."""
    llm = build_mas_llm(settings)
    catalog_preview = ", ".join(candidate_courses[:40])
    messages = [
        SystemMessage(
            content=(
                "You are the UniPilot MAS Planner agent. Propose a next-semester course plan "
                "using ONLY course numbers from the provided catalog list. "
                "Return a comma-separated list of 8-digit course codes and nothing else."
            )
        ),
        HumanMessage(
            content=(
                f"Goal: {goal}\n"
                f"Active semester: {semester_label}\n"
                f"Completed courses: {', '.join(completed_courses) or 'none'}\n"
                f"Catalog (subset): {catalog_preview}\n"
            )
        ),
    ]
    response = await llm.ainvoke(messages)
    text = str(response.content or "")
    codes = []
    for token in text.replace("\n", ",").split(","):
        cleaned = "".join(ch for ch in token if ch.isdigit())
        if len(cleaned) == 8:
            codes.append(cleaned)
    return list(dict.fromkeys(codes))
