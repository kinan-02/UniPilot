"""Heuristic classifier for auto-offloading heavy advisor questions to async jobs."""

from __future__ import annotations

import re
from typing import Literal

OffloadReason = Literal[
    "planning_intent",
    "graduation_intent",
    "risk_intent",
    "long_question",
    "multi_course",
    "force_async",
]

_COURSE_CODE_RE = re.compile(r"\d{8}")

_PLANNING_PATTERNS = (
    r"\bnext semester\b",
    r"\bsemester plan\b",
    r"\bspring plan\b",
    r"\bwinter plan\b",
    r"\bbuild a plan\b",
    r"\bplan my\b",
    r"\bwhat should i take\b",
    r"\bwhich courses should\b",
    r"\bcourse load\b",
    r"\bcredit load\b",
    r"\boptimize\b.{0,20}\bplan\b",
    r"מה לקחת",
    r"בסמסטר הבא",
    r"תוכנית לסמסטר",
    r"תכנון סמסטר",
    r"בנה.{0,12}תוכנית",
    r"תוכנית לימודים",
)

_GRADUATION_PATTERNS = (
    r"\bgraduate\b",
    r"\bgraduation\b",
    r"\bon track\b",
    r"\bdegree completion\b",
    r"\bfull degree\b",
    r"\bmulti[- ]semester\b",
    r"\broadmap\b",
    r"\bcredits remaining\b",
    r"\bcompletion percentage\b",
    r"לסיים את התואר",
    r"עמידה בדרישות",
    r"התקדמות לתואר",
    r"נקודות זכות",
    r"עוד כמה נקודות",
    r"מתי אסיים",
)

_RISK_PATTERNS = (
    r"\bacademic risk\b",
    r"\brisk analysis\b",
    r"\boverload\b",
    r"\boverloaded\b",
    r"\btoo many credits\b",
    r"\bflag.{0,12}risk\b",
    r"סיכון אקדמי",
    r"עומס",
    r"יותר מדי נקודות",
    r"סיכונים",
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_advisor_offload(question: str) -> tuple[bool, OffloadReason | None]:
    """
    Return whether a question should run as an async advisor_deep_plan job.
    Pure heuristics — no LLM call.
    """
    normalized = " ".join(question.strip().split())
    if not normalized:
        return False, None

    lowered = normalized.lower()
    course_codes = _COURSE_CODE_RE.findall(normalized)

    if _matches_any(lowered, _PLANNING_PATTERNS):
        return True, "planning_intent"
    if _matches_any(lowered, _GRADUATION_PATTERNS):
        return True, "graduation_intent"
    if _matches_any(lowered, _RISK_PATTERNS):
        return True, "risk_intent"
    if len(normalized) >= 280:
        return True, "long_question"
    if len(course_codes) >= 3:
        return True, "multi_course"

    return False, None
