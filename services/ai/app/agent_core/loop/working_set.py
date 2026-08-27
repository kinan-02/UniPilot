"""The working set -- the single source of truth for one advise turn and its
entire audit trail (AGENT_ARCHITECTURE_V2.md §5).

It replaces V1's scattered `tool_audit_trail` plumbing and `PlanExecutionState`.
A `Fact` is an immutable grounded value (it can only be born in the substrate --
never typed by the model, see Invariant A); the working set is the mutable
per-request accumulator that grows as the loop runs. Facts and the tool-result
index render into the prompt each turn; the raw tool payloads never do (context
discipline: a 40-page page fetched on turn 2 is addressed by handle, not
re-injected on turns 3-10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.subagents.fact_projection import available_paths, describe_call

# How many trailing observations to render each turn. The full log is the audit
# trail; the prompt only needs the recent tail so the model can react to the last
# turn's outcome without the whole history flooding context.
_OBSERVATION_TAIL = 8

# A call signature bound to a large object (a what-if state, via arg-refs) would
# otherwise dump the whole object into the index -- clip it; the handle + paths
# are what the model addresses it by.
_INDEX_CALL_CLIP = 160

# A fact's basis is "authoritative" when a composed answer needs no hedge for it:
# an official record, or arithmetic purely over authoritative inputs. Every other
# basis (interpreted text, a predicted pattern, a simulated what-if) is qualified
# and must render hedged in the answer (§4.2). `apply_compute` narrows a computed
# fact's basis to its weakest input, so "computed" here always means "computed
# over authoritative inputs".
AUTHORITATIVE_BASES = frozenset({"official_record", "computed"})


@dataclass(frozen=True)
class Fact:
    """One grounded fact. Immutable: a fact's value is fixed the moment it is
    admitted (fetched/computed/interpreted/selected); the working set replaces
    the entry to "change" it, never mutates in place.

    `basis` is the certainty basis inherited from the fact's origin
    (`official_record` / `wiki_derived` / `predicted_pattern` /
    `llm_interpretation` / `simulated` / `computed`) so a composed answer can
    render an official record flat and a prediction hedged (§4.2).
    """

    value: Any
    source: str
    basis: str
    confidence: float


@dataclass
class WorkingSet:
    """Per-request accumulator. Created fresh per request (never shared across
    turns or students -- the freshness invariant that makes cross-student state
    leakage structurally impossible, §5).
    """

    question: str
    user_id: str
    language: str = "en"
    sub_asks: list[str] = field(default_factory=list)
    facts: dict[str, Fact] = field(default_factory=dict)
    tool_results: dict[str, Any] = field(default_factory=dict)
    handles: dict[str, str] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    derivations: set[str] = field(default_factory=set)

    def admit_derivation(self, key: str, fact: Fact, signature: str) -> bool:
        """Store `fact` under `key` and report whether it is NEW INFORMATION --
        whether this exact derivation has been performed before. `signature`
        identifies the OPERATION (a selector's handle+path, a select spec, an
        expression), never the resulting value -- so two distinct fields that
        happen to share a value (two booleans from one call) are never collapsed.

        Re-deriving a value already held, under a fresh key, still STORES it (so a
        later fact_ref resolves) but returns False: it is not progress. This is
        the structural anti-wander signal the no-progress governor counts (§7) --
        a model that re-selects a record it already has cannot fool the governor
        by renaming the fact, which is what let the eval's hardest cases burn
        their whole budget re-deriving.
        """
        self.facts[key] = fact
        if signature in self.derivations:
            return False
        self.derivations.add(signature)
        return True

    def observe(self, message: str) -> None:
        self.observations.append(message)


@dataclass(frozen=True)
class Terminal:
    """A turn's terminal outcome: the loop concluded this turn."""

    kind: str  # "answered" | "clarified"
    text: str
    ungrounded: list[str]
    # The refs the accepted answer stood on, carried so the readability pass can
    # prove its rewrite dropped none of them.
    fact_refs: dict[str, Any] = field(default_factory=dict)


def summarize_value(value: Any) -> str:
    """A one-line shape summary for the prompt's facts/index -- never the full
    payload (context discipline, §5).

    A list of RECORDS shows its length and record fields (so the model knows what
    to `select` on); a list of SCALARS shows a short SAMPLE of its values, so the
    model can SEE the fact holds real, slottable/selectable data. Without that, a
    bare "[list of N items]" reads as "no values here" -- measured live, a
    sub-loop and a forced compose each gave up on a list they actually held."""
    if isinstance(value, list):
        if not value:
            return "[list of 0 items]"
        sample = value[0]
        if isinstance(sample, dict):
            return f"[list of {len(value)} records, fields: {sorted(sample.keys())}]"
        preview = ", ".join(str(item)[:24] for item in value[:3])
        more = ", …" if len(value) > 3 else ""
        return f"[list of {len(value)} values: {preview}{more}]"
    if isinstance(value, dict):
        return f"{{dict with keys: {sorted(value.keys())}}}"
    return json.dumps(value, ensure_ascii=False, default=str)


def _render_facts(ws: WorkingSet) -> str:
    if not ws.facts:
        return "  (none yet)"
    return "\n".join(
        f"  {key} = {summarize_value(fact.value)}  "
        f"(source: {fact.source}; basis: {fact.basis}; conf: {fact.confidence})"
        for key, fact in ws.facts.items()
    )


def _render_index(ws: WorkingSet) -> str:
    if not ws.handles:
        return "  (no tool calls yet)"
    lines: list[str] = []
    for handle, result_key in ws.handles.items():
        envelope = ws.tool_results.get(result_key, {})
        signature = describe_call(result_key)[:_INDEX_CALL_CLIP]
        if envelope.get("ok"):
            lines.append(
                f"  {handle} = {signature}  ok=True\n"
                f"     paths: {available_paths(envelope)}"
            )
        else:
            lines.append(f"  {handle} = {signature}  ok=False error={envelope.get('error')}")
    return "\n".join(lines)


def render_working_set(ws: WorkingSet, turn: int, max_turns: int) -> str:
    """The dynamic (uncached) prompt tier, §5. Carries the facts and an INDEX of
    tool results (handles + shapes + available paths) -- never the raw payloads."""
    obs = "\n".join(f"  - {o}" for o in ws.observations[-_OBSERVATION_TAIL:]) or "  (none)"
    sub_asks = "\n".join(f"  - {s}" for s in ws.sub_asks) or "  (none)"
    return (
        f"QUESTION: {ws.question}\n"
        f"USER_ID: {ws.user_id}\n\n"
        f"SUB-ASKS -- your final answer MUST address every one of these:\n{sub_asks}\n\n"
        f"GROUNDED FACTS:\n{_render_facts(ws)}\n\n"
        f"TOOL RESULTS INDEX:\n{_render_index(ws)}\n\n"
        f"OBSERVATIONS (recent):\n{obs}\n\n"
        f"BUDGET: turn {turn}/{max_turns}. Emit one JSON object with tool_calls."
    )


__all__ = ["AUTHORITATIVE_BASES", "Fact", "WorkingSet", "Terminal", "summarize_value", "render_working_set"]
