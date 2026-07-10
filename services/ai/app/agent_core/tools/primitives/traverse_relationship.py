"""`traverse_relationship` -- generic graph walk (docs/agent/AGENT_VISION.md §5, primitive 3).

`relation` is validated at runtime against `_KNOWN_RELATIONS`, the exact
edge-relation labels `AcademicGraphEngine.build_graph()` actually writes onto
graph edges (`data["relation"]`) -- no relation vocabulary is invented here.
Today that's exactly three: `has_prerequisite` (course -> its prerequisite
course), `belongs_to` (course -> a track it links to), `contains` (a track
page -> a course it links to). `direction` picks `successors` (`"forward"`)
or `predecessors` (`"backward"`) filtered to that relation -- e.g.
`(course, "has_prerequisite", "backward")` answers "what does this course
block" (the reverse-dependency need from the fail-course-X worked example,
AGENT_VISION.md §10) without a dedicated tool.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor
from app.retrieval.graph_engine.graph_registry import graph_registry

TOOL_NAME = "traverse_relationship"

_KNOWN_RELATIONS: frozenset[str] = frozenset({"has_prerequisite", "belongs_to", "contains"})


class TraverseRelationshipInput(BaseModel):
    entity: str
    relation: str
    direction: Literal["forward", "backward"] = "forward"


async def run_traverse_relationship(payload: TraverseRelationshipInput) -> ToolOutputEnvelope:
    entity = (payload.entity or "").strip()
    relation = (payload.relation or "").strip()

    if not entity:
        return ToolOutputEnvelope(ok=False, data=None, error="entity_required")
    if relation not in _KNOWN_RELATIONS:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_relation: {relation}")

    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        engine = graph_registry.get_engine()
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_graph_unavailable: {exc}")

    graph = engine.graph
    if entity not in graph:
        return ToolOutputEnvelope(ok=False, data=None, error=f"entity_not_found: {entity}")

    related_ids: list[str] = []
    if payload.direction == "forward":
        for target in graph.successors(entity):
            if graph.edges[entity, target].get("relation") == relation:
                related_ids.append(target)
    else:
        for source in graph.predecessors(entity):
            if graph.edges[source, entity].get("relation") == relation:
                related_ids.append(source)

    related_entities: list[dict[str, Any]] = [
        {"id": node_id, "nodeType": graph.nodes.get(node_id, {}).get("node_type")}
        for node_id in sorted(related_ids)
    ]

    return ToolOutputEnvelope(
        ok=True,
        data={
            "entity": entity,
            "relation": relation,
            "direction": payload.direction,
            "relatedEntities": related_entities,
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Generic graph walk, parameterized by relation type and direction. Known "
    "relations today: has_prerequisite (course -> prerequisite course), belongs_to "
    "(course -> track), contains (track -> course). direction='backward' on "
    "has_prerequisite answers reverse-dependency questions (what does this course block).",
    input_model=TraverseRelationshipInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_traverse_relationship,
)
