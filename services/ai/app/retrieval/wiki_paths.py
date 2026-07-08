"""Shared wiki path helpers (no retrieval imports)."""

from __future__ import annotations

from pathlib import Path


def resolve_wiki_root(path: str) -> str:
    """Return an absolute wiki root so chunk/index caches stay stable."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    return str(candidate)
