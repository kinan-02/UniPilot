"""Shared structured JSON extraction for MAS LLM layers (deepseek-v4-pro)."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.llm.client import build_mas_llm

T = TypeVar("T", bound=BaseModel)

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("Empty LLM response")

    block_match = JSON_BLOCK_RE.search(stripped)
    if block_match:
        return json.loads(block_match.group(1))

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])

    raise ValueError("No JSON object found in LLM response")


async def invoke_structured_model(
    *,
    system_prompt: str,
    user_prompt: str,
    model_type: type[T],
    settings: Settings | None = None,
) -> T:
    """Invoke the configured chat model and parse a Pydantic model from JSON output."""
    cfg = settings or get_settings()
    llm = build_mas_llm(cfg)
    messages = [
        SystemMessage(
            content=(
                f"{system_prompt}\n\n"
                "Respond with a single JSON object only. No markdown outside the JSON."
            )
        ),
        HumanMessage(content=user_prompt),
    ]
    response = await llm.ainvoke(messages)
    payload = _extract_json_object(str(response.content or ""))
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"LLM JSON did not match schema: {exc}") from exc
