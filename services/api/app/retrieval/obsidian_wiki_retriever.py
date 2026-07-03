"""Obsidian wiki hybrid retriever (spec §15) — delegates to profile-aware engine."""

from __future__ import annotations

from app.retrieval.hybrid_wiki_retriever import (  # noqa: F401
    retrieve_wiki_context,
    retrieve_wiki_context_with_profile,
)
