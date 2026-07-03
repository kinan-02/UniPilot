"""Violation typing and classification for MAS agents."""

from __future__ import annotations

import re

from app.orchestrator.artifacts import Violation, ViolationType

COURSE_ID_IN_MESSAGE_RE = re.compile(r"\b(\d{8})\b")


def violation_from_message(message: str, *, hard: bool = True) -> Violation:
    """Classify a human-readable violation string into a typed Violation."""
    lowered = message.lower()
    course_ids = list(dict.fromkeys(COURSE_ID_IN_MESSAGE_RE.findall(message)))

    if "missing candidate plan" in lowered or "no candidate plan" in lowered:
        vtype = ViolationType.MISSING_PLAN
    elif "not in the active semester catalog" in lowered or "not in catalog" in lowered:
        vtype = ViolationType.COURSE_NOT_IN_CATALOG
    elif "prerequisite" in lowered or "unmet prerequisites" in lowered:
        vtype = ViolationType.PREREQ_MISSING
    elif "schedule conflict" in lowered:
        vtype = ViolationType.SCHEDULE_CONFLICT
    elif "credit overload" in lowered or "exceeds" in lowered and "credit" in lowered:
        vtype = ViolationType.CREDIT_OVERLOAD
    elif "at least one course" in lowered or "no feasible courses" in lowered:
        vtype = ViolationType.EMPTY_PLAN
    elif "probation" in lowered or "gpa" in lowered:
        vtype = ViolationType.PROBATION_RISK
    else:
        vtype = ViolationType.OTHER

    return Violation(type=vtype, message=message, course_ids=course_ids, hard=hard)


def violations_from_messages(messages: list[str], *, hard: bool = True) -> list[Violation]:
    return [violation_from_message(message, hard=hard) for message in messages if message]


def has_violation_type(violations: list[Violation], vtype: ViolationType) -> bool:
    return any(violation.type == vtype for violation in violations)


def violation_messages(violations: list[Violation]) -> list[str]:
    return [violation.message for violation in violations]
