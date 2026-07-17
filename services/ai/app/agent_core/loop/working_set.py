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

    def add_fact(self, key: str, fact: Fact) -> bool:
        """Admit a fact. Returns True if it is genuinely new (a key not seen, or
        a changed value) -- the signal the no-progress governor counts (§7). A
        re-surface of an identical fact is a no-op for progress accounting.
        """
        existing = self.facts.get(key)
        self.facts[key] = fact
        return existing is None or existing.value != fact.value

    def observe(self, message: str) -> None:
        self.observations.append(message)


@dataclass(frozen=True)
class Terminal:
    """A turn's terminal outcome: the loop concluded this turn."""

    kind: str  # "answered" | "clarified"
    text: str
    ungrounded: list[str]


def summarize_value(value: Any) -> str:
    """A one-line shape summary for the prompt's facts/index -- never the full
    payload (context discipline, §5). A list shows its length and record keys so
    the model knows it can `select` over it."""
    if isinstance(value, list):
        sample = value[0] if value else None
        keys = sorted(sample.keys()) if isinstance(sample, dict) else None
        tail = f", record keys: {keys}" if keys else ""
        return f"[list of {len(value)} items{tail}]"
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


__all__ = ["Fact", "WorkingSet", "Terminal", "summarize_value", "render_working_set"]
