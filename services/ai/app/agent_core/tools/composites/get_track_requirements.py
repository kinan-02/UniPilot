"""`get_track_requirements` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). Bundles a track's own wiki page details
(`get_entity`) with its required courses (`traverse_relationship` on
`contains`) into one call -- almost nothing that needs one of these skips
straight to just the other.

`requiredCourses` reflects only what the graph can derive deterministically
(the `contains` edges a track page's `[[wikilinks]]` produce). Elective-bucket
rules and other free-text requirement nuance live in the track's own wiki
`content` (also returned here) and need `interpret_text` to extract, not this
tool -- the usual "structured facts here, free-text interpretation stays a
separate step" split.

`totalCreditsRequired` is the one exception, and it is deliberate. It reads as
prose, but it is a hard scalar stated in a fixed bold-label form on 51 of the 67
track pages, and leaving it inside the markdown blob had a sharp cost: the
2026-07-18 live eval answered "how many credits do I still need?" with "your
track requires 35.5" -- grounded, and wrong by 119.5 credits. No path reached
the real total, so `surface_fact` could not bind it and the model fell back to
`interpret_text`, which returned the "Faculty electives" ROW (35.5) of the
credit breakdown table instead of the 155.0 total. Projecting the scalar here
is the same fix §19 #4b applied to the offering grain (`termLabels`): expose one
directly-surfaceable number so tool-choice cannot change the answer's shape, and
so the value carries the page's own (official) basis rather than an interpreted
one. Pages that state no total, or state conflicting ones, get no field and a
`total_credits_not_parsed` warning -- never a guess.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity
from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_track_requirements"

# A bold label naming a credit TOTAL, then its number. Anchoring on the bold
# label is what keeps breakdown rows out: the table states its components as
# plain cells (`| Faculty electives | 35.5 |`), so only the stated total matches.
_TOTAL_CREDITS_RE = re.compile(
    r"\*\*(?P<label>[^*\n]{0,60}?"
    r"(?:total\s+credits|credits\s+required|נקודות\s+זכות|סה\"כ\s+נקודות)"
    r"[^*\n]{0,40}?)\*\*[:\s]*(?P<value>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_total_credits(content: str) -> tuple[float, str] | None:
    """The track's stated total credits as `(value, label)`, or None.

    Returns None when the page states no total AND when it states more than one
    distinct total -- a few pages give only a qualified figure (medicine's
    pre-clinical vs clinical years), and picking one of those to present as "the"
    degree total is precisely the failure this projection exists to prevent. The
    label rides along so a qualified total can be rendered as what it is.

    Most pages state the same total twice, once in English and once in Hebrew;
    agreeing restatements are one fact, so only distinct VALUES conflict.
    """
    matches = list(_TOTAL_CREDITS_RE.finditer(content or ""))
    if not matches:
        return None
    if len({float(m.group("value")) for m in matches}) > 1:
        return None
    first = matches[0]
    return float(first.group("value")), first.group("label").strip().rstrip(":").strip()


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

    data = {
        "trackSlug": track_slug,
        "track": track_result.data,
        "requiredCourses": required_courses,
    }

    total_credits = parse_total_credits(track_result.data.get("content") or "")
    if total_credits is None:
        warnings.append("total_credits_not_parsed")
    else:
        data["totalCreditsRequired"], data["totalCreditsLabel"] = total_credits

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=track_result.certainty,
        warnings=warnings,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="A track's wiki page details plus its required courses (graph-derived "
    "'contains' edges) in one call. `totalCreditsRequired` is the track's stated total "
    "credits as a surfaceable scalar (with `totalCreditsLabel` naming it) -- use it "
    "directly; do NOT interpret_text the page for a credit total, and do not add up the "
    "breakdown rows. It is absent only when the page states no total or states "
    "conflicting ones (warning: total_credits_not_parsed). Remaining elective-bucket "
    "rules and other free-text nuance still live in the returned wiki content and need "
    "interpret_text to extract.",
    input_model=GetTrackRequirementsInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_track_requirements,
)
