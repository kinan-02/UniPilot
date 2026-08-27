"""`mutate_state` -- apply a hypothetical change to a state object
(docs/agent/AGENT_VISION.md §5, primitive 7). A small, cheap, deterministic
transform -- never a capability of its own, always feeds `search_over_state`.

`base_state`'s shape and the `change["type"]` vocabulary implemented here are
defined in docs/agent/SIMULATION_STATE_CONTRACT.md -- the single source of
truth for both, since nothing else in the codebase defines a student
academic "state" object. Update that doc whenever this file's vocabulary
changes.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "mutate_state"

_SEMESTER_CODE_RE = re.compile(r"^(\d+)-([1-3])$")

_HandlerResult = tuple[dict[str, Any] | None, str | None]


class MutateStateInput(BaseModel):
    base_state: dict[str, Any] = Field(default_factory=dict)
    change: dict[str, Any] = Field(default_factory=dict)


def _advance_semester_code(code: str, count: int) -> str | None:
    """Advance a "YYYY-N" semester code (N in {1,2,3}, the format
    `app.retrieval.graph_engine.semester_catalog` already produces) forward
    by `count` slots, wrapping N at 3 and incrementing the year on wrap.
    Returns None for an unparseable code -- never guesses a replacement.
    """
    match = _SEMESTER_CODE_RE.match((code or "").strip())
    if not match:
        return None
    year = int(match.group(1))
    term_index = int(match.group(2))
    zero_based = term_index - 1 + count
    new_year = year + zero_based // 3
    new_term_index = zero_based % 3 + 1
    return f"{new_year}-{new_term_index}"


def _fail_course(state: dict[str, Any], change: dict[str, Any]) -> _HandlerResult:
    course_number = change.get("courseNumber")
    semester = change.get("semester")
    if not course_number or not semester:
        return None, "fail_course_requires_courseNumber_and_semester"

    updated = False
    new_completed: list[dict[str, Any]] = []
    for entry in state.get("completedCourses") or []:
        if entry.get("courseNumber") == course_number and entry.get("semester") == semester:
            new_completed.append({**entry, "status": "failed"})
            updated = True
        else:
            new_completed.append(entry)
    if not updated:
        new_completed.append({"courseNumber": course_number, "semester": semester, "status": "failed"})

    return {**state, "completedCourses": new_completed}, None


def _drop_course(state: dict[str, Any], change: dict[str, Any]) -> _HandlerResult:
    course_number = change.get("courseNumber")
    semester = change.get("semester")
    if not course_number or not semester:
        return None, "drop_course_requires_courseNumber_and_semester"

    planned = dict(state.get("plannedSemesters") or {})
    planned[semester] = [c for c in (planned.get(semester) or []) if c != course_number]
    return {**state, "plannedSemesters": planned}, None


def _retake_course(state: dict[str, Any], change: dict[str, Any]) -> _HandlerResult:
    course_number = change.get("courseNumber")
    target_semester = change.get("targetSemester")
    if not course_number or not target_semester:
        return None, "retake_course_requires_courseNumber_and_targetSemester"

    planned = dict(state.get("plannedSemesters") or {})
    existing = list(planned.get(target_semester) or [])
    planned[target_semester] = existing if course_number in existing else [*existing, course_number]
    return {**state, "plannedSemesters": planned}, None


def _delay_semester(state: dict[str, Any], change: dict[str, Any]) -> _HandlerResult:
    count = change.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None, "delay_semester_requires_nonnegative_integer_count"

    current = state.get("currentSemesterCode")
    if not current:
        return None, "delay_semester_requires_currentSemesterCode_in_base_state"

    advanced = _advance_semester_code(str(current), count)
    if advanced is None:
        return None, f"unparseable_semester_code: {current}"

    return {**state, "currentSemesterCode": advanced}, None


def _change_track(state: dict[str, Any], change: dict[str, Any]) -> _HandlerResult:
    track_slug = change.get("trackSlug")
    if not track_slug:
        return None, "change_track_requires_trackSlug"

    return {**state, "trackSlug": track_slug}, None


_HANDLERS: dict[str, Any] = {
    "fail_course": _fail_course,
    "drop_course": _drop_course,
    "retake_course": _retake_course,
    "delay_semester": _delay_semester,
    "change_track": _change_track,
}


async def run_mutate_state(payload: MutateStateInput) -> ToolOutputEnvelope:
    change_type = str(payload.change.get("type") or "").strip()
    if not change_type:
        return ToolOutputEnvelope(ok=False, data=None, error="change_type_required")

    handler = _HANDLERS.get(change_type)
    if handler is None:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_change_type: {change_type}")

    # Deep-copied once so no handler ever mutates the caller's base_state,
    # even though every handler also builds fresh dicts/lists for the keys
    # it actually touches (belt-and-braces immutability, per this repo's
    # "never mutate, always return a new object" convention).
    base_state = copy.deepcopy(payload.base_state)
    new_state, error = handler(base_state, payload.change)
    if error is not None:
        return ToolOutputEnvelope(ok=False, data=None, error=error)

    return ToolOutputEnvelope(
        ok=True,
        data={"state": new_state, "appliedChange": dict(payload.change)},
        certainty=CertaintyTag(basis="hypothetical_simulation", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Apply a hypothetical change (fail/drop/retake a course, delay a semester, "
    "change track) to a state object, producing a perturbed state for search_over_state. "
    "See docs/agent/SIMULATION_STATE_CONTRACT.md for the base_state shape and change vocabulary.",
    input_model=MutateStateInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_mutate_state,
)
