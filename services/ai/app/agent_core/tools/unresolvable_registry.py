"""Turn-scoped registry of entity lookups/searches that returned conclusively
empty results -- a negative-fact cache.

Parallel to `ToolCallCache` in spirit, but storing negative facts (keyed by the
literal query string, not a fuzzy-matched full result).  When `get_entity`
comes back ``entity_not_found`` or `search_knowledge` returns zero matches for
a specific search term, that term is recorded as a known dead end.  The
registry's ``snapshot()`` is surfaced as a first-class structured field on
``PlannerInvocationInput`` (``unresolvable_entities``) so every Planner
invocation -- top-level or nested -- sees it directly and is instructed: "if a
referenced entity is already listed as unresolvable, do not schedule another
search for it."

Much lower-risk than caching whole specialist results, because this is a
negative fact (*something doesn't exist*) rather than a positive answer that
could be subtly wrong if reused for a slightly different question.

One ``UnresolvableEntityRegistry`` instance is created fresh per turn
(``turn.py::run_agent_turn``) and threaded down through every specialist
dispatch -- atomic or nested, sibling or parent/child -- exactly the same
chain as ``ToolCallCache``.  Never a module-level global: a registry shared
across turns/requests would leak one student's dead ends into another's.
"""

from __future__ import annotations


class UnresolvableEntityRegistry:
    """Plain, mutable wrapper -- deliberately not a ``BaseModel``, since this
    is a runtime-only collaborator (like ``ToolCallCache`` / ``ToolRegistry``),
    never serialized or part of any schema."""

    def __init__(self) -> None:
        self._dead_ends: dict[str, str] = {}  # normalized_query -> reason

    def record(self, query: str, reason: str) -> None:
        """Record a search term as a known dead end."""
        self._dead_ends[query.strip().lower()] = reason

    def is_known_dead_end(self, query: str) -> bool:
        """Check whether a search term has already been tried and failed."""
        return query.strip().lower() in self._dead_ends

    def snapshot(self) -> list[str]:
        """Return a sorted list of dead-end query strings, suitable for
        ``PlannerInvocationInput.unresolvable_entities``."""
        return sorted(self._dead_ends.keys())


__all__ = ["UnresolvableEntityRegistry"]
