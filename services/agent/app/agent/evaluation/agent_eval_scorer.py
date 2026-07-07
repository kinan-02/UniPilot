"""Score agent turn results against benchmark expectations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.intent_router import classify_intent


@dataclass
class AgentTurnResult:
    """Collected output from one agent conversation turn."""

    text: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    run_failed: bool = False
    run_error: str | None = None
    latency_ms: float = 0.0


@dataclass
class ScoreOutcome:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)


def _collect_block_types(events: list[dict[str, Any]]) -> set[str]:
    block_types: set[str] = set()
    for event in events:
        if event.get("type") != "structured_output":
            continue
        block = event.get("block") or {}
        block_type = block.get("type")
        if block_type:
            block_types.add(str(block_type))
    return block_types


def _collect_action_types(events: list[dict[str, Any]]) -> set[str]:
    action_types: set[str] = set()
    for event in events:
        if event.get("type") != "action.proposed":
            continue
        action = event.get("action") or {}
        action_type = action.get("action_type") or action.get("actionType")
        if action_type:
            action_types.add(str(action_type))
    return action_types


def _text_matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        if pattern.lower() in lowered:
            return True
    return False


def _text_matches_all(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return all(pattern.lower() in lowered for pattern in patterns)


def _text_excludes_all(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return all(pattern.lower() not in lowered for pattern in patterns)


def score_agent_turn(
    *,
    message: str,
    result: AgentTurnResult,
    expect: dict[str, Any],
) -> ScoreOutcome:
    """Validate one agent turn against expectation rules."""
    failures: list[str] = []
    warnings: list[str] = []

    classification = classify_intent(message)
    observed_intent = classification.intent
    block_types = _collect_block_types(result.events)
    action_types = _collect_action_types(result.events)

    expected_intent = expect.get("intent")
    expected_intents = expect.get("intentsAny") or []
    if expected_intent and observed_intent != expected_intent:
        failures.append(f"intent: expected {expected_intent!r}, got {observed_intent!r}")
    elif expected_intents and observed_intent not in expected_intents:
        failures.append(
            f"intent: expected one of {expected_intents!r}, got {observed_intent!r}"
        )

    if expect.get("noRunFailed", True) and result.run_failed:
        failures.append(f"run.failed: {result.run_error or 'unknown error'}")

    min_text_length = int(expect.get("minTextLength") or 0)
    if min_text_length and len(result.text.strip()) < min_text_length:
        failures.append(
            f"text too short: {len(result.text.strip())} chars (min {min_text_length})"
        )

    text_contains_any = list(expect.get("textContainsAny") or [])
    if text_contains_any and not _text_matches_any(result.text, text_contains_any):
        failures.append(f"text missing any of: {text_contains_any!r}")

    text_contains_all = list(expect.get("textContainsAll") or [])
    if text_contains_all and not _text_matches_all(result.text, text_contains_all):
        failures.append(f"text missing all of: {text_contains_all!r}")

    text_not_contains = list(expect.get("textNotContains") or [])
    if text_not_contains and not _text_excludes_all(result.text, text_not_contains):
        failures.append(f"text contains forbidden phrase from: {text_not_contains!r}")

    text_regex_any = list(expect.get("textRegexAny") or [])
    if text_regex_any:
        matched = any(re.search(pattern, result.text, re.I) for pattern in text_regex_any)
        if not matched:
            failures.append(f"text matched none of regex patterns: {text_regex_any!r}")

    block_types_any = list(expect.get("blockTypesAny") or [])
    if block_types_any and not block_types.intersection(block_types_any):
        failures.append(
            f"blocks: expected any of {block_types_any!r}, got {sorted(block_types)!r}"
        )

    block_types_all = list(expect.get("blockTypesAll") or [])
    missing_blocks = [block for block in block_types_all if block not in block_types]
    if missing_blocks:
        failures.append(f"blocks missing required types: {missing_blocks!r}")

    action_types_any = list(expect.get("actionTypesAny") or [])
    if action_types_any and not action_types.intersection(action_types_any):
        failures.append(
            f"actions: expected any of {action_types_any!r}, got {sorted(action_types)!r}"
        )

    if expect.get("requireStructuredOutput") and not block_types:
        failures.append("expected structured_output blocks but none were emitted")

    max_latency_ms = expect.get("maxLatencyMs")
    if max_latency_ms is not None and result.latency_ms > float(max_latency_ms):
        warnings.append(
            f"slow turn: {result.latency_ms:.0f}ms > {float(max_latency_ms):.0f}ms limit"
        )

    return ScoreOutcome(
        passed=not failures,
        failures=failures,
        warnings=warnings,
        observed={
            "intent": observed_intent,
            "blockTypes": sorted(block_types),
            "actionTypes": sorted(action_types),
            "textLength": len(result.text.strip()),
            "latencyMs": round(result.latency_ms, 1),
            "eventCount": len(result.events),
        },
    )
