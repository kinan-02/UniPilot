"""Academic knowledge graph retrieval (wiki + semester JSON).

Ported from ``services/ai`` — the primary retrieval mechanism for the agent
orchestrator. Legacy BM25/embedding RAG lives under ``app.retrieval`` sibling
modules and is no longer wired into the live path.
"""

from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
from app.retrieval.graph_engine.graph_registry import GraphRegistry, graph_registry
from app.retrieval.graph_engine.graph_tools import build_graph_tools, parse_tool_result

__all__ = [
    "AcademicGraphEngine",
    "GraphRegistry",
    "build_graph_tools",
    "graph_registry",
    "parse_tool_result",
]
