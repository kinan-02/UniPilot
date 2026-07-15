"""Parse JSON payloads from LLM responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass(frozen=True)
class LlmJsonParseOutcome:
    payload: dict[str, Any] | None
    failure_code: str | None = None


def _find_object_starts(text: str) -> list[int]:
    return [index for index, char in enumerate(text) if char == "{"]


def _extract_balanced_object(text: str, start: int) -> str | None:
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _json_object_candidates(content: str) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []

    seen: set[str] = set()
    candidates: list[str] = []

    def _add(candidate: str) -> None:
        cleaned = candidate.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    _add(text)
    for match in _FENCED_JSON_RE.finditer(text):
        _add(match.group(1))

    for start in _find_object_starts(text):
        fragment = _extract_balanced_object(text, start)
        if fragment:
            _add(fragment)

    return candidates


def parse_llm_json_detailed(content: str) -> LlmJsonParseOutcome:
    """Extract and parse a JSON object from model output with a compact failure code."""
    candidates = _json_object_candidates(content)
    if not candidates:
        return LlmJsonParseOutcome(payload=None, failure_code="json_extraction_failed")

    last_decode_error = False
    for candidate in candidates:
        try:
            # strict=False tolerates raw control characters (literal newlines,
            # tabs) inside string values. Synthesis answers are multi-paragraph
            # markdown, so the model routinely emits un-escaped newlines inside
            # `answer_text` -- valid content, but illegal to strict json.loads,
            # which previously hard-failed the whole turn as `json_parse_failed`.
            # It still rejects genuinely malformed JSON (trailing commas, etc.).
            payload = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            last_decode_error = True
            continue
        if isinstance(payload, dict):
            return LlmJsonParseOutcome(payload=payload)
        last_decode_error = True

    if last_decode_error:
        return LlmJsonParseOutcome(payload=None, failure_code="json_parse_failed")
    return LlmJsonParseOutcome(payload=None, failure_code="json_extraction_failed")


def parse_llm_json_content(content: str) -> dict[str, Any] | None:
    """Strip markdown fences and parse a JSON object from model output."""
    return parse_llm_json_detailed(content).payload
