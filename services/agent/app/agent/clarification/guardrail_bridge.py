"""Deterministic clarification guardrail for semester-planning ambiguity (Phase 26.1).

Runs without LLM calls. Shadow/eval safe: read-only diagnostics only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

GuardrailKind = Literal["missing_preferences", "preference_conflict"]

_SEMESTER_PLANNING_RE = re.compile(
    r"(?:"
    r"\b(?:plan|build|recommend|optimize|schedule|make)\b.{0,40}\b(?:next semester|semester plan|my semester|a schedule)\b|"
    r"\bwhat should i take next semester\b|"
    r"\bwhich courses should i take(?: next semester)?\b|"
    r"\bhelp me (?:plan|build) (?:my )?(?:next )?semester\b"
    r")",
    re.IGNORECASE,
)

_OPTIMIZATION_GOAL_RE = re.compile(
    r"\b(?:"
    r"easiest|easy|light|lighter|minimal workload|low workload|"
    r"fastest graduation|graduate sooner|finish faster|maximum progress|"
    r"balanced|balance|"
    r"\d{1,2}\s*credits?|"
    r"morning|evening|afternoon|"
    r"monday|tuesday|wednesday|thursday|friday|weekend|"
    r"avoid labs?|no labs?|"
    r"specific courses?|already want|prefer(?:red)?|"
    r"work(?:ing)?|commute|internship|research track|industry track"
    r")\b",
    re.IGNORECASE,
)

_LIGHT_LOAD_RE = re.compile(
    r"\b(?:light|lighter|easy|easiest|minimal workload|low workload|low load)\b",
    re.IGNORECASE,
)
_HEAVY_LOAD_RE = re.compile(
    r"\b(?:24\s*credits?|two labs?|2 labs?|heavy load|maximum credits?|fastest graduation|graduate sooner|finish faster|maximum progress)\b",
    re.IGNORECASE,
)
_EASIEST_RE = re.compile(r"\b(?:easiest|easy|light|lighter)\b", re.IGNORECASE)
_FASTEST_RE = re.compile(
    r"\b(?:fastest graduation|graduate sooner|finish faster|maximum progress|as fast as possible)\b",
    re.IGNORECASE,
)

_MISSING_PREFS_QUESTION = (
    "To plan your next semester correctly, what should I optimize for: easiest workload, "
    "fastest graduation progress, balanced schedule, preferred days/times, or specific "
    "courses you already want to take?"
)

_CONFLICT_QUESTION = (
    "These goals may conflict: an easy/light semester usually means a lighter load, while "
    "fastest graduation usually means taking more required credits. Which should I "
    "prioritize, or should I balance them?"
)


@dataclass(frozen=True)
class ClarificationGuardrailDetection:
    kind: GuardrailKind
    consequence: Literal["medium", "high"]
    question: str
    conflict_summary: str | None = None


def detect_semester_planning_clarification_need(user_message: str) -> ClarificationGuardrailDetection | None:
    """Detect obvious semester-planning ambiguity from the user message alone."""
    text = (user_message or "").strip()
    if not text:
        return None

    if _LIGHT_LOAD_RE.search(text) and _HEAVY_LOAD_RE.search(text):
        return ClarificationGuardrailDetection(
            kind="preference_conflict",
            consequence="high",
            question=_CONFLICT_QUESTION,
            conflict_summary="light_or_easy_semester_vs_heavy_load_or_fast_graduation",
        )

    if _EASIEST_RE.search(text) and _FASTEST_RE.search(text):
        return ClarificationGuardrailDetection(
            kind="preference_conflict",
            consequence="high",
            question=_CONFLICT_QUESTION,
            conflict_summary="easiest_semester_vs_fastest_graduation",
        )

    if not _SEMESTER_PLANNING_RE.search(text):
        return None

    if _OPTIMIZATION_GOAL_RE.search(text):
        return None

    return ClarificationGuardrailDetection(
        kind="missing_preferences",
        consequence="medium",
        question=_MISSING_PREFS_QUESTION,
    )


def build_clarification_guardrail_diagnostics(
    detection: ClarificationGuardrailDetection,
) -> dict[str, Any]:
    return {
        "action": "ask_user",
        "status": "question_ready",
        "source": "deterministic_guardrail",
        "guardrailKind": detection.kind,
        "needCount": 1,
        "questionCount": 1,
        "assumedAnswerCount": 0,
        "questions": [
            {
                "ambiguityType": "preference",
                "consequence": detection.consequence,
                "optionCount": 0,
                "topic": detection.conflict_summary or detection.kind,
            }
        ],
        "warnings": [],
    }


def _existing_clarification_action(existing: dict[str, Any]) -> str | None:
    action = existing.get("action") or existing.get("status")
    if not action:
        return None
    normalized = str(action).strip().lower()
    if normalized in {"ask_user", "ask", "question_ready"}:
        return "ask_user"
    return str(action)


def apply_clarification_guardrail(
    *,
    user_message: str,
    replay_meta: dict[str, Any],
    enabled: bool = True,
) -> dict[str, Any]:
    """Merge deterministic clarification diagnostics when ambiguity is obvious."""
    if not enabled:
        return replay_meta

    detection = detect_semester_planning_clarification_need(user_message)
    if detection is None:
        return replay_meta

    guardrail_diag = build_clarification_guardrail_diagnostics(detection)
    existing = replay_meta.get("clarificationDiagnostics")
    existing_dict = existing if isinstance(existing, dict) else {}

    if _existing_clarification_action(existing_dict) == "ask_user":
        merged = {**existing_dict, "action": "ask_user"}
        if not merged.get("questions"):
            merged["questions"] = guardrail_diag["questions"]
        return {**replay_meta, "clarificationDiagnostics": merged}

    return {
        **replay_meta,
        "clarificationDiagnostics": guardrail_diag,
        "clarificationGuardrail": {
            "applied": True,
            "kind": detection.kind,
            "consequence": detection.consequence,
        },
    }
