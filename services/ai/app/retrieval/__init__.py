"""Retrieval package — structured Mongo/catalog data + academic graph (wiki + semester JSON)."""

from app.retrieval.graph_engine.graph_registry import warmup_graph_engine

__all__ = [
    "warmup_graph_engine",
]
