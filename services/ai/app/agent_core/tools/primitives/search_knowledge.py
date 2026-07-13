"""`search_knowledge` -- semantic resolution over the wiki (docs/agent/AGENT_VISION.md §5, primitive 2).

Thin wrapper over
`app.retrieval.graph_engine.academic_graph_engine.AcademicGraphEngine.search_wiki`
(BM25 + optional embeddings, via `app.retrieval.graph_engine.graph_registry`)
-- the same engine `get_entity`/`traverse_relationship` already use.
`app.retrieval.graph_retriever`/`hybrid_wiki_retriever` (the old
intent-driven wrapper and the legacy pre-graph retriever) have since been
retired entirely -- see docs/agent/TOOL_PRIMITIVES_PROGRESS.md.

Unlike `get_entity`/`traverse_relationship`, a search returning zero matches
is a legitimate outcome, not a failure -- `ok=True` with an empty `matches`
list, never `ok=False`, since "nothing matched" is an accurate answer, not an
error (`error` stays reserved for genuine `ok=False` failure paths).
`certainty.confidence` is derived from the top hit's own relevance score via
`min(1.0, score / 10.0)` -- the same BM25-score-to-confidence heuristic the
now-retired `graph_retriever.py` used for `wiki_search` blocks, reused here
rather than invented fresh.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag, SourceRef
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor
from app.retrieval.graph_engine.graph_registry import graph_registry

TOOL_NAME = "search_knowledge"

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20


class SearchKnowledgeInput(BaseModel):
    query: str
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1)


def _confidence_from_score(score: float) -> float:
    return max(0.0, min(1.0, score / 10.0))


async def run_search_knowledge(payload: SearchKnowledgeInput) -> ToolOutputEnvelope:
    query = (payload.query or "").strip()
    if not query:
        return ToolOutputEnvelope(ok=False, data=None, error="query_required")

    limit = max(1, min(payload.limit, _MAX_LIMIT))

    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        engine = graph_registry.get_engine()
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_graph_unavailable: {exc}")

    try:
        # `search_wiki` (BM25 + optional embeddings via `embed_query_cached`)
        # is fully synchronous all the way down to the blocking HTTP call an
        # embeddings request makes -- called directly (no `to_thread`), it
        # would freeze the entire asyncio event loop for as long as that
        # call takes, and `asyncio.wait_for`'s cooperative cancellation
        # can't interrupt a call that never yields control back to the loop
        # (found live: a turn's own 300s timeout only fired at 463s, once
        # the blocking call finally returned on its own). `to_thread` moves
        # the whole synchronous chain off the event loop so a slow/stalled
        # call blocks only its own thread, not every concurrent turn.
        hits = await asyncio.to_thread(engine.search_wiki, query, limit=limit)
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"search_failed: {exc}")

    matches: list[dict[str, Any]] = [
        {
            "slug": hit.get("slug"),
            "title": hit.get("title"),
            "titleHe": hit.get("title_he"),
            "kind": hit.get("kind"),
            # A structured course-code field for course-classified hits,
            # sourced from the engine's own slug->code map -- turns the
            # previously-implicit "course slugs lead with their 8-digit
            # code" convention into an explicit, tested contract, rather
            # than requiring callers to parse it out of the slug string
            # themselves (docs/agent/TOOL_PRIMITIVES_OPEN_GAPS.md #3).
            "courseCode": engine.slug_to_course_code.get(hit.get("slug", "")) if hit.get("kind") == "course" else None,
            "sectionTitle": hit.get("sectionTitle"),
            "content": hit.get("content"),
            "score": hit.get("score"),
        }
        for hit in hits
    ]

    top_score = float(matches[0]["score"] or 0.0) if matches else 0.0
    source_ref = SourceRef(page=str(matches[0]["slug"])) if matches and matches[0].get("slug") else None

    # `ok=True` even with zero matches -- "nothing matched" is an accurate,
    # successful search result, not an error; `error` stays reserved for
    # `ok=False` paths, consistent with every other primitive's envelope
    # contract. Callers detect "no matches" from an empty `data["matches"]`.
    return ToolOutputEnvelope(
        ok=True,
        data={"query": query, "matches": matches},
        certainty=CertaintyTag(
            basis="wiki_derived",
            confidence=_confidence_from_score(top_score),
            source_ref=source_ref,
        ),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Semantic resolution over the wiki when the exact entity isn't already named. "
    "Returns ranked wiki chunks (slug, title, section, content, score) via BM25 + optional "
    "embeddings, plus a structured courseCode when a hit is a course page. An empty result "
    "set is a legitimate outcome, not a failure.",
    input_model=SearchKnowledgeInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_search_knowledge,
)
