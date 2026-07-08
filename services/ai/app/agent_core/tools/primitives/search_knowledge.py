"""`search_knowledge` -- semantic resolution over the wiki (docs/agent/AGENT_VISION.md §5, primitive 2).

The eventual real implementation calls into the already-ported
`app.retrieval.graph_retriever`/`hybrid_wiki_retriever` -- deliberately not
wired yet, per this pass's scope (stub interfaces only).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "search_knowledge"


class SearchKnowledgeInput(BaseModel):
    query: str


async def run_search_knowledge(payload: SearchKnowledgeInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Semantic resolution over the wiki when the exact entity isn't already named.",
    input_model=SearchKnowledgeInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_search_knowledge,
)
