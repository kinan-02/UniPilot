"""`check_eligibility` -- higher-level composite tool (docs/agent/HIGHER_LEVEL_TOOLS.md).

Exposes `AcademicGraphEngine.evaluate_eligibility` -- the one place that
already gets AND/OR prerequisite logic right (see
`search_over_state.py`'s own docstring for why `traverse_relationship`'s
flattened `has_prerequisite` edges can't be used for this) -- as its own
callable, plus an optional single-semester offering check. Currently that
logic is only reachable *inside* `search_over_state`'s multi-semester
search.

**Deliberately narrow, not a partial reimplementation of `search_over_state`.**
Eligibility here is a snapshot: "given what's genuinely `status=="completed"`
right now, is this course eligible" -- it does **not** account for courses
merely *planned* (not yet completed) satisfying a prerequisite, the way
`search_over_state`'s own multi-semester walk does (where an earlier
semester's scheduled course legitimately counts as satisfied by the time a
later semester is reached). A caller that needs *that* -- "will I be
eligible after my planned courses are done" -- needs the real multi-semester
search, not this tool. This tool answers the smaller, much more common
question: "can I take this right now / next semester, given what I've
actually finished."
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.identifiers import COURSE_ID_DESCRIPTION, not_found_error
from app.agent_core.tools.primitives.extract_temporal_pattern import (
    ExtractTemporalPatternInput,
    run_extract_temporal_pattern,
)
from app.agent_core.tools.composites.student_state import resolve_completed_entries
from app.agent_core.tools.registry import ToolDescriptor
from app.retrieval.graph_engine.graph_registry import graph_registry

TOOL_NAME = "check_eligibility"

_SEMESTER_CODE_RE = re.compile(r"^(\d+)-([1-3])$")


class CheckEligibilityInput(BaseModel):
    course_id: str = Field(description=COURSE_ID_DESCRIPTION)
    # PREFERRED. Given this, the tool reads the student's completed courses
    # itself, and `state` is not needed -- see `_resolve_completed_entries`.
    student_id: str | None = None
    # Only for a what-if: a state a caller has deliberately altered (e.g. via
    # `mutate_state` to fail a course). Wins over `student_id` when non-empty,
    # because a simulated state is the whole point of passing one.
    state: dict[str, Any] = Field(default_factory=dict)
    target_semester: str | None = None


def _completed_course_numbers(entries: list[dict[str, Any]]) -> set[str]:
    """A course counts unless it was FAILED.

    This predicate used to demand `status == "completed"`, which nothing ever
    satisfies: `get_entity` emits these entries straight from the record with no
    `status` at all (they are completed -- that is what the collection IS), and
    the only writer of the field is `mutate_state`, which stamps
    `status="failed"` to simulate failing a course. So `status` is only ever
    absent or "failed"; requiring "completed" matched nothing, and every student
    looked like they had finished no courses.

    Measured live (2026-07-16): a student who passed 00940224 (grade 85) was
    told they were ineligible for 00960211, whose prerequisite is
    "00940224 OR 00940226" -- `missingPrerequisites: ["00940224"]`, with the
    course sitting right there in the payload. It answered `eligible: false` for
    every course with prerequisites, for every student.

    The unit tests missed it because they hand-built `{"courseNumber": ...,
    "status": "completed"}` -- a shape no producer emits. A fixture has to match
    what `get_entity` actually returns, or it only proves the code agrees with
    itself.
    """
    return {
        str(entry.get("courseNumber"))
        for entry in entries
        if entry.get("status") != "failed" and entry.get("courseNumber")
    }


async def _resolve_completed_entries(
    payload: CheckEligibilityInput,
) -> tuple[list[dict[str, Any]], str | None]:
    """Prefer reading the record ourselves over being told what is in it.

    This tool pioneered the `student_id` self-fetch; `student_state` now holds
    the implementation, because `simulate_course_disruption`,
    `audit_graduation_progress` and `find_requirement_substitutes` needed the
    identical thing -- and this function's own docstring warned that a second
    copy of the derivation would be a second thing to drift. The precedence it
    documented is unchanged: `state` wins when it carries completed courses,
    since a deliberately-altered state is the whole point of passing one.
    """
    return await resolve_completed_entries(payload.state, payload.student_id)


async def run_check_eligibility(payload: CheckEligibilityInput) -> ToolOutputEnvelope:
    course_id = (payload.course_id or "").strip()
    if not course_id:
        return ToolOutputEnvelope(ok=False, data=None, error="course_id_required")

    target_semester = payload.target_semester
    term_index: int | None = None
    if target_semester:
        match = _SEMESTER_CODE_RE.match(target_semester.strip())
        if not match:
            return ToolOutputEnvelope(ok=False, data=None, error=f"unparseable_target_semester: {target_semester}")
        term_index = int(match.group(2))

    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        engine = graph_registry.get_engine()
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_graph_unavailable: {exc}")

    if course_id not in engine.graph:
        return ToolOutputEnvelope(ok=False, data=None, error=not_found_error(course_id))

    entries, fetch_error = await _resolve_completed_entries(payload)
    if fetch_error:
        return ToolOutputEnvelope(ok=False, data=None, error=fetch_error)

    completed = _completed_course_numbers(entries)
    eligible, missing = engine.evaluate_eligibility(course_id, completed)
    # Name the prerequisites the student HOLDS, not just what is missing: the
    # engine's verdict is asymmetric (it reports only unmet requirements), so a
    # clean pass left an eligibility answer with no code to cite (measured live
    # 2026-07-16 -- "eligible, no missing prerequisites" never named 00940224).
    prerequisite_ids = engine.prerequisite_course_ids(course_id)
    prerequisites_held = sorted(set(prerequisite_ids) & completed)

    data: dict[str, Any] = {
        "courseId": course_id,
        "eligible": eligible,
        "missingPrerequisites": missing,
        "prerequisiteCourseIds": prerequisite_ids,
        "prerequisitesHeld": prerequisites_held,
        "targetSemester": target_semester,
        "offeringPattern": None,
        "schedulable": None,
    }
    warnings: list[str] = []
    # `eligible`/`missingPrerequisites` are an official record, but `schedulable`
    # and `offeringPattern` depend on the offering PREDICTION -- so they carry
    # their own (predicted_pattern) basis rather than being laundered into this
    # envelope's official_record certainty when surfaced (§4.2).
    field_certainty: dict[str, CertaintyTag] = {}

    if target_semester:
        offering_result = await run_extract_temporal_pattern(
            ExtractTemporalPatternInput(fact_type="course_offering", entity=course_id)
        )
        if offering_result.ok:
            data["offeringPattern"] = {
                **offering_result.data,
                "certainty": offering_result.certainty.model_dump(mode="json"),
            }
            term_pattern = offering_result.data["termPatterns"].get(str(term_index))
            offered_this_term = term_pattern is None or term_pattern["label"] != "never"
            data["schedulable"] = eligible and offered_this_term
            field_certainty["schedulable"] = offering_result.certainty
            field_certainty["offeringPattern"] = offering_result.certainty
        else:
            warnings.append("offering_pattern_unavailable")

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
        warnings=warnings,
        field_certainty=field_certainty,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Check whether a course is eligible right now given the student's completed "
    "courses (AND/OR-aware prerequisite logic), optionally combined with an offering-pattern "
    "check for one target semester. Narrower and cheaper than a full search_over_state run "
    "-- does not account for merely-planned (not yet completed) courses. "
    "PASS student_id AND LEAVE state EMPTY: this tool reads the completed-course record "
    "itself, so you never need to copy it into the arguments -- doing so is slower and risks "
    "reshaping the data. Pass state ONLY to evaluate a state you deliberately altered (e.g. "
    "mutate_state failing a course for a what-if); a non-empty state overrides student_id.",
    input_model=CheckEligibilityInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_check_eligibility,
)
