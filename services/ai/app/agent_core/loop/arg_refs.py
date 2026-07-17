"""Argument binding -- pass a grounded object into a tool call (§17.3).

The what-if chain (`mutate_state` an altered state -> `check_eligibility` /
`simulate_course_disruption` over it) needs a fetched or computed object -- the
student's `state` -- as a tool ARGUMENT. The model cannot type such an object
(the grounding law, and it is large), so it names a grounded fact instead: an
argument value of the exact form `{"ref": "factKey"}` is replaced, in code, by
that fact's value before the tool input is built.

This is the tool-input analogue of `surface_fact`'s selector. Grounding is
preserved: the object comes from a grounded fact, the tool's output is itself
surfaced as a grounded fact, and the answer's numbers still slot only from
grounded facts (§4.2). A what-if parameter typed as a literal (the course to
fail, the semester) is a simulation INPUT, not an answer fact -- unaffected.

Only DATA-tool arguments pass through here; the meta-tools (compute's own
`{"ref": ...}` expression leaves, surface, select) are dispatched separately, so
there is no collision with expression-tree refs.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.loop.working_set import Fact


def _is_arg_ref(node: Any) -> str | None:
    """A node is an arg-ref iff it is exactly `{"ref": "<str>"}`. Returns the
    referenced fact key, or None if the node is ordinary data to recurse into."""
    if isinstance(node, dict) and set(node.keys()) == {"ref"} and isinstance(node["ref"], str):
        return node["ref"]
    return None


def resolve_arg_refs(arguments: Any, facts: dict[str, Fact]) -> tuple[Any, list[str]]:
    """Recursively replace every `{"ref": factKey}` in `arguments` with the
    referenced fact's value. Returns (resolved_arguments, errors). A ref naming
    no grounded fact is an error (and left in place) so the caller can fail the
    call closed with a repairable message rather than dispatch a malformed one."""
    errors: list[str] = []

    def _walk(node: Any) -> Any:
        ref_key = _is_arg_ref(node)
        if ref_key is not None:
            if ref_key in facts:
                return facts[ref_key].value
            errors.append(
                f"arg ref {{'ref': '{ref_key}'}} names no grounded fact "
                f"(available: {sorted(facts)}); surface it first."
            )
            return node
        if isinstance(node, dict):
            return {key: _walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(arguments), errors


__all__ = ["resolve_arg_refs"]
