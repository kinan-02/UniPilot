"""Filter offering schedule groups by per-type user selection."""

from __future__ import annotations

from typing import Any

from app.planning.lesson_events import (
    _canonical_slot_type,
    filter_groups_by_lesson_selection,
    group_schedule_by_type,
)
from app.planning.weekly_schedule import normalize_schedule_group

SLOT_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "lecture": ("lecture", "הרצאה", "lec"),
    "tutorial": ("tutorial", "תרגול", "recitation", "lesson", "תר"),
    "lab": ("lab", "מעבדה", "laboratory"),
    "project": ("project", "פרויקט", "workshop", "סדנה"),
}


def filter_schedule_groups_by_selection(
    schedule_groups: list[dict[str, Any]],
    selected_groups: dict[str, Any] | None,
    *,
    selected_lesson_events: list[dict[str, Any]] | None = None,
    course_number: str | None = None,
    academic_year: int | None = None,
    semester_code: int | None = None,
) -> list[dict[str, Any]]:
    """Return schedule groups included in the plan based on lesson selection."""
    return filter_groups_by_lesson_selection(
        schedule_groups,
        selected_lesson_events=selected_lesson_events,
        selected_groups=selected_groups,
        course_number=course_number,
        academic_year=academic_year,
        semester_code=semester_code,
    )


def available_group_options(schedule_groups: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Summarize selectable groups per slot type for UI."""
    grouped = group_schedule_by_type(schedule_groups)
    options: dict[str, list[dict[str, Any]]] = {}
    for slot_key, items in grouped.items():
        options[slot_key] = [
            {
                "index": index,
                "label": normalize_schedule_group(group).get("slotType") or slot_key,
                "day": normalize_schedule_group(group).get("day"),
                "timeRange": normalize_schedule_group(group).get("timeRange"),
            }
            for index, group in items
        ]
    return options
