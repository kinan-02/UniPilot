"""Impact Narrator — synthesis over before/after simulation snapshots."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def _default_model() -> str:
    return os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-mini")


def _llm_base_url() -> str | None:
    raw = os.environ.get("OPENAI_BASE_URL", "").strip()
    return raw or None


def _build_llm() -> ChatOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for simulation narration")
    kwargs: dict[str, Any] = {
        "model": _default_model(),
        "temperature": 0,
        "api_key": api_key,
    }
    base_url = _llm_base_url()
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _template_narrative(
    scenario_name: str,
    *,
    deltas: dict[str, Any],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> str:
    progress_delta = (deltas or {}).get("progress") or {}
    completed_delta = progress_delta.get("completedCreditsDelta", 0)
    remaining_delta = progress_delta.get("creditsRemainingDelta", 0)
    before_credits = (before_snapshot.get("graduation") or {}).get("completedCredits")
    after_credits = (after_snapshot.get("graduation") or {}).get("completedCredits")
    return (
        f'For scenario "{scenario_name}", completed credits move from {before_credits} to '
        f"{after_credits} ({completed_delta:+.1f}). Remaining credits change by "
        f"{remaining_delta:+.1f}. Use the stored snapshots for exact requirement details."
    )


def narrate_simulation_impact(
    *,
    scenario_name: str,
    operations: list[dict[str, Any]],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    deltas: dict[str, Any],
) -> str:
    """
    Impact Narrator agent: explain deterministic before/after snapshots.
    Falls back to a template when LLM is unavailable.
    """
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return _template_narrative(
            scenario_name,
            deltas=deltas,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )

    payload = json.dumps(
        {
            "scenario_name": scenario_name,
            "operations": operations,
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "deltas": deltas,
        },
        ensure_ascii=False,
    )
    llm = _build_llm()
    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "You are the UniPilot Impact Narrator for academic what-if simulations.\n"
                    "Explain the BEFORE vs AFTER snapshots in clear student-friendly language.\n"
                    "Copy all credit counts and risk counts exactly from the JSON — never invent numbers.\n"
                    "Mention which operations likely drove the change. Keep the answer under 180 words."
                )
            ),
            HumanMessage(content=payload),
        ]
    )
    content = response.content if isinstance(response.content, str) else str(response.content)
    cleaned = content.strip()
    if not cleaned:
        return _template_narrative(
            scenario_name,
            deltas=deltas,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
    return cleaned
