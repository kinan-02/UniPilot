"""Hard schedule conflict detection from semester JSON slot data."""

from __future__ import annotations

import re
from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine

HEBREW_DAY_ORDER = [
    "ראשון",
    "שני",
    "שלישי",
    "רביעי",
    "חמישי",
    "שישי",
    "שבת",
]

TIME_RANGE_PATTERN = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$"
)


def parse_time_range(time_range: str) -> tuple[int, int] | None:
    normalized = str(time_range or "").replace("–", "-").replace("—", "-")
    match = TIME_RANGE_PATTERN.match(normalized)
    if not match:
        return None
    start_hour, start_minute, end_hour, end_minute = (int(value) for value in match.groups())
    start_total = start_hour * 60 + start_minute
    end_total = end_hour * 60 + end_minute
    if end_total <= start_total:
        return None
    return start_total, end_total


def normalize_slot(slot: dict[str, Any]) -> dict[str, str]:
    day = str(slot.get("יום") or slot.get("day") or "").strip()
    time_range = str(slot.get("שעה") or slot.get("time") or "").strip()
    slot_type = str(slot.get("סוג") or slot.get("type") or "").strip()
    group = str(slot.get("קבוצה") or slot.get("group") or "").strip()
    return {
        "day": day,
        "timeRange": time_range,
        "slotType": slot_type,
        "group": group,
    }


def collect_course_slots(
    engine: AcademicGraphEngine,
    course_id: str,
) -> list[dict[str, Any]]:
    if not engine._built:
        return []
    node = engine.graph.nodes.get(course_id, {})
    schedule = node.get("schedule") or []
    slots: list[dict[str, Any]] = []
    for raw_slot in schedule:
        if not isinstance(raw_slot, dict):
            continue
        normalized = normalize_slot(raw_slot)
        parsed = parse_time_range(normalized["timeRange"])
        if not normalized["day"] or parsed is None:
            continue
        start_minutes, end_minutes = parsed
        slots.append(
            {
                "courseId": course_id,
                "day": normalized["day"],
                "timeRange": normalized["timeRange"],
                "slotType": normalized["slotType"],
                "group": normalized["group"],
                "startMinutes": start_minutes,
                "endMinutes": end_minutes,
            }
        )
    return slots


def _slots_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["day"] != right["day"]:
        return False
    return left["startMinutes"] < right["endMinutes"] and right["startMinutes"] < left["endMinutes"]


def detect_plan_schedule_conflicts(
    engine: AcademicGraphEngine,
    course_ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return timetable conflicts between distinct courses in a plan."""
    all_slots: list[dict[str, Any]] = []
    for course_id in course_ids:
        all_slots.extend(collect_course_slots(engine, course_id))

    conflicts: list[dict[str, Any]] = []
    references: list[str] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    for index, left in enumerate(all_slots):
        for right in all_slots[index + 1 :]:
            if left["courseId"] == right["courseId"]:
                continue
            if not _slots_overlap(left, right):
                continue
            pair_key = tuple(
                sorted(
                    [
                        f"{left['courseId']}:{left['day']}:{left['timeRange']}",
                        f"{right['courseId']}:{right['day']}:{right['timeRange']}",
                    ]
                )
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            conflicts.append(
                {
                    "courseA": left["courseId"],
                    "courseB": right["courseId"],
                    "day": left["day"],
                    "timeRangeA": left["timeRange"],
                    "timeRangeB": right["timeRange"],
                    "slotTypeA": left["slotType"],
                    "slotTypeB": right["slotType"],
                }
            )
            references.append(
                "schedule_conflict:"
                f"{left['courseId']}+{right['courseId']}:"
                f"{left['day']}:{left['timeRange']}"
            )

    if not conflicts:
        references.append("schedule:no_conflicts")
    return conflicts, references


def courses_involved_in_conflicts(conflicts: list[dict[str, Any]]) -> set[str]:
    involved: set[str] = set()
    for conflict in conflicts:
        involved.add(str(conflict.get("courseA") or ""))
        involved.add(str(conflict.get("courseB") or ""))
    return {course_id for course_id in involved if course_id}
