"""`find_requirement_substitutes` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). Wraps `search_over_state`'s
`objective="find_substitute"` (docs/agent/SEARCH_OVER_STATE_CONTRACT.md)
with the one structural check that objective doesn't do itself -- confirming
`course_id` is actually part of `track_slug`'s required-course pool in the
first place -- plus flattening the resulting per-semester `plan` into a
ranked, soonest-first candidate list.

**Structurally plausible, not semantically verified** -- carried through
verbatim from the underlying objective's own documented limitation: the
graph has no elective-bucket/substitutability structure, only a track's
flat `contains` list. A candidate here is "another course in the same
track, not yet completed/planned, actually schedulable" -- not a claim that
it fulfills the exact same requirement line `course_id` was filling. This
is stated directly in the tool's own output (`note`) and its `DESCRIPTOR`
description, not just in this docstring, since a caller reading only the
returned data (not this file) still needs to see it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.composites.get_track_requirements import (
    GetTrackRequirementsInput,
    run_get_track_requirements,
)
from app.agent_core.tools.composites.student_state import resolve_student_state
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.identifiers import COURSE_ID_DESCRIPTION
from app.agent_core.tools.primitives.search_over_state import SearchOverStateInput, run_search_over_state
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "find_requirement_substitutes"

_SUBSTITUTE_CANDIDATE_NOTE = (
    "Candidates are other courses from the same track's required-course pool that are "
    "currently unscheduled and schedulable -- not a semantic verification that a candidate "
    "fulfills the exact same requirement line course_id was filling (the graph has no "
    "elective-bucket/substitutability structure to confirm that)."
)


class FindRequirementSubstitutesInput(BaseModel):
    course_id: str = Field(description=COURSE_ID_DESCRIPTION)
    track_slug: str
    # PREFERRED. Given this, the tool reads the student's completed courses
    # itself and `state` is not needed -- see `student_state.resolve_student_state`.
    student_id: str | None = None
    # Only for a what-if the CALLER built. Wins over `student_id` when it carries
    # completed courses.
    state: dict[str, Any] = Field(default_factory=dict)
    max_semesters: float | None = None


async def run_find_requirement_substitutes(payload: FindRequirementSubstitutesInput) -> ToolOutputEnvelope:
    course_id = (payload.course_id or "").strip()
    if not course_id:
        return ToolOutputEnvelope(ok=False, data=None, error="course_id_required")

    track_slug = (payload.track_slug or "").strip()
    if not track_slug:
        return ToolOutputEnvelope(ok=False, data=None, error="track_slug_required")

    # Read the record ourselves when the caller only named the student, so the
    # completed-course list never has to cross a model to get here.
    state, state_error = await resolve_student_state(payload.state, payload.student_id)
    if state_error:
        return ToolOutputEnvelope(ok=False, data=None, error=state_error)

    track_result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug=track_slug))
    if not track_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"track_requirements_failed: {track_result.error}")

    required_ids = {entry["id"] for entry in track_result.data["requiredCourses"]}
    if course_id not in required_ids:
        return ToolOutputEnvelope(ok=False, data=None, error=f"course_not_in_track: {course_id} not in {track_slug}")

    constraints: list[dict[str, Any]] = [
        {"type": "substitute_for", "courseId": course_id, "trackSlug": track_slug}
    ]
    if payload.max_semesters is not None:
        constraints.append({"type": "max_semesters", "value": payload.max_semesters})

    search_result = await run_search_over_state(
        SearchOverStateInput(state=state, constraints=constraints, objective="find_substitute")
    )
    if not search_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"substitute_search_failed: {search_result.error}")

    candidates: list[dict[str, Any]] = [
        {"courseNumber": course["courseNumber"], "semester": semester, "offeringCertainty": course["offeringCertainty"]}
        for semester, courses in search_result.data["plan"].items()
        for course in courses
    ]

    return ToolOutputEnvelope(
        ok=True,
        data={
            "courseId": course_id,
            "trackSlug": track_slug,
            "candidates": candidates,
            "unscheduledCandidates": search_result.data["unscheduledCourses"],
            "note": _SUBSTITUTE_CANDIDATE_NOTE,
        },
        certainty=search_result.certainty,
        warnings=list(track_result.warnings),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Find other courses from the same track's required-course pool that could "
    "stand in for course_id, ranked by soonest-schedulable semester. Structurally plausible "
    "(same track, not yet done, currently schedulable), not a semantic verification -- the "
    "graph has no elective-bucket/substitutability structure to confirm a candidate fulfills "
    "the exact same requirement line.",
    input_model=FindRequirementSubstitutesInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_find_requirement_substitutes,
)
