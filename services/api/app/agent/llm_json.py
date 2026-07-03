"""Parse JSON payloads from LLM responses."""

from __future__ import annotations

import json
from typing import Any


def parse_llm_json_content(content: str) -> dict[str, Any] | None:
    """Strip markdown fences and parse a JSON object from model output."""
    normalized = (content or "").strip()
    if not normalized:
        return None
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
