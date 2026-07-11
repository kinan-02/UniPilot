"""`get_track_requirements` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). Bundles a track's own wiki page details
(`get_entity`) with its required courses (`traverse_relationship` on
`contains`) into one call -- almost nothing that needs one of these skips
straight to just the other.

`requiredCourses` reflects only what the graph can derive deterministically
(the `contains` edges a track page's `[[wikilinks]]` produce) -- credit
minimums, elective-bucket rules, and other free-text requirement details
live in the track's own wiki `content` (also returned here) and need
`interpret_text` to extract, not this tool. Same "structured facts here,
free-text interpretation stays a separate step" split every other composite
in this tier already follows.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity
from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_track_requirements"


class GetTrackRequirementsInput(BaseModel):
    track_slug: str


async def run_get_track_requirements(payload: GetTrackRequirementsInput) -> ToolOutputEnvelope:
    track_slug = (payload.track_slug or "").strip()
    if not track_slug:
        return ToolOutputEnvelope(ok=False, data=None, error="track_slug_required")

    track_result = await run_get_entity(GetEntityInput(entity_type="track", entity_id=track_slug))
    if not track_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"track_not_found: {track_slug}")

    warnings: list[str] = list(track_result.warnings)

    contains_result = await run_traverse_relationship(
        TraverseRelationshipInput(entity=track_slug, relation="contains", direction="forward")
    )
    if contains_result.ok:
        required_courses = [
            entry for entry in contains_result.data["relatedEntities"] if entry.get("nodeType") == "course"
        ]
    else:
        required_courses = []
        warnings.append("required_courses_unavailable")

    return ToolOutputEnvelope(
        ok=True,
        data={
            "trackSlug": track_slug,
            "track": track_result.data,
            "requiredCourses": required_courses,
        },
        certainty=track_result.certainty,
        warnings=warnings,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="A track's wiki page details plus its required courses (graph-derived "
    "'contains' edges) in one call. Free-text requirement details (credit minimums, "
    "elective-bucket rules) live in the returned wiki content and need interpret_text to "
    "extract -- this tool only returns what's structurally derivable from the graph.",
    input_model=GetTrackRequirementsInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_track_requirements,
)
