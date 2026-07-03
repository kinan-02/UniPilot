"""Soft preference evaluation for the Student Advocate agent."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import sum_plan_credits

HEBREW_WEEKDAYS = {
    "ראשון",
    "שני",
    "שלישי",
    "רביעי",
    "חמישי",
    "שישי",
    "שבת",
}


def _constraints(user_context: dict[str, Any]) -> dict[str, Any]:
    raw = user_context.get("constraints") or {}
    return raw if isinstance(raw, dict) else {}


def _preferences(user_context: dict[str, Any]) -> dict[str, Any]:
    raw = user_context.get("preferences") or {}
    return raw if isinstance(raw, dict) else {}


def resolve_min_credits(user_context: dict[str, Any]) -> float | None:
    constraints = _constraints(user_context)
    raw = constraints.get("minCredits")
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    return None


def resolve_avoid_days(user_context: dict[str, Any]) -> list[str]:
    constraints = _constraints(user_context)
    raw = constraints.get("avoidDays") or constraints.get("preferredDaysOff")
    if not isinstance(raw, list):
        return []
    days = [str(day).strip() for day in raw if str(day).strip()]
    return [day for day in days if day in HEBREW_WEEKDAYS]


def collect_schedule_days(engine: AcademicGraphEngine, course_id: str) -> set[str]:
    if not engine._built:
        return set()
    node = engine.graph.nodes.get(course_id, {})
    schedule = node.get("schedule") or []
    days: set[str] = set()
    for slot in schedule:
        if not isinstance(slot, dict):
            continue
        day = str(slot.get("יום") or "").strip()
        if day:
            days.add(day)
    return days


def evaluate_day_preferences(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    avoid_days: list[str],
) -> list[dict[str, Any]]:
    if not avoid_days:
        return []

    critiques: list[dict[str, Any]] = []
    avoid_set = set(avoid_days)
    for course_id in course_ids:
        scheduled_days = collect_schedule_days(engine, course_id)
        conflicts = sorted(scheduled_days.intersection(avoid_set))
        if conflicts:
            critiques.append(
                {
                    "type": "day_preference_conflict",
                    "courseId": course_id,
                    "conflictDays": conflicts,
                    "message": (
                        f"Course {course_id} meets on preferred day(s) off: "
                        f"{', '.join(conflicts)}."
                    ),
                }
            )
    return critiques


def evaluate_credit_preferences(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    user_context: dict[str, Any],
) -> list[dict[str, Any]]:
    critiques: list[dict[str, Any]] = []
    total_credits = sum_plan_credits(engine, course_ids)
    min_credits = resolve_min_credits(user_context)
    preferences = _preferences(user_context)
    max_credits = preferences.get("maxCreditsPerSemester")

    if min_credits is not None and total_credits < min_credits:
        critiques.append(
            {
                "type": "below_min_credits",
                "totalCredits": total_credits,
                "minCredits": min_credits,
                "message": (
                    f"Plan schedules {total_credits} credits, below the preferred "
                    f"minimum of {min_credits}."
                ),
            }
        )

    if isinstance(max_credits, (int, float)) and max_credits > 0:
        target = float(max_credits) * 0.6
        if total_credits < target and len(course_ids) <= 1:
            critiques.append(
                {
                    "type": "light_load",
                    "totalCredits": total_credits,
                    "targetCredits": round(target, 2),
                    "message": (
                        "Plan is quite light relative to the student's usual semester capacity."
                    ),
                }
            )

    return critiques


def evaluate_soft_preferences(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    user_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    critiques: list[dict[str, Any]] = []
    references: list[str] = []

    avoid_days = resolve_avoid_days(user_context)
    if avoid_days:
        references.append(f"preferences:avoidDays={','.join(avoid_days)}")
        critiques.extend(
            evaluate_day_preferences(
                engine=engine,
                course_ids=course_ids,
                avoid_days=avoid_days,
            )
        )

    min_credits = resolve_min_credits(user_context)
    if min_credits is not None:
        references.append(f"preferences:minCredits={min_credits}")

    credit_critiques = evaluate_credit_preferences(
        engine=engine,
        course_ids=course_ids,
        user_context=user_context,
    )
    critiques.extend(credit_critiques)

    if not critiques:
        references.append("preferences:no_soft_conflicts")

    return critiques, references


def preference_match_score(critiques: list[dict[str, Any]], course_count: int) -> float:
    if course_count <= 0:
        return 0.0
    if not critiques:
        return 1.0
    penalty = min(0.8, 0.2 * len(critiques))
    return max(0.0, 1.0 - penalty)
