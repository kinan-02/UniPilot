"""What-if scenario parsing and user-context adjustment (DEC-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.planner_support import extract_course_codes

_WHAT_IF_TRIGGERS = ("what if", "what-if", "מה אם")
_FAIL_TRIGGERS = ("fail", "failed", "failing", "נכשל", "נכשלתי", "כישלון")
_LIGHT_LOAD_TRIGGERS = (
    "light load",
    "lighter load",
    "less credits",
    "lower workload",
    "עומס קל",
    "עומס מופחת",
)
_SUMMER_TRIGGERS = ("summer", "summer term", "קיץ", "סמסטר קיץ")
_TRACK_TRIGGERS = ("switch track", "change track", "מסלול אחר", "החלפת מסלול")


class WhatIfScenario(str, Enum):
    COURSE_FAILURE = "course_failure"
    LIGHT_LOAD = "light_load"
    SUMMER_TERM = "summer_term"
    SWITCH_TRACK = "switch_track"


@dataclass(frozen=True)
class WhatIfSpec:
    scenario: WhatIfScenario
    failed_courses: list[str] = field(default_factory=list)
    max_credits: float | None = None
    semester_filename: str | None = None
    track_slug: str | None = None


def _has_what_if_trigger(goal: str) -> bool:
    lowered = goal.lower()
    return any(trigger in lowered or trigger in goal for trigger in _WHAT_IF_TRIGGERS)


def parse_what_if_fail_courses(goal: str) -> list[str] | None:
    """Backward-compatible helper for course-failure what-if goals."""
    spec = parse_what_if_scenario(goal)
    if spec is None or spec.scenario != WhatIfScenario.COURSE_FAILURE:
        return None
    return list(spec.failed_courses) if spec.failed_courses else None


def parse_what_if_scenario(goal: str) -> WhatIfSpec | None:
    """
    Detect what-if goals and return a structured scenario.

    Supports: course failure, lighter workload, summer term, track switch.
    """
    if not _has_what_if_trigger(goal):
        return None

    lowered = goal.lower()

    if any(trigger in lowered or trigger in goal for trigger in _FAIL_TRIGGERS):
        codes = extract_course_codes(goal)
        if codes:
            return WhatIfSpec(
                scenario=WhatIfScenario.COURSE_FAILURE,
                failed_courses=list(dict.fromkeys(codes)),
            )

    if any(trigger in lowered or trigger in goal for trigger in _LIGHT_LOAD_TRIGGERS):
        return WhatIfSpec(scenario=WhatIfScenario.LIGHT_LOAD, max_credits=12.0)

    if any(trigger in lowered or trigger in goal for trigger in _SUMMER_TRIGGERS):
        return WhatIfSpec(
            scenario=WhatIfScenario.SUMMER_TERM,
            semester_filename="courses_2025_202.json",
        )

    if any(trigger in lowered or trigger in goal for trigger in _TRACK_TRIGGERS):
        track_slug = _extract_track_slug(goal)
        return WhatIfSpec(
            scenario=WhatIfScenario.SWITCH_TRACK,
            track_slug=track_slug,
        )

    return None


def _extract_track_slug(goal: str) -> str | None:
    lowered = goal.lower()
    mapping = {
        "data-information-engineering": (
            "data",
            "information engineering",
            "הנדסת נתונים",
        ),
        "software-engineering": ("software", "תוכנה"),
        "computer-engineering": ("computer", "חשמל ומחשב"),
    }
    for slug, tokens in mapping.items():
        if any(token in lowered or token in goal for token in tokens):
            return slug
    return None


def apply_what_if_fail(user_context: dict[str, Any], failed_courses: list[str]) -> dict[str, Any]:
    return apply_what_if_scenario(
        user_context,
        WhatIfSpec(scenario=WhatIfScenario.COURSE_FAILURE, failed_courses=failed_courses),
    )


def apply_what_if_scenario(user_context: dict[str, Any], spec: WhatIfSpec) -> dict[str, Any]:
    """Apply a what-if scenario to the planning user context."""
    updated = dict(user_context)
    constraints = dict(updated.get("constraints") or {})
    what_if: dict[str, Any] = {
        "scenario": spec.scenario.value,
    }

    if spec.scenario == WhatIfScenario.COURSE_FAILURE:
        completed = list(updated.get("completed_courses") or [])
        remove = set(spec.failed_courses)
        adjusted = [course_id for course_id in completed if course_id not in remove]
        removed = [course_id for course_id in completed if course_id in remove]
        updated["completed_courses"] = adjusted
        what_if["simulated_failures"] = list(spec.failed_courses)
        what_if["removed_from_completed"] = removed

    if spec.scenario == WhatIfScenario.LIGHT_LOAD and spec.max_credits is not None:
        constraints["maxCredits"] = spec.max_credits
        what_if["maxCredits"] = spec.max_credits

    if spec.scenario == WhatIfScenario.SUMMER_TERM and spec.semester_filename:
        constraints["preferredSemesterFile"] = spec.semester_filename
        what_if["semesterFilename"] = spec.semester_filename

    if spec.scenario == WhatIfScenario.SWITCH_TRACK:
        if spec.track_slug:
            updated["track_slug"] = spec.track_slug
            what_if["trackSlug"] = spec.track_slug
        else:
            what_if["trackSlugUnspecified"] = True

    updated["constraints"] = constraints
    updated["what_if"] = what_if
    return updated
