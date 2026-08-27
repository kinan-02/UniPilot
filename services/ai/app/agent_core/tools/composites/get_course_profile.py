"""`get_course_profile` -- higher-level composite tool (docs/agent/HIGHER_LEVEL_TOOLS.md).

Bundles the "tell me everything about this course" pattern into one call:
course details (`get_entity`), its prerequisites and what it unlocks (two
`traverse_relationship` calls, opposite directions on `has_prerequisite`),
which tracks it belongs to (`traverse_relationship` on `belongs_to`), and
its offering pattern (`extract_temporal_pattern`) -- 5 primitive calls
collapsed into 1. Composes the primitives' own `run_*` functions directly,
same discipline as `get_policy_answer`/`search_over_state`.

Only `get_entity` failing is a hard failure (`course_not_found`) -- the
course not existing at all means there's nothing to build a profile around.
Every other sub-call degrades gracefully: a wiki-only course (no catalog
entry) has no plain-course-code graph node, so its `traverse_relationship`
calls come back `entity_not_found` -- expected, not an error, so it's
recorded as an empty list plus a `warnings` entry (using the envelope's
`warnings` field, added specifically to support this "partial success, not
partial failure" case) rather than failing the whole profile.

`prerequisites`/`dependents` are a **flattened set of graph edges, not an
AND/OR-aware structure** -- same caveat `search_over_state` already
documents about `has_prerequisite` edges (`build_graph()` collapses an
OR-prerequisite AST into one flat edge set per course). The authoritative,
properly AND/OR-structured prerequisite logic is already included verbatim
in `course.prerequisitesAst` (from `get_entity`) -- this list is a
convenience "which courses are involved," never a substitute for it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.identifiers import COURSE_ID_DESCRIPTION
from app.agent_core.tools.primitives.extract_temporal_pattern import (
    ExtractTemporalPatternInput,
    run_extract_temporal_pattern,
)
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity
from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_course_profile"


class GetCourseProfileInput(BaseModel):
    course_id: str = Field(description=COURSE_ID_DESCRIPTION)


async def _related_or_empty(
    course_id: str, relation: str, direction: str, *, warning_on_failure: str
) -> tuple[list[dict[str, Any]], str | None]:
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity=course_id, relation=relation, direction=direction)
    )
    if not result.ok:
        return [], warning_on_failure
    return result.data["relatedEntities"], None


async def run_get_course_profile(payload: GetCourseProfileInput) -> ToolOutputEnvelope:
    course_id = (payload.course_id or "").strip()
    if not course_id:
        return ToolOutputEnvelope(ok=False, data=None, error="course_id_required")

    course_result = await run_get_entity(GetEntityInput(entity_type="course", entity_id=course_id))
    if not course_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"course_not_found: {course_id}")

    warnings: list[str] = list(course_result.warnings)

    prerequisites, warning = await _related_or_empty(
        course_id, "has_prerequisite", "forward", warning_on_failure="prerequisites_unavailable"
    )
    if warning:
        warnings.append(warning)

    dependents, warning = await _related_or_empty(
        course_id, "has_prerequisite", "backward", warning_on_failure="dependents_unavailable"
    )
    if warning:
        warnings.append(warning)

    tracks, warning = await _related_or_empty(
        course_id, "belongs_to", "forward", warning_on_failure="tracks_unavailable"
    )
    if warning:
        warnings.append(warning)

    offering_result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity=course_id)
    )
    offering_pattern: dict[str, Any] | None = None
    if offering_result.ok:
        offering_pattern = {
            **offering_result.data,
            "certainty": offering_result.certainty.model_dump(mode="json"),
        }
    else:
        warnings.append("offering_pattern_unavailable")

    return ToolOutputEnvelope(
        ok=True,
        data={
            "courseId": course_id,
            "course": course_result.data,
            "prerequisites": prerequisites,
            "dependents": dependents,
            "tracks": tracks,
            "offeringPattern": offering_pattern,
        },
        certainty=course_result.certainty,
        warnings=warnings,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Everything about one course in a single call: details, prerequisites, "
    "what it unlocks, track memberships, and offering pattern -- 5 primitive calls "
    "collapsed into 1. Only a completely unknown course_id is a hard failure; every other "
    "sub-fact degrades gracefully to an empty/null value plus a warning.",
    input_model=GetCourseProfileInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_course_profile,
)
