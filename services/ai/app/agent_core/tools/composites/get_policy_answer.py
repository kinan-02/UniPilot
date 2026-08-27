"""`get_policy_answer` -- higher-level composite tool (docs/agent/HIGHER_LEVEL_TOOLS.md).

Bundles the most common two-step retrieval pattern into one call:
`search_knowledge` (find the right wiki page when the caller doesn't already
know its slug) then `interpret_text` (answer the question from it). Composes
the two primitives' own `run_*` functions directly -- no new data-access
path, same discipline `search_over_state` already established for the
primitive tier.

Tries up to `_MAX_SOURCES_TRIED` distinct top-ranked search results in
order, stopping at the first one `interpret_text` can actually answer from
-- mirrors the Retrieval role's own documented allowance to "iterate if
what it finds is ambiguous" (AGENT_VISION.md §6), rather than giving up
after the single top-ranked (but not necessarily correct) match. Still
fails closed: if no distinct source is found at all, or every attempted
source comes back "cannot determine", this returns `ok=False` -- never a
best-guess answer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.interpret_text import InterpretTextInput, run_interpret_text
from app.agent_core.tools.primitives.search_knowledge import SearchKnowledgeInput, run_search_knowledge
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_policy_answer"

_MAX_SOURCES_TRIED = 3
_SEARCH_LIMIT = 5


class GetPolicyAnswerInput(BaseModel):
    question: str


def _distinct_slugs_in_rank_order(matches: list[dict[str, Any]]) -> list[str]:
    """`search_knowledge` can return several chunks from the same page --
    dedupe to distinct slugs, preserving rank order, before spending an
    `interpret_text` call on each.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for match in matches:
        slug = match.get("slug")
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


async def run_get_policy_answer(payload: GetPolicyAnswerInput) -> ToolOutputEnvelope:
    question = (payload.question or "").strip()
    if not question:
        return ToolOutputEnvelope(ok=False, data=None, error="question_required")

    search_result = await run_search_knowledge(SearchKnowledgeInput(query=question, limit=_SEARCH_LIMIT))
    if not search_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"search_failed: {search_result.error}")

    candidate_slugs = _distinct_slugs_in_rank_order(search_result.data["matches"])[:_MAX_SOURCES_TRIED]
    if not candidate_slugs:
        return ToolOutputEnvelope(ok=False, data=None, error="no_relevant_source_found")

    sources_tried: list[str] = []
    for slug in candidate_slugs:
        sources_tried.append(slug)
        interpretation = await run_interpret_text(InterpretTextInput(source=slug, question=question))
        if interpretation.ok:
            return ToolOutputEnvelope(
                ok=True,
                data={
                    "question": question,
                    "answer": interpretation.data["answer"],
                    "citedSection": interpretation.data["citedSection"],
                    "source": slug,
                    "sourcesConsidered": sources_tried,
                },
                certainty=interpretation.certainty,
            )

    # Same reasoning as interpret_text's own cannot_determine: a bare "could not
    # determine" reads as "try again" and buys a wander. These sources were read
    # and searched; say so, and name the two moves that are left.
    return ToolOutputEnvelope(
        ok=False,
        data=None,
        error=(
            f"cannot_determine: read {sources_tried} and none answers this. Searching or "
            "rephrasing against the same pages will return this again. Either name a different "
            "source, or tell the student this is not documented in the material available."
        ),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Answer a policy/regulation question end to end: find the relevant wiki "
    "page(s) via search_knowledge, then interpret the answer from the best match via "
    "interpret_text -- one call instead of two. Fails closed if nothing relevant is found "
    "or no candidate source actually answers the question.",
    input_model=GetPolicyAnswerInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_policy_answer,
)
