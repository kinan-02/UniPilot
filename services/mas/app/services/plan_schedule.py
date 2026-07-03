"""Build schedule summaries for MAS final decisions."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import parse_course_credits, sum_plan_credits
from app.services.schedule_conflict import collect_course_slots, detect_plan_schedule_conflicts
from app.services.semester_catalog import plan_semester_code_from_filename


def _course_title(engine: AcademicGraphEngine, course_id: str) -> str:
    node = engine.graph.nodes.get(course_id, {}) if engine._built else {}
    name = str(node.get("name") or "").strip()
    if name:
        return name
    entry = engine.course_catalog.get(course_id, {})
    general = entry.get("general", {}) if isinstance(entry, dict) else {}
    return str(general.get("שם מקצוע") or "").strip()


def build_plan_schedule_summary(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    semester_filename: str | None,
) -> dict[str, Any]:
    """Summarize catalog schedule slots for committed course plans."""
    active_semester = engine.active_semester
    semester_label = active_semester.display_label if active_semester else None
    plan_semester_code = (
        plan_semester_code_from_filename(semester_filename)
        if semester_filename
        else None
    )
    if plan_semester_code is None and active_semester is not None:
        plan_semester_code = active_semester.plan_semester_code

    courses: list[dict[str, Any]] = []
    for course_id in course_ids:
        slots = collect_course_slots(engine, course_id)
        courses.append(
            {
                "courseId": course_id,
                "title": _course_title(engine, course_id),
                "credits": parse_course_credits(engine, course_id),
                "slots": [
                    {
                        "day": slot["day"],
                        "timeRange": slot["timeRange"],
                        "slotType": slot["slotType"],
                        "group": slot.get("group") or "",
                    }
                    for slot in slots
                ],
            }
        )

    conflicts, _refs = detect_plan_schedule_conflicts(engine, course_ids)
    return {
        "semesterFilename": semester_filename,
        "semesterLabel": semester_label,
        "planSemesterCode": plan_semester_code,
        "totalCredits": sum_plan_credits(engine, course_ids),
        "courses": courses,
        "scheduleConflicts": conflicts,
        "hasScheduleConflicts": bool(conflicts),
    }
